"""Real-data smoke test.

  python3 smoke_real.py         live SEC and transcript sources; no model calls, no cost
  python3 smoke_real.py model   one extraction call on a real filing (about $0.01)

Downloads the latest 10-K and 10-Q of a few companies from SEC and checks that every
section is found with a plausible length, that XBRL revenue is returned, and that the
transcript dataset still answers. The companies are the ones whose filing layouts broke
sectioning before (KO cross-references, CSX running page headers, AMAT colon headings,
COST dash headings)
plus UNP as a plain case. The model check extracts notes from KO's latest 10-Q MD&A and
fails if the reply is not valid JSON, too few notes survive quote verification, or too many
are dropped. Needs SEC_USER_AGENT (and an OpenRouter key for the model check); the cache is
skipped so each run hits the live sources.
"""
import os
import sys
import tempfile

TICKERS = ["KO", "UNP", "CSX", "AMAT", "COST"]
MIN_CHARS = 10000   # shortest real section seen so far is about 12,000 (TXN 10-Q MD&A)
MAX_CHARS = 400000  # a section this long has swallowed its neighbours
MODEL = "anthropic/claude-haiku-5.5"  # the extract model used for the example briefs
MIN_NOTES = 5       # verified notes expected from one 60,000-character chunk (typical: 12-15)
MAX_DROP = 0.30     # observed drop rates are 4-13%; above this the model is paraphrasing


def model_check():
    from coverage import edgar, extract, text
    from orc import complete
    f = [x for x in edgar.filings(edgar.cik_for("KO"), ["10-Q"], "2000-01-01")][-1]
    body = text.html_to_text(edgar.get(f["url"]).decode("utf-8", "replace"))
    label, start, ends = text.SECTIONS["10-Q"][0]
    chunk = text.chunks(text.section(body, start, ends))[0]
    result = extract.extract(f"10-Q {f['period']} {label}", chunk, MODEL, complete)  # raises on malformed JSON
    ok, bad = extract.verify(result["notes"], chunk)
    total = len(ok) + len(bad)
    print(f"{MODEL} on KO 10-Q {f['period']}: {len(ok)} notes verified, {len(bad)} dropped, "
          f"cost ${result['cost'] or 0:.4f}")
    if len(ok) < MIN_NOTES or len(bad) / total > MAX_DROP:
        sys.exit(f"Model check failed: need at least {MIN_NOTES} verified notes and a drop rate of at most "
                 f"{MAX_DROP:.0%}. Dropped claims: {[n['claim'] for n in bad]}")
    print("Model check passed.")


def main():
    if not os.environ.get("SEC_USER_AGENT"):
        sys.exit("SEC_USER_AGENT is not set (in GitHub: add it as a repository secret).")
    os.environ["COVERAGE_CACHE"] = tempfile.mkdtemp()  # read when coverage is imported
    if sys.argv[1:] == ["model"]:
        return model_check()
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
