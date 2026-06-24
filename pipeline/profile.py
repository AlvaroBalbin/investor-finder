"""
Per-firm verification + profiling.

For one candidate fund we:
  1. resolve its website (if discovery didn't already give one) via search
  2. fetch the homepage + likely team/about/portfolio/contact pages
  3. pull extra web evidence (search snippets) for fund-size + partner signals
  4. ask the LLM to return ONE structured record: is this a real US VC, its
     thesis / sectors / stage / check size, an estimated fund size with a
     confidence, whether it is consumer/B2C and marketplace, and its partners
     (with any LinkedIn / email visible directly on the site).

A firm that the LLM judges not-a-real-VC, or not-US, is dropped before output,
so hallucinated or off-thesis candidates never reach the list.
"""

from __future__ import annotations

from urllib.parse import urlparse

from providers import llm, search, web

# Domains that are directories/socials, not a fund's own site.
_NOT_A_FUND_SITE = (
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "crunchbase.com", "pitchbook.com", "openvc.app", "signal.nfx.com",
    "wikipedia.org", "medium.com", "youtube.com", "bloomberg.com",
    "forbes.com", "techcrunch.com", "wellfound.com", "angel.co",
)

_TEAM_HINTS = ("team", "about", "people", "partners", "who-we-are", "portfolio", "contact")


def resolve_website(firm: str) -> str:
    for r in search.web_search(f"{firm} venture capital fund", num=8):
        link = r.get("link", "")
        host = urlparse(link).netloc.lower()
        if not host:
            continue
        if any(bad in host for bad in _NOT_A_FUND_SITE):
            continue
        # Use the site root.
        return f"{urlparse(link).scheme}://{host}"
    return ""


def _gather_site_text(website: str) -> tuple[str, list[str]]:
    """Return (combined_text, list_of_emails_seen) from home + sub pages."""
    if not website:
        return "", []
    home = web.fetch(website)
    if not home:
        return "", []
    texts = [web.to_text(home, limit=6000)]
    emails = set(web.emails_in(home))

    # Pick a few promising internal pages.
    subs = []
    for link in web.internal_links(home, website):
        low = link.lower()
        if any(h in low for h in _TEAM_HINTS) and link != website:
            subs.append(link)
    # De-dup and cap.
    picked = []
    seen = set()
    for s in subs:
        if s not in seen:
            seen.add(s)
            picked.append(s)
        if len(picked) >= 3:
            break

    for s in picked:
        html = web.fetch(s)
        if html:
            texts.append(web.to_text(html, limit=5000))
            emails.update(web.emails_in(html))

    return "\n\n".join(texts)[:16000], sorted(emails)


def _evidence_snippets(firm: str) -> str:
    bits = []
    for q in (f"{firm} fund size AUM assets under management", f"{firm} partners team founders"):
        for r in search.web_search(q, num=5):
            sn = r.get("snippet", "")
            if sn:
                bits.append(f"- {r.get('title','')}: {sn}")
    return "\n".join(bits[:12])


_SYS = (
    "You are a meticulous VC-data analyst. You only state what the evidence supports. "
    "If something is unknown, say so rather than guessing. Never invent partners or emails."
)


def profile_firm(candidate: dict) -> dict | None:
    firm = candidate["firm"]
    website = candidate.get("website") or resolve_website(firm)
    site_text, site_emails = _gather_site_text(website)

    # If the seeded/guessed domain didn't resolve, search for the real one.
    if not site_text:
        alt = resolve_website(firm)
        if alt and alt != website:
            website = alt
            site_text, site_emails = _gather_site_text(website)

    evidence = _evidence_snippets(firm)

    if not site_text and not evidence:
        return None  # nothing to verify against; drop quietly

    prompt = f"""Firm name: {firm}
Website: {website or 'unknown'}
Site emails seen: {', '.join(site_emails) or 'none'}

--- WEBSITE TEXT ---
{site_text or '(none)'}

--- WEB SEARCH EVIDENCE ---
{evidence or '(none)'}

Return a JSON object describing this firm as an investor:
{{
  "is_real_vc": bool,                       // an actual venture/angel fund, not a company/agency/directory
  "is_us": bool,                            // headquartered in the United States
  "hq_location": str,                       // city, state if known else ""
  "thesis": str,                            // one sentence
  "sectors": [str],
  "stage": [str],                           // check stages, e.g. ["pre-seed","seed"].
      // A small / emerging / Fund I or solo-GP fund almost always writes
      // pre-seed and seed checks, so include "pre-seed" unless the evidence
      // clearly shows they only come in at Series A or later.
  "check_size": str,                        // e.g. "$50k-$250k" or ""
  "size_bucket": "micro"|"small"|"mid"|"large"|"mega"|"unknown",
      // micro = under $20M total fund, small = $20M-$50M, mid = $50M-$200M,
      // large = $200M-$1B, mega = $1B+. Judge from team size, fund number
      // (Fund I/II is usually small), check size, and any public figure.
      // Famous multi-stage firms (Sequoia, a16z, Greylock, Accel, Lightspeed,
      // Bessemer, General Catalyst, etc.) are mega/large, never micro.
  "est_fund_size_usd": number|null,         // best estimate of total fund AUM in USD
  "fund_size_basis": str,                   // one phrase: what the estimate is based on
  "size_confidence": "low"|"medium"|"high",
  "is_consumer": bool,                      // invests in consumer / B2C / DTC
  "consumer_confidence": "low"|"medium"|"high",
  "is_marketplace": bool,                   // explicitly invests in marketplaces / two-sided networks
  "partners": [                             // founders / GPs / partners ONLY, max 6
    {{"name": str, "role": str, "linkedin": str, "email": str}}
  ]
}}
Only include partners you can actually find in the text. linkedin/email = "" if not visible."""

    data = llm.chat_json(_SYS, prompt, temperature=0.1)
    if not data or not data.get("is_real_vc"):
        return None

    data["firm"] = firm
    data["website"] = website
    data["discovery_source"] = candidate.get("source", "")
    data["_site_emails"] = site_emails
    data["_email_domain"] = web.domain_of(website) if website else ""
    return data
