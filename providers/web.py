"""
Fetch a web page and pull out readable text + any emails.

Used to read a fund's website (home / team / about / contact) so the LLM can
extract thesis, sectors, fund-size signals, and partner names, and so we can
harvest published emails directly.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import http

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# Junk emails we never want to treat as a contact.
_EMAIL_JUNK = ("example.com", "sentry", "wixpress", "godaddy", ".png", ".jpg", "@2x")


def fetch(url: str, timeout: int = 20) -> str | None:
    """Return raw HTML for a URL, or None on failure."""
    try:
        resp = http.request("GET", url, timeout=timeout, max_retries=1)
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return None
        return resp.text
    except Exception:
        return None


def to_text(html: str, limit: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return text[:limit]


def emails_in(html: str) -> list[str]:
    found = set()
    # mailto links are the most reliable.
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select('a[href^="mailto:"]'):
        addr = a.get("href", "")[7:].split("?")[0].strip()
        if addr:
            found.add(addr.lower())
    for m in _EMAIL_RE.findall(html):
        found.add(m.lower())
    return [e for e in found if not any(j in e for j in _EMAIL_JUNK)]


def internal_links(html: str, base_url: str) -> list[str]:
    """Same-domain links, used to find team/about/contact pages."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower().replace("www.", "")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        host = urlparse(full).netloc.lower().replace("www.", "")
        if host == base_host and full not in seen:
            seen.add(full)
            out.append(full)
    return out


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")
