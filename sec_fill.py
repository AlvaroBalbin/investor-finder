"""
Override fund-size estimates with authoritative SEC Form D figures.

For each relevant fund we look up its flagship Form D offering amount on EDGAR
and, when found, replace the LLM estimate with the real number (and recompute
the size bucket + sub-$20M from it). Funds with no Form D keep their estimate,
flagged as such. Writes back to the cache; run reselect.py afterwards.

  python sec_fill.py
  python sec_fill.py --workers 6
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.exclude import is_excluded, is_not_fund
from pipeline.output import stage_is_early
from providers import llm, sec

RECORDS_CACHE = "data/_records.json"


def bucket_for(amount: float) -> str:
    if amount < 20_000_000:
        return "micro"
    if amount < 50_000_000:
        return "small"
    if amount < 200_000_000:
        return "mid"
    if amount < 1_000_000_000:
        return "large"
    return "mega"


def relevant(r: dict) -> bool:
    return (
        not is_excluded(r.get("firm", ""))
        and not is_not_fund(r.get("firm", ""), r.get("website", ""))
        and r.get("is_us")
        and (r.get("is_consumer") or r.get("is_marketplace"))
        and stage_is_early(r.get("stage", []))
    )


_EST_SYS = (
    "You estimate venture fund size from the signals given. Give your best rough "
    "estimate even if approximate, never null. A small / emerging / pre-seed fund "
    "is usually $5M to $40M; infer from check size (small checks imply a small "
    "fund), stage, and team. Famous large firms are bigger."
)


def estimate_size(rec: dict) -> dict:
    prompt = (
        f"Fund: {rec.get('firm','')}\n"
        f"Thesis: {rec.get('thesis','')}\n"
        f"Sectors: {', '.join(rec.get('sectors', []) or [])}\n"
        f"Stage: {rec.get('stage')}\n"
        f"Check size: {rec.get('check_size','') or 'unknown'}\n\n"
        'Return JSON {"est_fund_size_usd": number, "size_bucket": '
        '"micro"|"small"|"mid"|"large"|"mega", "size_confidence": "low"|"medium"}. '
        "Give a number."
    )
    return llm.chat_json(_EST_SYS, prompt, temperature=0.2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    targets = [r for r in recs if relevant(r)]
    # Skip funds already carrying an authoritative SEC figure.
    to_query = [r for r in targets if not str(r.get("fund_size_source", "")).startswith("SEC")]
    print(f"looking up SEC Form D for {len(to_query)} funds (of {len(targets)} relevant)...")

    def work(r: dict):
        return r, sec.form_d_size(r["firm"])

    found = 0
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, r) for r in to_query]
        for fut in as_completed(futures):
            done += 1
            try:
                r, res = fut.result()
            except Exception:
                res = None
                r = None
            if r is not None and res:
                amt = res["amount"]
                r["est_fund_size_usd"] = amt
                r["size_bucket"] = bucket_for(amt)
                r["size_confidence"] = "high" if res.get("is_main") else "medium"
                r["fund_size_source"] = f"SEC Form D: {res['entity']} ({res['year']})"
                r["fund_size_basis"] = "SEC Form D total offering amount"
                found += 1
            if done % 25 == 0:
                print(f"  checked {done}/{len(targets)} (SEC hits: {found})")

    # Forced estimate for any relevant fund still lacking a figure (no blanks).
    still = [r for r in targets if not isinstance(r.get("est_fund_size_usd"), (int, float))]
    print(f"estimating {len(still)} funds with no SEC figure...")

    def est_work(r: dict):
        return r, estimate_size(r)

    est_done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for fut in as_completed([ex.submit(est_work, r) for r in still]):
            try:
                r, d = fut.result()
            except Exception:
                r, d = None, None
            if r is not None and d and isinstance(d.get("est_fund_size_usd"), (int, float)):
                r["est_fund_size_usd"] = d["est_fund_size_usd"]
                r["size_bucket"] = (d.get("size_bucket") or bucket_for(d["est_fund_size_usd"])).lower()
                r["size_confidence"] = d.get("size_confidence", "low")
                r["fund_size_source"] = "estimate"
                r["fund_size_basis"] = "estimate from check size / stage / thesis"
                est_done += 1

    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print(f"done. SEC Form D: {found}, estimated: {est_done} of {len(targets)} funds")
    print("next: python reselect.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
