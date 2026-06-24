"""
Re-run only the selection stage from cached profiled records (data/_records.json),
without re-profiling. Use this to tune filters / ranking quickly.

  python reselect.py
  python reselect.py --out data/funds.csv --size-ceiling 50000000
  python reselect.py --notion
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import select

RECORDS_CACHE = "data/_records.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--size-ceiling", type=float, default=50_000_000)
    ap.add_argument("--out", default="data/us_consumer_vc_funds.csv")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--enrichment-email", action="store_true")
    ap.add_argument("--notion", action="store_true")
    args = ap.parse_args()

    records = json.loads(Path(args.records).read_text(encoding="utf-8"))
    print(f"loaded {len(records)} cached records from {args.records}")
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
