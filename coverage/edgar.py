"""SEC EDGAR access: filing index, filing documents, XBRL financial facts.

Assumptions (source: SEC developer docs unless marked otherwise):
- data.sec.gov/submissions lists every filing; `filingDate` is the date it became public.
- XBRL companyfacts `filed` is the date a value became public; `end` is the period end.
- SEC asks automated clients to declare themselves in the User-Agent and to stay under
  10 requests/second. www.sec.gov rejects undeclared clients with HTTP 403 (observed).
- companyfacts has no segment (dimensional) data. Segment revenue must come from the text.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

CACHE = os.environ.get("COVERAGE_CACHE", "data/cache")
UA = os.environ.get("SEC_USER_AGENT", "research-script")
REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]


def get(url):
    """GET with an on-disk cache. Filings never change once published, so the cache never expires."""
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    time.sleep(0.15)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 403 and "www.sec.gov" in url:
            raise RuntimeError(
                f"SEC refused {url} (403). Set SEC_USER_AGENT to a declared client, "
                "e.g. 'Your Name your@email', as SEC requires.") from None
        raise
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return body


def cik_for(ticker):
    """Ticker -> 10-digit CIK. A string of digits is treated as a CIK already."""
    if ticker.isdigit():
        return ticker.zfill(10)
    table = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
    hits = [row for row in table.values() if row["ticker"] == ticker.upper()]
    if len(hits) != 1:
        raise ValueError(f"{ticker}: expected exactly 1 CIK match, found {len(hits)}")
    return str(hits[0]["cik_str"]).zfill(10)


def company(cik):
    s = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    return {"cik": cik, "name": s["name"], "tickers": s["tickers"], "sic": s["sic"],
            "sic_description": s["sicDescription"]}


def filings(cik, forms, since):
    """All filings of the given form types filed on or after `since` (YYYY-MM-DD), oldest first."""
    s = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    pages = [s["filings"]["recent"]]
    for extra in s["filings"]["files"]:
        pages.append(json.loads(get(f"https://data.sec.gov/submissions/{extra['name']}")))
    out = []
    for p in pages:
        for i, form in enumerate(p["form"]):
            if form in forms and p["filingDate"][i] >= since:
                acc = p["accessionNumber"][i]
                out.append({
                    "form": form, "accession": acc, "filed": p["filingDate"][i],
                    "period": p["reportDate"][i], "items": p["items"][i],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                           f"{acc.replace('-', '')}/{p['primaryDocument'][i]}",
                })
    return sorted(out, key=lambda f: f["filed"])


def annual_revenue(cik):
    """Fiscal-year revenue as first reported, from XBRL. Returns rows of (period_end, value, filed, tag).

    When a period was reported more than once (restatement or comparative column), the
    earliest filing wins, so each number is what was known at the time. The count of
    later differing values is returned so restatements are visible, not hidden.
    """
    facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))["facts"]["us-gaap"]
    by_end = {}
    for tag in REVENUE_TAGS:
        for v in facts.get(tag, {}).get("units", {}).get("USD", []):
            if v["form"] != "10-K" or "start" not in v:
                continue
            days = (time.mktime(time.strptime(v["end"], "%Y-%m-%d")) -
                    time.mktime(time.strptime(v["start"], "%Y-%m-%d"))) / 86400
            if not 350 <= days <= 380:
                continue
            by_end.setdefault(v["end"], []).append({"value": v["val"], "filed": v["filed"], "tag": tag})
    rows = []
    for end in sorted(by_end):
        vals = sorted(by_end[end], key=lambda v: v["filed"])
        first = vals[0]
        rows.append({"period_end": end, **first,
                     "later_differing_values": len({v["value"] for v in vals} - {first["value"]})})
    return rows
