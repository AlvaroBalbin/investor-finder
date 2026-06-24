"""
Second-pass consumer classification on cached records.

The first profiling pass marks is_consumer too strictly: a generalist or
sector-agnostic fund that happily backs consumer startups gets is_consumer=
False just because its page does not shout "consumer". The brief is "funds
open to consumer", not "consumer-only", so this pass re-judges every record
currently flagged not-consumer using its stored thesis + sectors (no web work)
and recovers the ones that are genuinely consumer-open.

Writes the updated records back to the cache. Idempotent.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from providers import llm

RECORDS_CACHE = "data/_records.json"

_SYS = (
    "You decide whether a venture fund is OPEN to investing in consumer / B2C / "
    "DTC startups. A generalist or sector-agnostic fund counts as YES, because it "
    "is open to consumer deals. Answer NO only when the fund is explicitly and "
    "almost exclusively B2B / enterprise SaaS / infrastructure / deep tech / "
    "hardware / climate-hardware / dev tools and clearly does not do consumer."
)


def judge(rec: dict) -> dict:
    sectors = ", ".join(rec.get("sectors", []) or [])
    prompt = (
        f"Fund: {rec.get('firm','')}\n"
        f"Thesis: {rec.get('thesis','')}\n"
        f"Sectors: {sectors or '(none listed)'}\n"
        f"Hint: {rec.get('discovery_source','')}\n\n"
        'Return JSON {"consumer_open": bool, "is_marketplace": bool, "reason": str}.'
    )
    return llm.chat_json(_SYS, prompt, temperature=0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    todo = [r for r in recs if not (r.get("is_consumer") or r.get("is_marketplace"))]
    print(f"re-judging {len(todo)} not-consumer records (of {len(recs)} total)...")

    def work(r: dict) -> None:
        d = judge(r)
        if d.get("consumer_open"):
            r["is_consumer"] = True
            r["consumer_confidence"] = r.get("consumer_confidence") or "low"
            r["consumer_recovered"] = True
        if d.get("is_marketplace"):
            r["is_marketplace"] = True
        r["consumer_reason"] = d.get("reason", "")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, todo))

    recovered = sum(1 for r in todo if r.get("consumer_recovered"))
    print(f"recovered {recovered} consumer-open funds")
    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print(f"updated cache -> {args.records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
