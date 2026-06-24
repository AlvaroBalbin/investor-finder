"""
Completeness pass: re-profile the funds that matter (US + consumer/marketplace
+ early-stage) to refresh HQ, stage, check size, and fund size from fresh web
evidence. Fills the blanks and corrects stage (so small funds stop reading as
"not pre-seed"). Merges back into the cache; run reclassify.py + reselect.py
afterwards.

  python fill.py
  python fill.py --workers 10
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline import profile
from pipeline.exclude import is_excluded
from pipeline.output import stage_is_early

RECORDS_CACHE = "data/_records.json"

# Fields refreshed from the new profiling pass.
_REFRESH = [
    "thesis", "sectors", "stage", "check_size", "est_fund_size_usd",
    "fund_size_basis", "size_confidence", "size_bucket", "hq_location",
    "is_consumer", "consumer_confidence", "is_marketplace", "partners",
    "_site_emails", "_email_domain", "website",
]


def loose_keep(r: dict) -> bool:
    return (
        not is_excluded(r.get("firm", ""))
        and r.get("is_us")
        and (r.get("is_consumer") or r.get("is_marketplace"))
        and stage_is_early(r.get("stage", []))
    )


def merge(old: dict, fresh: dict) -> dict:
    if not fresh:
        return old
    for k in _REFRESH:
        if k in fresh and fresh[k] not in (None, "", []):
            old[k] = fresh[k]
    # Never lose a previously recovered consumer flag.
    if old.get("consumer_recovered"):
        old["is_consumer"] = True
    return old


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    targets = [r for r in recs if loose_keep(r)]
    print(f"re-profiling {len(targets)} relevant funds (of {len(recs)})...")

    def work(r: dict):
        fresh = profile.profile_firm({"firm": r["firm"], "website": r.get("website", ""), "source": r.get("discovery_source", "")})
        return r, fresh

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, r) for r in targets]
        for fut in as_completed(futures):
            done += 1
            try:
                old, fresh = fut.result()
                merge(old, fresh)
            except Exception:
                pass
            if done % 25 == 0:
                print(f"  refreshed {done}/{len(targets)}")

    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    filled_hq = sum(1 for r in targets if (r.get("hq_location") or "").strip())
    filled_size = sum(1 for r in targets if isinstance(r.get("est_fund_size_usd"), (int, float)))
    print(f"done. HQ present: {filled_hq}/{len(targets)} | size present: {filled_size}/{len(targets)}")
    print("next: python reclassify.py && python reselect.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
