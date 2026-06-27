"""
Central config + secret loading.

Loads environment variables from the process environment first, then this
repo's own `.env`. As a local convenience it will ALSO fall back to reading a
sibling `../thescraper/.env` for any key it doesn't already have, so if you keep
related tools side by side you don't have to duplicate provider keys. That
fallback is a no-op on any machine without that sibling checkout, so it is
harmless to leave in place.

No secret values are ever printed or committed (.env is gitignored).
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Settings this tool may use. Pulled from the process env or the repo .env,
# falling back to a sibling thescraper/.env for local runs. Most are provider
# secrets; the COMPANY_* and SEC_CONTACT_EMAIL entries are plain config used to
# tailor outreach text and the SEC request header.
KNOWN_KEYS = [
    "SERPER_API_KEY",
    "PILOTERR_API_KEY",
    "CORESIGNAL_API_KEY",
    "ENRICHLAYER_API_KEY",
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "NOTION_TOKEN",
    "COMPANY_NAME",
    "COMPANY_PITCH",
    "SEC_CONTACT_EMAIL",
]


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _load() -> dict[str, str]:
    merged: dict[str, str] = {}

    # 1. Process env (highest priority).
    for k in KNOWN_KEYS:
        if os.environ.get(k):
            merged[k] = os.environ[k]

    # 2. This repo's .env.
    for k, v in _parse_env_file(REPO_ROOT / ".env").items():
        merged.setdefault(k, v)

    # 3. Local convenience fallback: sibling thescraper/.env.
    sibling = REPO_ROOT.parent / "thescraper" / ".env"
    for k, v in _parse_env_file(sibling).items():
        if k in KNOWN_KEYS:
            merged.setdefault(k, v)

    return merged


_ENV = _load()


def get(key: str, default: str | None = None) -> str | None:
    return _ENV.get(key) or default


def require(key: str) -> str:
    val = get(key)
    if not val:
        raise RuntimeError(
            f"Missing required key {key}. Add it to {REPO_ROOT / '.env'} "
            f"(copy .env.example) or export it."
        )
    return val


def have(key: str) -> bool:
    return bool(get(key))


# Provider secrets only, for the status readout (excludes plain COMPANY_*/SEC config).
_PROVIDER_KEYS = [k for k in KNOWN_KEYS if k.endswith(("_API_KEY", "_TOKEN"))]


def status() -> dict[str, bool]:
    """Which providers are configured (booleans only, never values)."""
    return {k: have(k) for k in _PROVIDER_KEYS}
