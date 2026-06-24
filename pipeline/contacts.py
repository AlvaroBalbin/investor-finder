"""
Contact resolution per partner: a LinkedIn URL and a best-effort email, each
tagged with its source and a confidence so the founder can trust the high ones
and treat guesses as guesses.

Email strategy, in priority order:
  1. email published on the firm's own site (high)
  2. email derived from the firm's observed address pattern (medium)
  3. optional enrichment-API lookup (medium, opt-in, costs credits)
  4. single pattern guess from the firm domain (low, clearly flagged)

LinkedIn strategy:
  1. URL already visible on the site (high)
  2. resolved via Google search "name firm linkedin" (medium)
"""

from __future__ import annotations

import re

from providers import people, search

_GENERIC_LOCALS = {
    "info", "hello", "contact", "team", "hi", "admin", "press", "jobs",
    "careers", "support", "office", "general", "ir", "media", "deals",
    "pitch", "ventures", "invest", "partners",
}


def resolve_linkedin(name: str, firm: str, existing: str = "") -> tuple[str, str]:
    if existing and "linkedin.com/in/" in existing:
        return existing, "site"
    for r in search.web_search(f"{name} {firm} linkedin", num=6):
        link = r.get("link", "")
        if "linkedin.com/in/" in link:
            return link.split("?")[0], "search"
    return "", ""


def _name_parts(name: str) -> tuple[str, str]:
    toks = re.sub(r"[^a-zA-Z ]", "", name or "").lower().split()
    if not toks:
        return "", ""
    first = toks[0]
    last = toks[-1] if len(toks) > 1 else ""
    return first, last


def _patterns(first: str, last: str) -> dict[str, str]:
    out = {}
    if first:
        out["first"] = first
    if first and last:
        out["first.last"] = f"{first}.{last}"
        out["firstlast"] = f"{first}{last}"
        out["flast"] = f"{first[0]}{last}"
        out["first_last"] = f"{first}_{last}"
        out["firstl"] = f"{first}{last[0]}"
    return out


def infer_pattern(site_emails: list[str], partner_names: list[str]) -> str | None:
    """Learn the firm's local-part pattern from any personal email on the site."""
    for email in site_emails:
        local, _, _ = email.partition("@")
        if local in _GENERIC_LOCALS:
            continue
        for nm in partner_names:
            first, last = _name_parts(nm)
            for pat_name, candidate in _patterns(first, last).items():
                if candidate and candidate == local:
                    return pat_name
    return None


def guess_email(name: str, domain: str, pattern: str | None) -> tuple[str, str]:
    """Return (email, confidence). pattern=None falls back to first@domain."""
    if not domain:
        return "", ""
    first, last = _name_parts(name)
    pats = _patterns(first, last)
    if pattern and pattern in pats:
        return f"{pats[pattern]}@{domain}", "medium"
    if first and last:
        return f"{first}@{domain}", "low"
    if first:
        return f"{first}@{domain}", "low"
    return "", ""


def enrich_contact(
    partner: dict,
    firm_record: dict,
    learned_pattern: str | None,
    try_enrichment_email: bool = False,
) -> dict:
    name = (partner.get("name") or "").strip()
    role = (partner.get("role") or "").strip()
    firm = firm_record["firm"]
    domain = firm_record.get("_email_domain", "")

    linkedin, li_source = resolve_linkedin(name, firm, partner.get("linkedin", ""))

    # Email cascade.
    email, email_source, email_conf = "", "", ""
    site_email = (partner.get("email") or "").strip().lower()
    if site_email and "@" in site_email:
        email, email_source, email_conf = site_email, "site", "high"

    if not email:
        guessed, conf = guess_email(name, domain, learned_pattern)
        if guessed and conf == "medium":
            email, email_source, email_conf = guessed, "pattern_observed", "medium"

    if not email and try_enrichment_email and linkedin:
        enriched = people.enrichlayer_email(linkedin)
        if enriched:
            email, email_source, email_conf = enriched, "enrichment", "medium"

    if not email:
        guessed, conf = guess_email(name, domain, learned_pattern)
        if guessed:
            email, email_source, email_conf = guessed, "pattern_guess", conf or "low"

    return {
        "founder_name": name,
        "founder_role": role,
        "founder_linkedin": linkedin,
        "linkedin_source": li_source,
        "founder_email": email,
        "email_source": email_source,
        "email_confidence": email_conf,
    }
