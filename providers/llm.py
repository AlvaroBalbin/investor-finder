"""
LLM access for candidate generation, classification, and extraction.

OpenAI is primary; Grok (xAI) is used if no OpenAI key is present. Both speak
the OpenAI chat-completions shape. `chat_json` forces and parses a JSON object.
"""

from __future__ import annotations

import json

import config
from . import http

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_XAI_URL = "https://api.x.ai/v1/chat/completions"


def _provider() -> tuple[str, str, str] | None:
    """Return (url, api_key, default_model) for the available provider."""
    if config.have("OPENAI_API_KEY"):
        return _OPENAI_URL, config.get("OPENAI_API_KEY"), "gpt-4o-mini"
    if config.have("XAI_API_KEY"):
        return _XAI_URL, config.get("XAI_API_KEY"), "grok-2-latest"
    return None


def available() -> bool:
    return _provider() is not None


def chat_json(system: str, user: str, model: str | None = None, temperature: float = 0.2) -> dict:
    """Call the LLM and return a parsed JSON object. Returns {} on failure."""
    prov = _provider()
    if prov is None:
        return {}
    url, key, default_model = prov
    body = {
        "model": model or default_model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = http.request(
            "POST",
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return {}


# The "big" model for harder generation (recall of fund names). Falls back
# gracefully to whatever default the provider has.
def big_model() -> str:
    prov = _provider()
    if prov and prov[0] == _OPENAI_URL:
        return "gpt-4o"
    return "grok-2-latest"
