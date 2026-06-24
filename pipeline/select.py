"""
Selection stage: from the full set of profiled firm records, filter to the
ones that fit the brief (US, consumer or marketplace, early-stage, small),
resolve founder contacts, rank, and write the output.

This is deliberately separate from profiling so the expensive web+LLM work can
be done once (and cached to JSON) while the cheap selection knobs are re-tuned
freely.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from pipeline import contacts, output
from pipeline.exclude import is_excluded
from pipeline.output import stage_has_preseed, stage_is_early

# Buckets we keep. "small" = $20-50M (allowed per the brief); "unknown" kept
# on benefit of the doubt and flagged.
KEEP_BUCKETS = {"micro", "small", "unknown", ""}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def passes_filter(rec: dict, size_ceiling: float) -> bool:
    if is_excluded(rec.get("firm", "")):
        return False
    if not rec.get("is_us"):
        return False
    # Consumer is the core requirement; a marketplace specialist also qualifies.
    if not (rec.get("is_consumer") or rec.get("is_marketplace")):
        return False
    # Early-stage only.
    if not stage_is_early(rec.get("stage", [])):
        return False
    # Size: keep micro / small / unknown buckets; drop mid / large / mega.
    bucket = (rec.get("size_bucket") or "").lower()
    if bucket and bucket not in KEEP_BUCKETS:
        return False
    # Backstop on a high-confidence explicit estimate when the bucket is missing.
    est = rec.get("est_fund_size_usd")
    conf = rec.get("size_confidence", "low")
    if bucket in ("", "unknown") and isinstance(est, (int, float)):
        if est > size_ceiling and conf == "high":
            return False
    return True


def rank_key(rec: dict):
    bucket = (rec.get("size_bucket") or "").lower()
    micro = bucket == "micro"
    pre_seed = stage_has_preseed(rec.get("stage", []))
    cons_high = rec.get("consumer_confidence") == "high"
    has_contact = any(
        c.get("founder_linkedin") or c.get("founder_email")
        for c in rec.get("contacts", [])
    )
    # Higher sorts first (caller reverses). Order matches the brief:
    # pre-seed, micro, consumer, consumer-confidence, marketplace, has-contact.
    return (
        1 if pre_seed else 0,
        1 if micro else 0,
        1 if rec.get("is_consumer") else 0,
        1 if cons_high else 0,
        1 if rec.get("is_marketplace") else 0,
        1 if has_contact else 0,
        len(rec.get("contacts", [])),
    )


def _resolve_one(rec: dict, enrichment_email: bool) -> dict:
    partners = rec.get("partners", []) or []
    site_emails = rec.get("_site_emails", [])
    pattern = contacts.infer_pattern(site_emails, [p.get("name", "") for p in partners])
    out = []
    for p in partners[:6]:
        if not (p.get("name") or "").strip():
            continue
        out.append(contacts.enrich_contact(p, rec, pattern, try_enrichment_email=enrichment_email))
    rec["contacts"] = out
    return rec


def select_and_output(
    records: list[dict],
    *,
    size_ceiling: float,
    out_path: str,
    workers: int = 10,
    enrichment_email: bool = False,
    notion: bool = False,
) -> tuple[str, list[dict], list[dict]]:
    kept = [r for r in records if passes_filter(r, size_ceiling)]
    _log(f"kept {len(kept)} of {len(records)} after US + consumer/marketplace + early + small filter")

    _log("resolving founder LinkedIn + email...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda r: _resolve_one(r, enrichment_email), kept))

    # A fund with no named founder/partner has no outreach value (and is often
    # an accelerator or corporate program rather than a fund), so drop it.
    before = len(kept)
    kept = [r for r in kept if any((c.get("founder_name") or "").strip() for c in r.get("contacts", []))]
    if before != len(kept):
        _log(f"dropped {before - len(kept)} funds with no named founders")

    kept.sort(key=rank_key, reverse=True)
    rows = output.rows_from_records(kept)
    path = output.write_csv(rows, out_path)

    n_funds = len(kept)
    n_founders = sum(1 for r in rows if r.get("founder_name"))
    n_email = sum(1 for r in rows if r.get("founder_email"))
    n_li = sum(1 for r in rows if r.get("founder_linkedin"))
    pre_seed_funds = sum(1 for r in kept if stage_has_preseed(r.get("stage", [])))
    micro_funds = sum(1 for r in kept if (r.get("size_bucket") or "").lower() == "micro")
    mkt_funds = sum(1 for r in kept if r.get("is_marketplace"))
    _log("")
    _log(f"DONE: {n_funds} funds ({pre_seed_funds} pre-seed, {micro_funds} micro/<$20M, {mkt_funds} marketplace)")
    _log(f"  founders: {n_founders} | with LinkedIn: {n_li} | with an email: {n_email}")
    _log(f"  CSV: {path}")

    if notion:
        url = output.push_to_notion(rows, "US consumer / marketplace micro-VC funds")
        _log(f"  Notion: {url or 'skipped (no token/parent)'}")

    return path, kept, rows
