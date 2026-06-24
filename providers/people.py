"""
Person enrichment via Coresignal and EnrichLayer (Proxycurl-compatible).

Used to (a) confirm a LinkedIn profile belongs to the right person at the
right firm and (b) best-effort fetch a contact email. Email endpoints cost
credits and are not guaranteed, so they are opt-in and fail soft.
"""

from __future__ import annotations

import re

import config
from . import http

_CORESIGNAL_BASE = "https://api.coresignal.com/cdapi/v2"
_ENRICHLAYER_BASE = "https://enrichlayer.com/api/v2"

_SLUG_RE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)


def linkedin_slug(url: str) -> str | None:
    m = _SLUG_RE.search(url or "")
    return m.group(1) if m else None


def coresignal_profile(linkedin_url: str) -> dict | None:
    key = config.get("CORESIGNAL_API_KEY")
    slug = linkedin_slug(linkedin_url)
    if not key or not slug:
        return None
    try:
        resp = http.request(
            "GET",
            f"{_CORESIGNAL_BASE}/employee_clean/collect/{slug}",
            headers={"apikey": key},
            max_retries=1,
        )
        return resp.json()
    except Exception:
        return None


def enrichlayer_profile(linkedin_url: str) -> dict | None:
    key = config.get("ENRICHLAYER_API_KEY")
    if not key or not linkedin_url:
        return None
    try:
        resp = http.request(
            "GET",
            f"{_ENRICHLAYER_BASE}/profile",
            headers={"Authorization": f"Bearer {key}"},
            params={"url": linkedin_url, "use_cache": "if-present"},
            max_retries=1,
        )
        return resp.json()
    except Exception:
        return None


def _normalize(profile: dict) -> dict:
    """Pull the few fields we care about out of either provider's shape."""
    if not profile:
        return {}
    name = (
        profile.get("full_name")
        or profile.get("name")
        or " ".join(
            [profile.get("first_name", ""), profile.get("last_name", "")]
        ).strip()
    )
    headline = (
        profile.get("headline")
        or profile.get("occupation")
        or profile.get("generated_headline")
        or profile.get("job_title")
        or ""
    )
    exps = profile.get("experiences") or profile.get("experience") or []
    current_company = ""
    if exps:
        e0 = exps[0]
        current_company = e0.get("company") or e0.get("company_name") or ""
    return {
        "name": name,
        "headline": headline,
        "current_company": current_company,
    }


def confirm_person(linkedin_url: str) -> dict:
    """Return normalized {name, headline, current_company} using whichever
    enrichment provider answers first. {} if none."""
    prof = enrichlayer_profile(linkedin_url) or coresignal_profile(linkedin_url)
    return _normalize(prof or {})


# Email lookup. EnrichLayer mirrors Proxycurl's contact endpoints; the exact
# path has changed across versions, so we try the known ones and stop at the
# first that returns an address. Fails soft (None) and is opt-in per call.
_EMAIL_ENDPOINTS = [
    ("GET", "/profile/email", "url"),
    ("GET", "/contact-api/personal-email", "linkedin_profile_url"),
    ("GET", "/linkedin/profile/email", "linkedin_profile_url"),
]


def enrichlayer_email(linkedin_url: str) -> str | None:
    key = config.get("ENRICHLAYER_API_KEY")
    if not key or not linkedin_url:
        return None
    for method, path, param in _EMAIL_ENDPOINTS:
        try:
            resp = http.request(
                method,
                f"{_ENRICHLAYER_BASE}{path}",
                headers={"Authorization": f"Bearer {key}"},
                params={param: linkedin_url, "page_size": 1},
                max_retries=0,
                timeout=30,
            )
            data = resp.json()
            email = _extract_email(data)
            if email:
                return email
        except Exception:
            continue
    return None


def _extract_email(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("email", "work_email", "personal_email"):
        v = data.get(key)
        if isinstance(v, str) and "@" in v:
            return v.lower()
    for key in ("emails", "personal_emails", "work_emails"):
        v = data.get(key)
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str) and "@" in first:
                return first.lower()
            if isinstance(first, dict):
                addr = first.get("email") or first.get("address")
                if isinstance(addr, str) and "@" in addr:
                    return addr.lower()
    return None
