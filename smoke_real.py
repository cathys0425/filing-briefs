"""Real-data smoke test: no model calls, no cost. Run with: python3 smoke_real.py

Downloads the latest 10-K and 10-Q of a few companies from SEC and checks that every
section is found with a plausible length, that XBRL revenue is returned, and that the
transcript dataset still answers. The companies are the ones whose filing layouts broke
sectioning before (KO cross-references, CSX running page headers, AMAT colon headings)
plus UNP as a plain case. Needs SEC_USER_AGENT; the cache is skipped so each run hits the
live sources.
"""
import os
import sys
import tempfile

TICKERS = ["KO", "UNP", "CSX", "AMAT"]
MIN_CHARS = 10000   # shortest real section seen so far is about 12,000 (TXN 10-Q MD&A)
MAX_CHARS = 400000  # a section this long has swallowed its neighbours


def main():
    if not os.environ.get("SEC_USER_AGENT"):
        sys.exit("SEC_USER_AGENT is not set (in GitHub: add it as a repository secret).")
    os.environ["COVERAGE_CACHE"] = tempfile.mkdtemp()  # read when coverage is imported
    from coverage import edgar, text, transcripts
    os.chdir(tempfile.mkdtemp())  # transcripts.fetch writes under ./data

    failures = []
    for ticker in TICKERS:
        cik = edgar.cik_for(ticker)
        filings = edgar.filings(cik, ["10-K", "10-Q"], "2000-01-01")
        for form in ("10-K", "10-Q"):
            f = [x for x in filings if x["form"] == form][-1]
            body = text.html_to_text(edgar.get(f["url"]).decode("utf-8", "replace"))
            for label, start, ends in text.SECTIONS[form]:
                s = text.section(body, start, ends)
                n = len(s) if s else 0
                ok = MIN_CHARS <= n <= MAX_CHARS
                print(f"{'ok  ' if ok else 'FAIL'} {ticker} {form} {f['period']} {label}: {n:,} chars")
                if not ok:
                    failures.append(f"{ticker} {form} {f['period']} {label}: {n:,} chars")
        revenue = edgar.annual_revenue(cik)
        ok = len(revenue) >= 5 and revenue[-1]["value"] > 0
        print(f"{'ok  ' if ok else 'FAIL'} {ticker} XBRL revenue: {len(revenue)} fiscal years")
        if not ok:
            failures.append(f"{ticker} XBRL revenue: {len(revenue)} fiscal years")
    found, _ = transcripts.fetch("KO")
    ok = found >= 70
    print(f"{'ok  ' if ok else 'FAIL'} KO transcripts in dataset: {found}")
    if not ok:
        failures.append(f"KO transcripts in dataset: {found}")
    if failures:
        sys.exit("Smoke test failed:\n" + "\n".join(failures))
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
