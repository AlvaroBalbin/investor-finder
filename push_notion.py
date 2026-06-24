"""
Push the fund-level rows (data/_notion_funds.json) into an existing Notion
database via the REST API. One-off delivery helper.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import config
from providers import http

VER = "2022-06-28"


def _text(v):
    v = str(v or "")[:1990]
    return {"rich_text": [{"text": {"content": v}}]} if v else {"rich_text": []}


def _select(v, allowed, default=None):
    v = (str(v or "").strip().lower()) or (default or "")
    if v in allowed:
        return {"select": {"name": v}}
    return None


def _url(v):
    v = str(v or "").strip()
    if v.startswith("http"):
        return {"url": v}
    return {"url": None}


def _email(v):
    v = str(v or "").strip()
    return {"email": v} if "@" in v else {"email": None}


def build_props(d: dict) -> dict:
    props = {
        "Fund": {"title": [{"text": {"content": (d.get("firm") or "(unknown)")[:200]}}]},
        "Website": _url(d.get("website")),
        "HQ": _text(d.get("hq_location")),
        "Stage": _text(d.get("stage")),
        "Check size": _text(d.get("check_size")),
        "Est fund size": _text(d.get("fund_size_display")),
        "Over $20M by": _text(d.get("over_20m_text")),
        "Fund size source": _text(d.get("fund_size_source")),
        "# Founders": {"number": d.get("num_founders", 0)},
        "Thesis": _text(d.get("thesis")),
        "Sectors": _text(d.get("sectors")),
        "Founders (role | linkedin | email)": _text(d.get("founders_text")),
        "Source": _text(d.get("discovery_source")),
        "Fit (SocialGravity)": _text(d.get("fit_sg")),
        "Priority": {"number": d.get("priority", 0)},
    }
    sf = _select(d.get("sf_area"), {"yes", "no"})
    if sf:
        props["SF area"] = sf
    ps = _select(d.get("pre_seed"), {"yes", "no"}, default="no")
    if ps:
        props["Pre-seed"] = ps
    s20 = _select(d.get("sub_20m"), {"yes", "no", "unknown"}, default="unknown")
    if s20:
        props["Sub $20M"] = s20
    cons = _select(d.get("is_consumer"), {"yes", "no"}, default="no")
    if cons:
        props["Consumer"] = cons
    mkt = _select(d.get("is_marketplace"), {"yes", "no"}, default="no")
    if mkt:
        props["Marketplace"] = mkt
    em = _email(d.get("primary_email"))
    if em["email"]:
        props["Primary email"] = em
    return props


def _archive_all(db: str, headers: dict) -> int:
    """Archive every existing row in the database (for a clean re-push)."""
    ids, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        d = http.request(
            "POST", f"https://api.notion.com/v1/databases/{db}/query", headers=headers, json=body
        ).json()
        ids += [p["id"] for p in d.get("results", [])]
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    for pid in ids:
        try:
            http.request(
                "PATCH",
                f"https://api.notion.com/v1/pages/{pid}",
                headers=headers,
                json={"archived": True},
                max_retries=3,
            )
        except Exception:
            pass
    return len(ids)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Notion database id")
    ap.add_argument("--rows", default="data/_notion_funds.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--replace", action="store_true", help="archive existing rows first")
    args = ap.parse_args()

    tok = config.require("NOTION_TOKEN")
    headers = {"Authorization": f"Bearer {tok}", "Notion-Version": VER, "Content-Type": "application/json"}
    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if args.replace:
        n = _archive_all(args.db, headers)
        print(f"archived {n} existing rows")
    print(f"pushing {len(rows)} funds to db {args.db}...")

    ok = {"n": 0}

    def push(d: dict):
        try:
            http.request(
                "POST",
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={"parent": {"database_id": args.db}, "properties": build_props(d)},
                max_retries=4,
            )
            ok["n"] += 1
        except Exception as e:
            print("  FAIL", d.get("firm"), str(e)[:120])

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(push, rows))
    print(f"done: {ok['n']}/{len(rows)} pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
