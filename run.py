"""
sg-investor-finder: find small US VC funds that lean consumer / B2C (with a
marketplace tilt where possible), and resolve a LinkedIn URL and best-effort
email for each fund's founders/partners.

Pipeline: discover -> verify+profile -> [cache] -> filter+contacts -> output.

The profiled records are cached to data/_records.json, so you can re-tune the
selection (filters, ranking) cheaply with `python reselect.py` instead of
re-profiling every firm.

Usage:
  python run.py                       # full run, default target
  python run.py --target 200          # aim for ~200 funds
  python run.py --max-candidates 500  # widen the discovery pool
  python run.py --no-listicles        # skip article harvesting (faster)
  python run.py --enrichment-email     # also try the paid email endpoint
  python run.py --out data/funds.csv  # output path
  python run.py --notion              # also push to Notion (needs token+parent)
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config
from pipeline import discover, profile, select

RECORDS_CACHE = "data/_records.json"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=150)
    ap.add_argument("--max-candidates", type=int, default=500)
    ap.add_argument("--size-ceiling", type=float, default=50_000_000)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-listicles", action="store_true")
    ap.add_argument("--enrichment-email", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--out", default="data/us_consumer_vc_funds.csv")
    ap.add_argument("--notion", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="debug: cap firms profiled")
    args = ap.parse_args()

    log(f"providers configured: {config.status()}")

    # 1. Discover.
    log("discovering candidates...")
    candidates = discover.discover(use_llm=not args.no_llm, use_listicles=not args.no_listicles)
    log(f"  {len(candidates)} unique candidate firms")
    candidates = candidates[: args.max_candidates]
    if args.limit:
        candidates = candidates[: args.limit]

    # 2. Verify + profile (concurrent).
    log(f"verifying + profiling {len(candidates)} firms...")
    records: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(profile.profile_firm, c): c for c in candidates}
        for fut in as_completed(futures):
            done += 1
            try:
                rec = fut.result()
            except Exception:
                rec = None
            if rec:
                records.append(rec)
            if done % 20 == 0:
                log(f"  profiled {done}/{len(candidates)} (real VCs: {len(records)})")

    # 2b. Cache the profiled records for cheap re-selection.
    Path(RECORDS_CACHE).parent.mkdir(parents=True, exist_ok=True)
    Path(RECORDS_CACHE).write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    log(f"cached {len(records)} profiled records -> {RECORDS_CACHE}")

    # 3-5. Filter + contacts + rank + output.
    select.select_and_output(
        records,
        size_ceiling=args.size_ceiling,
        out_path=args.out,
        workers=args.workers,
        enrichment_email=args.enrichment_email,
        notion=args.notion,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
