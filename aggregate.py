"""
Aggregate the founder-level CSV into fund-level rows for the Notion table
(data/_notion_funds.json). One row per fund, founders collapsed into a single
field, with readable fund-size formatting.

  python aggregate.py
  python aggregate.py --csv data/us_consumer_vc_funds.csv
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

_SF = re.compile(
    r"san francisco|bay area|palo alto|menlo park|mountain view|oakland|berkeley|"
    r"san mateo|redwood city|sunnyvale|santa clara|san jose|burlingame|los altos|"
    r"foster city|emeryville|cupertino",
    re.I,
)


def _priority(d: dict, sf: bool) -> int:
    """Higher = better fit: sub-$20M + pre-seed + consumer + marketplace + SF +
    real (SEC) size + more contacts."""
    s = 0
    if d.get("sub_20m") == "yes":
        s += 1000
    elif d.get("sub_20m") == "no":
        s += 300  # 20-50M, still kept
    if d.get("pre_seed") == "yes":
        s += 400
    if d.get("is_consumer") == "yes":
        s += 200
    if d.get("is_marketplace") == "yes":
        s += 150
    if sf:
        s += 120
    if str(d.get("fund_size_source", "")).startswith("SEC"):
        s += 60
    s += min(d.get("num_founders", 0), 6) * 10
    return s


def _money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n >= 1_000_000:
        s = f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"${s}M"
    return f"${round(n / 1000)}k"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/us_consumer_vc_funds.csv")
    ap.add_argument("--out", default="data/_notion_funds.json")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    funds: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
    keep = [
        "firm", "website", "hq_location", "thesis", "sectors", "stage",
        "check_size", "pre_seed", "est_fund_size_usd", "sub_20m", "over_20m_usd",
        "size_confidence", "fund_size_source", "is_consumer", "is_marketplace",
        "discovery_source",
    ]
    for r in rows:
        f = r["firm"]
        if f not in funds:
            funds[f] = {k: r.get(k, "") for k in keep}
            funds[f]["founders"] = []
        if r.get("founder_name"):
            funds[f]["founders"].append(r)

    out = []
    for d in funds.values():
        fl = d.pop("founders")
        lines, primary = [], ""
        for c in fl:
            seg = c["founder_name"]
            if c.get("founder_role"):
                seg += f" ({c['founder_role']})"
            if c.get("founder_linkedin"):
                seg += f" | {c['founder_linkedin']}"
            if c.get("founder_email"):
                seg += f" | {c['founder_email']}"
            lines.append(seg)
            if not primary and c.get("founder_email") and c.get("email_confidence") in ("high", "medium"):
                primary = c["founder_email"]
        if not primary and fl:
            primary = fl[0].get("founder_email", "")
        d["founders_text"] = "\n".join(lines)
        d["num_founders"] = len(fl)
        d["primary_email"] = primary
        d["fund_size_display"] = _money(d.get("est_fund_size_usd"))
        over = _money(d.get("over_20m_usd"))
        d["over_20m_text"] = f"{over} over" if over else ""
        if not d.get("fund_size_source") and d.get("fund_size_display"):
            d["fund_size_source"] = "estimate"
        sf = bool(_SF.search(d.get("hq_location") or ""))
        d["sf_area"] = "yes" if sf else "no"
        d["priority"] = _priority(d, sf)
        out.append(d)

    out.sort(key=lambda x: x["priority"], reverse=True)

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_sec = sum(1 for d in out if str(d.get("fund_size_source", "")).startswith("SEC"))
    n_sub20 = sum(1 for d in out if d.get("sub_20m") == "yes")
    print(f"aggregated {len(out)} funds | SEC-sourced size: {n_sec} | sub-$20M: {n_sub20}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
