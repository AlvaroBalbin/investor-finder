"""
Output writers: a founder-level CSV (one row per founder/partner) and an
optional Notion database (via the Notion REST API, so the repo stays
self-contained for open-sourcing).
"""

from __future__ import annotations

import csv
from pathlib import Path

import config
from providers import http

# Column order for the CSV / table.
COLUMNS = [
    "firm",
    "website",
    "hq_location",
    "thesis",
    "sectors",
    "stage",
    "check_size",
    "pre_seed",
    "est_fund_size_usd",
    "sub_20m",
    "size_confidence",
    "fund_size_basis",
    "is_consumer",
    "consumer_confidence",
    "is_marketplace",
    "founder_name",
    "founder_role",
    "founder_linkedin",
    "linkedin_source",
    "founder_email",
    "email_source",
    "email_confidence",
    "discovery_source",
]


def _stage_text(stage) -> str:
    if isinstance(stage, list):
        return " ".join(str(s) for s in stage).lower()
    return str(stage or "").lower()


def stage_has_preseed(stage) -> bool:
    t = _stage_text(stage)
    return any(k in t for k in ("pre-seed", "pre seed", "preseed"))


def stage_is_early(stage) -> bool:
    """True if the fund invests at pre-seed or seed (or stage is unknown)."""
    t = _stage_text(stage)
    if not t.strip():
        return True  # unknown: do not exclude on stage alone
    if stage_has_preseed(stage) or "seed" in t or "angel" in t:
        return True
    # Stage is stated but only late-stage markers -> not early.
    return False


def rows_from_records(records: list[dict]) -> list[dict]:
    """Flatten firm records into founder-level rows."""
    rows = []
    for rec in records:
        est = rec.get("est_fund_size_usd")
        sub_20m = ""
        if isinstance(est, (int, float)):
            sub_20m = "yes" if est < 20_000_000 else "no"
        pre_seed = "yes" if stage_has_preseed(rec.get("stage", [])) else ""
        base = {
            "firm": rec.get("firm", ""),
            "website": rec.get("website", ""),
            "hq_location": rec.get("hq_location", ""),
            "thesis": rec.get("thesis", ""),
            "sectors": ", ".join(rec.get("sectors", []) or []),
            "stage": ", ".join(rec.get("stage", []) or []),
            "check_size": rec.get("check_size", ""),
            "pre_seed": pre_seed,
            "est_fund_size_usd": est if est is not None else "",
            "sub_20m": sub_20m,
            "size_confidence": rec.get("size_confidence", ""),
            "fund_size_basis": rec.get("fund_size_basis", ""),
            "is_consumer": _yn(rec.get("is_consumer")),
            "consumer_confidence": rec.get("consumer_confidence", ""),
            "is_marketplace": _yn(rec.get("is_marketplace")),
            "discovery_source": rec.get("discovery_source", ""),
        }
        contacts = rec.get("contacts") or []
        if not contacts:
            rows.append({**base, **_empty_contact()})
            continue
        for c in contacts:
            rows.append({**base, **c})
    return rows


def _yn(v) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return ""


def _empty_contact() -> dict:
    return {
        "founder_name": "",
        "founder_role": "",
        "founder_linkedin": "",
        "linkedin_source": "",
        "founder_email": "",
        "email_source": "",
        "email_confidence": "",
    }


def write_csv(rows: list[dict], path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    return str(p)


# --- Notion (optional) ---------------------------------------------------

_NOTION_VER = "2022-06-28"


def push_to_notion(rows: list[dict], title: str) -> str | None:
    token = config.get("NOTION_TOKEN")
    parent = config.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VER,
        "Content-Type": "application/json",
    }
    # Create a database with text properties (simple + robust).
    props = {c: {"rich_text": {}} for c in COLUMNS if c != "firm"}
    props["firm"] = {"title": {}}
    db = http.request(
        "POST",
        "https://api.notion.com/v1/databases",
        headers=headers,
        json={
            "parent": {"type": "page_id", "page_id": parent},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": props,
        },
    ).json()
    db_id = db.get("id")
    if not db_id:
        return None
    for r in rows:
        page_props = {}
        for c in COLUMNS:
            val = str(r.get(c, "") or "")[:1900]
            if c == "firm":
                page_props[c] = {"title": [{"text": {"content": val or "(unknown)"}}]}
            else:
                page_props[c] = {"rich_text": [{"text": {"content": val}}]} if val else {"rich_text": []}
        try:
            http.request(
                "POST",
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={"parent": {"database_id": db_id}, "properties": page_props},
                max_retries=2,
            )
        except Exception:
            continue
    return db.get("url") or db_id
