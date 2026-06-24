"""
Grow the candidate pool incrementally without re-profiling what we already
have. Generates fresh consumer-niche candidates (by vertical and by city),
dedupes against the firms already in the cache, profiles only the NEW ones,
and appends them to data/_records.json.

Run reclassify.py then reselect.py afterwards to fold them into the output.

  python expand.py
  python expand.py --workers 12
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline import discover, profile
from pipeline.exclude import is_excluded
from providers import llm, search, web

RECORDS_CACHE = "data/_records.json"

# Round-2 niches + geographies, chosen to surface funds the first pass missed.
# Dedup against the cache means only genuinely new firms get profiled, so it is
# safe to re-run with a fresh angle set.
_NICHE_ANGLES = [
    "US seed funds investing in music, audio, or podcasting consumer startups",
    "US early-stage funds investing in consumer sustainability or climate-friendly brands",
    "US seed funds investing in longevity, senior care, or aging consumer products",
    "US early-stage funds investing in consumer hardware or smart home products",
    "US seed funds investing in sports, outdoor, or fitness-tech consumer startups",
    "US early-stage funds investing in mobility, micromobility, or consumer automotive",
    "US seed funds investing in consumer AI apps or companion apps",
    "US early-stage funds investing in food-tech, restaurant-tech, or grocery startups",
    "US seed funds investing in consumer subscription or membership businesses",
    "US early-stage funds backing second-time or operator founders in consumer",
    "US pre-seed funds writing checks under $250k into consumer startups",
    "US seed funds investing in LGBTQ, Latino, or Asian-American led consumer startups",
    "Texas or Southeast US based early-stage consumer venture funds",
    "Midwest US based seed-stage consumer and marketplace venture funds",
    "Pacific Northwest or Mountain West consumer venture funds",
    "US university-affiliated or alumni-backed consumer seed funds",
    "US faith-based or values-driven consumer venture funds",
    "US studio and venture-builder funds focused on consumer brands",
]

_NICHE_LISTICLES = [
    "consumer hardware venture capital funds list",
    "food tech venture capital seed funds",
    "climate consumer brands venture funds",
    "consumer subscription venture funds list",
    "texas consumer venture capital funds",
    "midwest consumer seed funds list",
    "operator led consumer venture funds list",
]


def _niche_llm() -> list[dict]:
    out = []
    sys = (
        "You are a venture-capital research assistant. Return only REAL funds "
        "that exist. Never invent names."
    )
    for angle in _NICHE_ANGLES:
        prompt = (
            f"List up to 30 {angle}. Return JSON {{\"funds\": [{{\"firm\": str, "
            "\"website\": str, \"hint\": str}}]}}. US-based, smaller / emerging funds."
        )
        data = llm.chat_json(sys, prompt, model=llm.big_model(), temperature=0.5)
        for f in data.get("funds", []) or []:
            firm = (f.get("firm") or "").strip()
            if firm:
                dom = (f.get("website") or "").replace("https://", "").replace("http://", "").strip("/")
                out.append({"firm": firm, "website": f"https://{dom}" if dom else "", "hint": f.get("hint", ""), "source": "niche_llm"})
    return out


def _niche_listicles() -> list[dict]:
    urls, seen = [], set()
    for q in _NICHE_LISTICLES:
        for r in search.web_search(q, num=8):
            link = r.get("link", "")
            if link and link not in seen and "linkedin.com" not in link:
                seen.add(link)
                urls.append(link)
    out = []
    for url in urls[:12]:
        html = web.fetch(url)
        if not html:
            continue
        text = web.to_text(html, limit=9000)
        if "venture" not in text.lower() and "vc" not in text.lower():
            continue
        data = llm.chat_json(
            "Extract real US consumer/marketplace VC fund names. Do not invent any.",
            "List every US venture fund mentioned that invests in consumer or marketplace "
            'startups. Return JSON {"funds":[{"firm":str,"hint":str}]}.\n\n' + text,
        )
        for f in data.get("funds", []) or []:
            firm = (f.get("firm") or "").strip()
            if firm:
                out.append({"firm": firm, "website": "", "hint": f.get("hint", ""), "source": "niche_listicle"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=RECORDS_CACHE)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    recs = json.loads(Path(args.records).read_text(encoding="utf-8"))
    existing = {discover._norm(r.get("firm", "")) for r in recs}
    print(f"cache has {len(recs)} records")

    pool = _niche_llm() + _niche_listicles()
    # Dedup against existing + within new, and drop megafunds before profiling.
    fresh, fresh_keys = [], set()
    for c in pool:
        k = discover._norm(c["firm"])
        if not k or k in existing or k in fresh_keys or is_excluded(c["firm"]):
            continue
        fresh_keys.add(k)
        fresh.append(c)
    print(f"generated {len(pool)} niche candidates, {len(fresh)} new after dedup/exclude")

    new_records = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(profile.profile_firm, c): c for c in fresh}
        for fut in as_completed(futures):
            done += 1
            try:
                rec = fut.result()
            except Exception:
                rec = None
            if rec:
                new_records.append(rec)
            if done % 20 == 0:
                print(f"  profiled {done}/{len(fresh)} (real VCs: {len(new_records)})")

    recs.extend(new_records)
    Path(args.records).write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print(f"added {len(new_records)} new real-VC records -> cache now {len(recs)}")
    print("next: python reclassify.py && python reselect.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
