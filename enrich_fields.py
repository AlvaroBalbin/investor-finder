"""
Squeeze three specific fields as hard as possible on the kept set:
  - check_size        (typical check the fund writes)
  - est_fund_size_usd (total fund AUM estimate + bucket/confidence)
  - is_marketplace    (re-judged leniently: does it back marketplaces / two-
                       sided networks / commerce platforms at all)

For each fund it runs dedicated searches plus a fresh read of the fund's site,
then a single extraction call. Fills blanks (never blanks out existing data) and
only upgrades the marketplace flag. Writes back to the cache; run reselect.py
afterwards.

  python enrich_fields.py
  python enrich_fields.py --workers 10
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline import profile
from pipeline.exclude import is_excluded
from pipeline.output import stage_is_early
from providers import llm, search

RECORDS_CACHE = "data/_records.json"

_SYS = (
    "You are a meticulous VC-data analyst. State only what the evidence supports. "
    "Give est_fund_size_usd ONLY with a real basis (a stated figure, or fund number "
    "plus check size, or team size); otherwise null. Never invent. Marketplace means "
    "the fund backs marketplaces, two-sided networks, or commerce platforms."
)


def _targeted_evidence(firm: str) -> str:
    bits = []
    for q in (
        f"{firm} venture fund typical check size investment",
        f"{firm} fund size assets under management million raised",
        f"{firm} marketplace two-sided network portfolio companies",
    ):
        for r in search.web_search(q, num=5):
            sn = r.get("snippet", "")
            if sn:
                bits.append(f"- {r.get('title','')}: {sn}")
    return "\n".join(bits[:15])


def enrich_one(rec: dict) -> dict:
    site_text, _ = profile._gather_site_text(rec.get("website", ""))
    evidence = _targeted_evidence(rec["firm"])
    prompt = f"""Fund: {rec['firm']}
Website: {rec.get('website','')}
Thesis: {rec.get('thesis','')}
Sectors: {', '.join(rec.get('sectors', []) or [])}
Known check size: {rec.get('check_size','') or 'unknown'}
Known fund size: {rec.get('est_fund_size_usd') or 'unknown'}

--- SITE TEXT ---
{site_text or '(none)'}

--- TARGETED WEB EVIDENCE ---
{evidence or '(none)'}

Return JSON:
{{
  "check_size": str,
  "est_fund_size_usd": number|null,
  "size_bucket": "micro"|"small"|"mid"|"large"|"mega"|"unknown",
  "size_confidence": "low"|"medium"|"high",
  "fund_size_basis": str,
  "is_marketplace": bool
}}"""
    return llm.chat_json(_SYS, prompt, temperature=0.1)


def merge(rec: dict, d: dict) -> None:
    if not d:
        return
    if not (rec.get("check_size") or "").strip() and (d.get("check_size") or "").strip():
        rec["check_size"] = d["check_size"]
    # Never let an LLM estimate overwrite an authoritative SEC Form D figure.
    if str(rec.get("fund_size_source", "")).startswith("SEC"):
        if d.get("is_marketplace"):
            rec["is_marketplace"] = True
        return
    # Fill fund size if missing, or upgrade when the new read is more confident.
    new_size = d.get("est_fund_size_usd")
    if isinstance(new_size, (int, float)):
        cur = rec.get("est_fund_size_usd")
        new_conf = d.get("size_confidence", "low")
        if not isinstance(cur, (int, float)) or new_conf == "high":
            rec["est_fund_size_usd"] = new_size
            rec["size_confidence"] = new_conf
            rec["fund_size_basis"] = d.get("fund_size_basis", rec.get("fund_size_basis", ""))
            if d.get("size_bucket"):
                rec["size_bucket"] = d["size_bucket"]
    elif d.get("size_bucket") and not (rec.get("size_bucket") or ""):
        rec["size_bucket"] = d["size_bucket"]
    # Only upgrade marketplace (do not blank an existing yes).
    if d.get("is_marketplace"):
        rec["is_marketplace"] = True


def relevant(r: dict) -> bool:
    return (
        not is_excluded(r.get("firm", ""))
        and r.get("is_us")
        and (r.get("is_consumer") or r.get("is_marketplace"))
        and stage_is_early(r.get("stage", []))
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    targets = [r for r in recs if relevant(r)]
    print(f"enriching {len(targets)} funds (check size / fund size / marketplace)...")

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(enrich_one, r): r for r in targets}
        for fut in as_completed(futures):
            done += 1
            r = futures[fut]
            try:
                merge(r, fut.result())
            except Exception:
                pass
            if done % 25 == 0:
                print(f"  enriched {done}/{len(targets)}")

    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    cs = sum(1 for r in targets if (r.get("check_size") or "").strip())
    sz = sum(1 for r in targets if isinstance(r.get("est_fund_size_usd"), (int, float)))
    mk = sum(1 for r in targets if r.get("is_marketplace"))
    print(f"done. check size: {cs}/{len(targets)} | fund size: {sz}/{len(targets)} | marketplace: {mk}/{len(targets)}")
    print("next: python reselect.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
