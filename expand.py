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

# Round-3 angles: emerging-manager and city-by-city sweeps to surface the long
# tail of small consumer funds. Dedup against the cache means only genuinely new
# firms get profiled, so it is safe to re-run with a fresh angle set.
_NICHE_ANGLES = [
    "US first-check and day-one pre-seed funds backing consumer startups",
    "US AngelList rolling funds focused on consumer and B2C",
    "US consumer angel investors who run small funds or syndicates",
    "New York City based small consumer and DTC seed funds",
    "Los Angeles based consumer, commerce, and creator seed funds",
    "Austin or Dallas based early-stage consumer venture funds",
    "Miami based consumer and marketplace seed funds",
    "Chicago based consumer and CPG venture funds",
    "Boston based consumer and marketplace seed funds",
    "Seattle based consumer seed funds",
    "Atlanta or Nashville based consumer venture funds",
    "Denver or Salt Lake City based consumer seed funds",
    "US seed funds investing in consumer social, messaging, or community apps",
    "US seed funds investing in dating, relationships, or consumer connection apps",
    "US seed funds investing in baby, maternity, parenting, or kids consumer brands",
    "US seed funds investing in beauty, skincare, wellness, or sexual-wellness brands",
    "US seed funds investing in consumer travel, outdoor, or experiences",
    "US seed funds investing in consumer gaming, creator tools, or interactive media",
    "US seed funds investing in consumer real estate, home services, or proptech marketplaces",
    "US emerging-manager Fund I and Fund II consumer funds under $30M",
    "US women-led or BIPOC-led pre-seed consumer venture funds",
    "US consumer marketplaces and two-sided network specialist seed funds",
]

_NICHE_LISTICLES = [
    "list of pre-seed consumer venture funds new york",
    "los angeles consumer venture capital funds list",
    "miami venture capital consumer funds",
    "rolling funds consumer angellist list",
    "consumer marketplace seed funds list",
    "emerging manager consumer fund I list",
    "best consumer angel investors funds",
    "dtc brand venture capital funds list",
]


def _niche_llm() -> list[dict]:
    out = []
    sys = (
        "You are a venture-capital research assistant. Return only REAL funds "
        "that exist. Never invent names."
    )
    for angle in _NICHE_ANGLES:
        prompt = (
            f"List up to 40 {angle}. Return JSON {{\"funds\": [{{\"firm\": str, "
            "\"website\": str, \"hint\": str}}]}}. US-based, smaller / emerging funds."
        )
        data = llm.chat_json(sys, prompt, model=llm.big_model(), temperature=0.5)
        for f in data.get("funds", []) or []:
            firm = (f.get("firm") or "").strip()
            if firm:
                dom = (f.get("website") or "").replace("https://", "").replace("http://", "").strip("/")
                out.append({"firm": firm, "website": f"https://{dom}" if dom else "", "hint": f.get("hint", ""), "source": "niche_llm"})
    return out


import re as _re

# Investor directories + big curated lists. The fund name is usually right in
# the search-result title, so we harvest titles directly (cheap, no page fetch),
# and let profiling verify each one.
_DIRECTORY_QUERIES = [
    "site:openvc.app consumer",
    "site:openvc.app marketplace",
    "site:openvc.app pre-seed consumer",
    "site:signal.nfx.com consumer seed",
    "site:signal.nfx.com marketplace",
    "consumer venture fund openvc",
    "list of consumer pre-seed venture funds",
    "top consumer seed investors list",
    "dtc brand venture capital funds list",
    "marketplace focused seed investors list",
    "consumer fund I emerging managers list",
    "consumer angel syndicates list United States",
]

# Note: en/eM dash separators are normalized to a hyphen via chr() before this
# runs, so the pattern only needs the ascii separators.
_TITLE_SUFFIX = _re.compile(
    r"\s*[|:\-]\s*(openvc|signal.*|nfx|crunchbase|pitchbook|linkedin|wellfound|"
    r"angellist|home|investors?|venture capital|vc firm|profile).*$",
    _re.I,
)
_DASHES = (chr(0x2013), chr(0x2014))


def _directory_candidates() -> list[dict]:
    out, seen = [], set()
    for q in _DIRECTORY_QUERIES:
        for r in search.web_search(q, num=10):
            title = (r.get("title") or "").strip()
            for ch in _DASHES:
                title = title.replace(ch, "-")
            name = _TITLE_SUFFIX.sub("", title).strip()
            # Keep plausible firm names only.
            if not name or len(name) < 3 or len(name) > 60:
                continue
            if any(w in name.lower() for w in ("how to", "best ", "list of", "top ", "guide")):
                continue
            k = name.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append({"firm": name, "website": "", "hint": "directory", "source": "directory"})
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

    pool = _niche_llm() + _niche_listicles() + _directory_candidates()
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
