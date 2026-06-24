"""Shared HTTP helpers: a pooled session and a small retry/backoff wrapper."""

from __future__ import annotations

import time
import random
import requests

_SESSION = requests.Session()
# A realistic browser UA; many fund sites block unknown agents.
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }
)


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    timeout: int = 25,
    max_retries: int = 3,
    retry_statuses: tuple = (429, 500, 502, 503, 504),
) -> requests.Response:
    """Single request with exponential backoff on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = _SESSION.request(
                method, url, headers=headers, params=params, json=json, timeout=timeout
            )
            if resp.status_code in retry_statuses and attempt < max_retries:
                wait = _backoff(attempt, resp)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                raise HttpError(resp.status_code, resp.text)
            return resp
        except (requests.RequestException, HttpError) as exc:
            last_exc = exc
            if isinstance(exc, HttpError) and exc.status not in retry_statuses:
                raise
            if attempt >= max_retries:
                break
            time.sleep(_backoff(attempt, None))
    assert last_exc is not None
    raise last_exc


def _backoff(attempt: int, resp: requests.Response | None) -> float:
    if resp is not None:
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                return min(float(ra), 30.0)
            except ValueError:
                pass
    return min((2 ** attempt) + random.uniform(0, 0.75), 30.0)
