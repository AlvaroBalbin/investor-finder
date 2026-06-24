"""
Hard exclusion list of well-known large / mega venture firms. These are
unambiguously far above the small-fund ceiling, and LLM size estimates for
famous names are unreliable (it once guessed Greylock at $3,500), so we drop
them by name regardless of the estimate.

Matching is on a normalized firm name so "Greylock", "Greylock Partners", and
"greylock ventures" all hit.
"""

from __future__ import annotations

import re

_NOISE = re.compile(r"[^a-z0-9 ]+")


def _norm(name: str) -> str:
    n = _NOISE.sub("", (name or "").lower())
    n = re.sub(r"\s+(ventures|capital|partners|vc|fund|funds|management|group|associates)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


# Household-name funds that are clearly well above a small / micro size.
_MEGA = {
    "sequoia", "andreessen horowitz", "a16z", "accel", "greylock", "benchmark",
    "kleiner perkins", "lightspeed", "bessemer", "nea", "new enterprise",
    "general catalyst", "index", "ggv", "insight", "tiger global", "coatue",
    "founders", "khosla", "thrive", "ivp", "battery", "redpoint", "menlo",
    "norwest", "spark", "crv", "charles river", "first round", "initialized",
    "craft", "8vc", "lux", "dcvc", "social", "gv", "google", "sapphire",
    "emergence", "scale venture", "mayfield", "canaan", "shasta", "foundation",
    "tcv", "ribbit", "qed", "foundry", "union square", "usv", "felicis",
    "uncork", "homebrew", "floodgate", "bain", "bond", "dst", "sequoia heritage",
    "forerunner", "maveron", "lerer hippeau", "collaborative", "nfx", "fj labs",
    "slow", "lowercarbon", "obvious", "haystack", "village global", "susa",
    "cowboy", "matrix", "trinity", "sierra", "norwest", "m13", "signalfire",
}


def is_excluded(firm: str) -> bool:
    # Exact match on the normalized name only. Normalization already strips the
    # "Partners / Ventures / Capital" suffix, so "Greylock", "Greylock Partners"
    # and "Greylock Capital" all collapse to "greylock". Exact-only avoids
    # false-excluding small funds that merely share a first word.
    n = _norm(firm)
    return bool(n) and n in _MEGA
