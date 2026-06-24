"""
Google search via Serper (primary) and Piloterr (fallback).

Exposes one function, `web_search(query)`, returning a normalized list of
organic results: [{title, link, snippet}]. Used for firm discovery, finding
team pages, and resolving people to LinkedIn URLs.
"""

from __future__ import annotations

import config
from . import http

_SERPER_URL = "https://google.serper.dev/search"
_PILOTERR_URL = "https://piloterr.com/api/v2/google/search"


def _serper(query: str, num: int, gl: str, hl: str) -> list[dict]:
    key = config.get("SERPER_API_KEY")
    if not key:
        return []
    resp = http.request(
        "POST",
        _SERPER_URL,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": num, "gl": gl, "hl": hl},
    )
    data = resp.json()
    out = []
    for r in data.get("organic", []) or []:
        out.append(
            {
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
            }
        )
    return out


def _piloterr(query: str, num: int, gl: str, hl: str) -> list[dict]:
    key = config.get("PILOTERR_API_KEY")
    if not key:
        return []
    resp = http.request(
        "POST",
        _PILOTERR_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={"query": query, "num": num, "page": 1, "gl": gl, "hl": hl},
    )
    data = resp.json()
    rows = data.get("organic_results") or data.get("results") or []
    out = []
    for r in rows:
        out.append(
            {
                "title": r.get("title", ""),
                "link": r.get("link") or r.get("url", ""),
                "snippet": r.get("snippet", ""),
            }
        )
    return out


def web_search(query: str, num: int = 10, gl: str = "us", hl: str = "en") -> list[dict]:
    """Run a Google search and return normalized organic results.

    Tries Serper first; falls back to Piloterr if Serper is unset or errors.
    Never raises on a single failed query (returns [] so the pipeline survives).
    """
    try:
        res = _serper(query, num, gl, hl)
        if res:
            return res
    except Exception:
        pass
    try:
        return _piloterr(query, num, gl, hl)
    except Exception:
        return []


def have_search() -> bool:
    return config.have("SERPER_API_KEY") or config.have("PILOTERR_API_KEY")
