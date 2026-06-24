"""
Discovery: build a large candidate pool of US early-stage funds that may fit
the consumer / marketplace, sub-$50M thesis. Three independent sources are
merged and deduped:

  1. curated seeds (high precision, from seeds.py)
  2. LLM-proposed names across several angles (high recall; every name is
     verified later, so hallucinated funds get dropped, not shipped)
  3. Serper listicle harvest (catches funds outside the model's knowledge)

Output is a list of {firm, website, hint, source}. Nothing is trusted yet;
verification + classification happen downstream.
"""

from __future__ import annotations

import re

from providers import llm, search, web
from . import seeds

# Angles widen recall without drifting off-thesis. Each is run independently
# and the results are deduped, so overlap between angles is fine.
_LLM_ANGLES = [
    "small / micro VC funds (well under $50M) in the US that invest in consumer and B2C startups at pre-seed and seed",
    "US marketplace-focused venture funds that write early checks (consumer or B2B marketplaces, network-effects theses)",
    "US solo-GP and emerging-manager (Fund I or Fund II) funds with a consumer or direct-to-consumer focus",
    "US pre-seed funds known for consumer brands, creator economy, social, or community products",
    "US female-founded or diverse-led micro VC funds investing in consumer products",
    "US seed funds that specifically call out marketplaces, two-sided networks, or commerce in their thesis",
    "US micro VC funds focused on the creator economy, social apps, or community products",
    "US seed funds focused on consumer health, wellness, fitness, or food and beverage startups",
    "US early-stage funds focused on commerce, retail, DTC brands, or consumer packaged goods",
    "US consumer fintech and consumer subscription focused seed and pre-seed funds",
    "New York City based small consumer and marketplace focused venture funds",
    "Los Angeles based consumer, media, and entertainment focused early-stage venture funds",
    "San Francisco Bay Area micro VC funds investing in consumer and social startups",
    "US small venture funds focused on consumer gaming, sports, or interactive entertainment",
    "US emerging manager funds (under $50M) that lead pre-seed rounds in consumer startups",
]

_LISTICLE_QUERIES = [
    "list of consumer focused micro VC funds in the US",
    "best pre-seed consumer venture capital funds",
    "marketplace focused venture capital funds list",
    "emerging manager consumer seed funds",
    "solo GP consumer venture fund list",
    "top early stage consumer VC firms United States",
    "small consumer venture funds investing pre-seed",
    "creator economy venture capital funds list",
    "consumer brand CPG focused seed funds list",
    "best micro VC funds consumer social apps",
    "female founded consumer venture funds list",
    "new york consumer seed funds list",
    "los angeles consumer media venture funds",
]

_NAME_NOISE = re.compile(r"[^a-z0-9 ]+")


def _norm(name: str) -> str:
    n = _NAME_NOISE.sub("", (name or "").lower()).strip()
    n = re.sub(r"^the\s+", "", n)  # "The Venture Reality Fund" == "Venture Reality Fund"
    n = re.sub(r"\s+(ventures|ventura|capital|partners|vc|fund|funds|management|group)$", "", n)
    return re.sub(r"\s+", " ", n).strip()


def llm_candidates() -> list[dict]:
    if not llm.available():
        return []
    out = []
    sys = (
        "You are a venture-capital research assistant. You only return REAL funds "
        "that actually exist. Never invent names. If unsure a fund is real, omit it."
    )
    for angle in _LLM_ANGLES:
        prompt = (
            f"List up to 35 {angle}. "
            "Return JSON: {\"funds\": [{\"firm\": str, \"website\": str (domain or empty), "
            "\"hint\": str (one short phrase on their focus)}]}. "
            "US-based only. Prefer smaller / emerging funds over megafunds."
        )
        data = llm.chat_json(sys, prompt, model=llm.big_model(), temperature=0.5)
        for f in data.get("funds", []) or []:
            firm = (f.get("firm") or "").strip()
            if not firm:
                continue
            dom = (f.get("website") or "").strip().replace("https://", "").replace("http://", "").strip("/")
            out.append(
                {
                    "firm": firm,
                    "website": f"https://{dom}" if dom else "",
                    "hint": (f.get("hint") or "").strip(),
                    "source": "llm",
                }
            )
    return out


def listicle_candidates(max_pages: int = 18) -> list[dict]:
    if not (search.have_search() and llm.available()):
        return []
    # Gather candidate article URLs.
    urls: list[str] = []
    seen_url = set()
    for q in _LISTICLE_QUERIES:
        for r in search.web_search(q, num=8):
            link = r.get("link", "")
            if link and link not in seen_url and "linkedin.com" not in link:
                seen_url.add(link)
                urls.append(link)
    urls = urls[:max_pages]

    out = []
    sys = "Extract venture fund names from the article text. Do not invent any."
    for url in urls:
        html = web.fetch(url)
        if not html:
            continue
        text = web.to_text(html, limit=9000)
        if "venture" not in text.lower() and "vc" not in text.lower():
            continue
        data = llm.chat_json(
            sys,
            "From this article, list every US venture fund / VC firm name mentioned "
            "that invests in consumer or marketplace startups. "
            "Return JSON {\"funds\": [{\"firm\": str, \"hint\": str}]}.\n\n" + text,
        )
        for f in data.get("funds", []) or []:
            firm = (f.get("firm") or "").strip()
            if firm:
                out.append(
                    {"firm": firm, "website": "", "hint": (f.get("hint") or "").strip(), "source": "listicle"}
                )
    return out


def discover(use_llm: bool = True, use_listicles: bool = True) -> list[dict]:
    pool: list[dict] = list(seeds.seed_names())
    if use_llm:
        pool += llm_candidates()
    if use_listicles:
        pool += listicle_candidates()

    # Dedupe by normalized firm name; prefer the entry that already has a website.
    by_key: dict[str, dict] = {}
    for c in pool:
        key = _norm(c["firm"])
        if not key:
            continue
        if key not in by_key:
            by_key[key] = c
        else:
            if not by_key[key].get("website") and c.get("website"):
                by_key[key]["website"] = c["website"]
    return list(by_key.values())
