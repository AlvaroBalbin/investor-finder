"""
Generate a per-fund outreach angle for YOUR company: a one-line "why this fund
fits" grounded in the fund's actual thesis, and a one-line cold-open hook for
the first email. Drafts, meant to be edited.

Describe your company once via the COMPANY_NAME and COMPANY_PITCH env vars (see
.env.example); both feed the prompt below. With no pitch set, this falls back to
a placeholder so the step still runs.

Writes fit_note + cold_angle onto the kept records in the cache; run reselect.py
afterwards.

  python fit.py
  python fit.py --workers 12
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config
from pipeline.select import passes_filter
from providers import llm

RECORDS_CACHE = "data/_records.json"

_COMPANY = config.get("COMPANY_NAME", "our company")
_PRODUCT = config.get("COMPANY_PITCH") or (
    "Describe your company in 2-3 sentences here: what you build, the sector and "
    "business model, and what round you are raising. Set COMPANY_PITCH in your "
    ".env to replace this placeholder with your real pitch."
)

_SYS = (
    f"You write concise, factual fundraising outreach notes for the founder of "
    f"{_COMPANY}. No hype, no emoji, no em dashes, plain direct language. "
    "Ground everything in the specific fund's stated focus."
)


def gen(rec: dict) -> dict:
    prompt = (
        f"{_PRODUCT}\n\n"
        f"Fund: {rec.get('firm','')}\n"
        f"Their thesis: {rec.get('thesis','')}\n"
        f"Their sectors: {', '.join(rec.get('sectors', []) or [])}\n"
        f"Marketplace focus: {'yes' if rec.get('is_marketplace') else 'no'}\n\n"
        'Return JSON {"fit_note": str, "cold_angle": str}. '
        '"fit_note" = one sentence on why this specific fund is a plausible fit for '
        f"{_COMPANY}, tied to their stated focus (say so plainly if the fit is "
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
                if d.get("fit_note"):
                    r["fit_note"] = d["fit_note"]
                if d.get("cold_angle"):
                    r["cold_angle"] = d["cold_angle"]
            if done % 25 == 0:
                print(f"  {done}/{len(targets)}")

    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    n = sum(1 for r in targets if r.get("fit_note"))
    print(f"done. fit + angle on {n}/{len(targets)} funds")
    print("next: python reselect.py && python aggregate.py && python push_notion.py --db <id> --replace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
