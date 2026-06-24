"""
Generate a per-fund outreach angle for SocialGravity (My Twin): a one-line
"why this fund fits" grounded in the fund's actual thesis, and a one-line
cold-open hook for the first email. Drafts, meant to be edited.

Writes fit_sg + cold_angle onto the kept records in the cache; run reselect.py
afterwards.

  python fit.py
  python fit.py --workers 12
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.select import passes_filter
from providers import llm

RECORDS_CACHE = "data/_records.json"

_PRODUCT = (
    "SocialGravity makes My Twin: a consumer product where a person scrapes or "
    "interviews themselves and gets an AI voice twin that other people can talk "
    "to (voice-first, also text). It is B2C / creator-economy, and two-sided "
    "(creators publish twins, visitors talk to them), so it has marketplace "
    "dynamics. Currently raising a pre-seed in San Francisco."
)

_SYS = (
    "You write concise, factual fundraising outreach notes for the founder of "
    "SocialGravity. No hype, no emoji, no em dashes, plain direct language. "
    "Ground everything in the specific fund's stated focus."
)


def gen(rec: dict) -> dict:
    prompt = (
        f"{_PRODUCT}\n\n"
        f"Fund: {rec.get('firm','')}\n"
        f"Their thesis: {rec.get('thesis','')}\n"
        f"Their sectors: {', '.join(rec.get('sectors', []) or [])}\n"
        f"Marketplace focus: {'yes' if rec.get('is_marketplace') else 'no'}\n\n"
        'Return JSON {"fit_sg": str, "cold_angle": str}. '
        '"fit_sg" = one sentence on why this specific fund is a plausible fit for '
        "SocialGravity, tied to their stated focus (say so plainly if the fit is "
        'weak). "cold_angle" = one sentence the founder could open a cold email '
        "with, referencing something specific about the fund. Keep each under 40 words."
    )
    return llm.chat_json(_SYS, prompt, temperature=0.3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--size-ceiling", type=float, default=50_000_000)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    targets = [r for r in recs if passes_filter(r, args.size_ceiling)]
    print(f"generating fit + angle for {len(targets)} funds...")

    def work(r: dict):
        return r, gen(r)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, r) for r in targets]):
            done += 1
            try:
                r, d = fut.result()
            except Exception:
                r, d = None, None
            if r is not None and d:
                if d.get("fit_sg"):
                    r["fit_sg"] = d["fit_sg"]
                if d.get("cold_angle"):
                    r["cold_angle"] = d["cold_angle"]
            if done % 25 == 0:
                print(f"  {done}/{len(targets)}")

    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    n = sum(1 for r in targets if r.get("fit_sg"))
    print(f"done. fit + angle on {n}/{len(targets)} funds")
    print("next: python reselect.py && python aggregate.py && python push_notion.py --db <id> --replace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
