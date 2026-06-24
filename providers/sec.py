"""
Authoritative fund-size lookup from SEC EDGAR Form D filings.

US venture funds file Form D when they raise, disclosing the total offering
amount (the fund's target size). That is public and exact, so it beats any LLM
estimate. For a firm we full-text-search EDGAR for its Form D filings, match the
ones that are actually this firm's fund vehicle, and return the most recent
fund's offering amount.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

from . import http

_UA = {"User-Agent": "sg-investor-finder research alvaro@socialgravity.ai"}
_EFTS = "https://efts.sec.gov/LATEST/search-index?q={q}&forms=D"
_GETCO = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={q}"
    "&type=D&dateb=&owner=include&count=40&output=atom"
)
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"

_SUFFIX = re.compile(
    r"\b(ventures?|capital|partners|vc|management|group|associates|holdings|"
    r"advisors?|llc|lp|l\.p\.|inc|co)\b", re.I
)
_NON = re.compile(r"[^a-z0-9 ]+")
# Sub-vehicles that are not "the fund" for sizing purposes.
_NOT_MAIN = ("angel squad", "spv", "feeder", "co-invest", "coinvest", "scout")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _NON.sub(" ", (s or "").lower())).strip()


def _core(firm: str) -> str:
    n = _norm(firm)
    n = _SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _doc_url(acc_id: str) -> str:
    acc, doc = acc_id.split(":")
    cik = acc.split("-")[0].lstrip("0")
    nodash = acc.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{doc}"


def _acc_year(acc_id: str) -> int:
    # "0001905298-22-000001:..." -> 2022
    try:
        yy = int(acc_id.split("-")[1])
        return 2000 + yy if yy < 80 else 1900 + yy
    except Exception:
        return 0


def _num(v: str | None) -> int | None:
    if not v:
        return None
    v = v.strip().replace(",", "")
    if not v.isdigit():
        return None
    n = int(v)
    return n if n > 0 else None


def _parse_filing(acc_id: str) -> dict | None:
    try:
        r = http.request("GET", _doc_url(acc_id), headers=_UA, max_retries=2, timeout=20)
    except Exception:
        return None
    text = re.sub(r'xmlns(:\w+)?="[^"]*"', "", r.text)
    try:
        root = ET.fromstring(text)
    except Exception:
        return None

    def g(tag: str) -> str | None:
        e = root.find(".//" + tag)
        return e.text if e is not None else None

    entity = g("entityName") or ""
    offering = _num(g("totalOfferingAmount"))
    sold = _num(g("totalAmountSold"))
    amount = offering or sold  # offering is the target size; sold is the fallback
    if not amount:
        return None
    return {"entity": entity, "amount": amount, "year": _acc_year(acc_id), "accession": acc_id.split(":")[0]}


def _is_main(np: str, core: str) -> bool:
    """A flagship fund vehicle, not a small series / SPV / side vehicle."""
    if not np.startswith(core):
        return False
    return "a series of" not in np and "dc vc" not in np and "qp" not in np.split()


def form_d_size(firm: str, max_filings: int = 10) -> dict | None:
    """Return {amount, entity, year, accession, url, is_main} for the firm's
    flagship fund (largest main offering), or None if no Form D matches.

    We prefer entities that look like the firm's own main fund and take the
    LARGEST offering among them, because the most recent filing is often a tiny
    SPV / series vehicle rather than the flagship fund.
    """
    core = _core(firm)
    if len(core) < 3:
        return None
    url = _EFTS.format(q=urllib.parse.quote(f'"{firm}"'))
    try:
        hits = http.request("GET", url, headers=_UA, max_retries=2).json().get("hits", {}).get("hits", [])
    except Exception:
        return None

    matched = []  # (id, is_main)
    for h in hits:
        names = h.get("_source", {}).get("display_names", []) or []
        primary = names[0] if names else ""
        np = _norm(primary)
        if core not in np:
            continue
        if np.startswith("qp ") or any(x in np for x in _NOT_MAIN):
            continue
        _id = h.get("_id", "")
        if _id:
            matched.append((_id, _is_main(np, core)))

    if not matched:
        return None

    # Parse main-looking filings first, then others, capped.
    matched.sort(key=lambda m: (m[1], _acc_year(m[0])), reverse=True)
    parsed = []
    for acc_id, is_main in matched[:max_filings]:
        f = _parse_filing(acc_id)
        if f:
            f["url"] = _doc_url(acc_id)
            f["is_main"] = is_main
            parsed.append(f)
    if not parsed:
        return None

    mains = [p for p in parsed if p["is_main"]]
    pool = mains or parsed
    # Flagship = largest offering; tie-break to the more recent filing.
    return max(pool, key=lambda x: (x["amount"], x["year"]))


def _company_form_d(firm: str) -> dict | None:
    """Fallback: find the firm's entity via EDGAR company search, then read its
    Form D filings directly. Catches funds whose Form D text did not contain the
    firm's marketing name (so full-text search missed them)."""
    core = _core(firm)
    if len(core) < 3:
        return None
    try:
        atom = http.request("GET", _GETCO.format(q=urllib.parse.quote(firm)), headers=_UA, max_retries=2).text
    except Exception:
        return None
    ciks = list(dict.fromkeys(re.findall(r"<cik>(\d+)</cik>", atom)))[:4]
    parsed = []
    for cik in ciks:
        try:
            sub = http.request("GET", _SUBMISSIONS.format(cik10=cik.zfill(10)), headers=_UA, max_retries=2).json()
        except Exception:
            continue
        if core not in _norm(sub.get("name", "")):
            continue
        rec = sub.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        accs = rec.get("accessionNumber", [])
        docs = rec.get("primaryDocument", [])
        for form, acc, doc in zip(forms, accs, docs):
            if form != "D":
                continue
            acc_id = f"{acc}:{doc or 'primary_doc.xml'}"
            f = _parse_filing(acc_id)
            if f:
                f["url"] = _doc_url(acc_id)
                f["is_main"] = True
                parsed.append(f)
    if not parsed:
        return None
    return max(parsed, key=lambda x: (x["amount"], x["year"]))


_orig_form_d_size = form_d_size


def form_d_size(firm: str, max_filings: int = 10) -> dict | None:  # noqa: F811
    res = _orig_form_d_size(firm, max_filings=max_filings)
    if res:
        return res
    return _company_form_d(firm)
