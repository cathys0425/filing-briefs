"""Cover companies: python3 -m coverage.run AAPL MSFT --since 2021-01-01 -e MODEL -w MODEL [--industry NAME]

Per company it writes out/<TICKER>.md and out/<TICKER>.notes.json. With --industry it also
writes out/industry-<NAME>.md from the company briefs.
Earnings call transcripts are fetched from a public Hugging Face dataset into
data/transcripts/<TICKER>/<YYYY-MM-DD>.txt; files you add there yourself are read too.
"""
import argparse
import collections
import glob
import json
import os
import re

from coverage import edgar, extract, onepager, text, transcripts
from orc import APIError, complete

INDUSTRY_PROMPT = """These are one-page briefs for companies in one industry: {name}.
Write a one-page industry view for a systematic long/short equity researcher. Markdown, sections:
## How the industry makes money
## Common revenue drivers and KPIs
## Where the companies differ
## Catalysts shared across the group
## Datasets that would cover several companies at once
(each: the dataset, the driver or KPI it tracks, and the tickers it covers)
Use only what the briefs say. Every bullet must end with the brief notes it rests on, written as
ticker plus note id exactly as cited in that company's brief, like [UNP N12][CSX N40]. Name a
company in a bullet only if you cite a note from its brief. Keep figures exactly as the briefs
state them, with their period. At most 400 words.

{briefs}
"""


def industry_view(name, pages, model, complete=complete):
    """Industry view from company briefs {ticker: page}. Returns (markdown, cost)."""
    bodies = {t: p.split("## Revenue as first reported")[0] for t, p in pages.items()}
    briefs = "\n\n".join(f"=== {t} ===\n{b}" for t, b in bodies.items())
    view, cost = onepager.cached_reply("industry", INDUSTRY_PROMPT.format(name=name, briefs=briefs), model, complete)
    valid = {f"{t} {i}" for t, b in bodies.items() for i in re.findall(r"\[(N\d+)\]", b)}
    bad = []
    for line in view.splitlines():
        if line.lstrip().startswith(("-", "*")):
            cited = re.findall(r"\[([A-Z.\-]+ N\d+)\]", line)
            named = {t for t in bodies if re.search(rf"\b{re.escape(t)}\b", re.sub(r"\[[^\]]*\]", "", line))}
            if not cited or any(c not in valid for c in cited) or not named <= {c.split()[0] for c in cited}:
                bad.append(line.strip())
    out = [f"# Industry view: {name} ({', '.join(pages)})", "", view.strip(), "", "## Assumed, not verified", "",
           "- A citation shows the bullet points at a note in that company's brief; it does not show the "
           "bullet reads the brief correctly."]
    out += [f"- Bullet without a valid citation for every company it names: {b}" for b in bad]
    return "\n".join(out) + "\n", cost


def documents(ticker, cik, since):
    """Yield (label, form, filed, text or None). None means the section was not found."""
    for f in edgar.filings(cik, ["10-K", "10-Q"], since):
        body = text.html_to_text(edgar.get(f["url"]).decode("utf-8", "replace"))
        for label, start, ends in text.SECTIONS[f["form"]]:
            yield f"{f['form']} {f['period']} {label}", f["form"], f["filed"], text.section(body, start, ends)
    for path in sorted(glob.glob(f"data/transcripts/{ticker}/*.txt")):
        day = os.path.basename(path)[:-4]
        if day >= since:
            with open(path) as fh:
                yield f"Earnings call {day}", "call", day, fh.read()


def cover(ticker, since, extract_model, write_model, complete=complete):
    cik = edgar.cik_for(ticker)
    company = edgar.company(cik)
    notes, failures, dropped, cost = [], [], 0, 0.0
    found, short = transcripts.fetch(ticker)
    if not found:
        failures.append("earnings calls: ticker not in the transcript dataset")
    if short:
        failures.append(f"earnings calls: {short} transcripts are under {transcripts.SHORT} characters and may be cut off")
    forms, filed = collections.Counter(), []
    for label, form, day, body in documents(ticker, cik, since):
        if body is None:
            failures.append(f"{label}: section not found")
            continue
        if form != "call" and len(body) < text.MIN_SECTION:
            failures.append(f"{label}: only {len(body)} characters under this heading "
                            "(cross-reference or incorporation by reference, not the section text)")
            continue
        forms[form] += 1
        filed.append(day)
        for i, chunk in enumerate(text.chunks(body)):
            try:
                result = extract.extract(label, chunk, extract_model, complete)
            except (APIError, ValueError) as e:
                failures.append(f"{label} chunk {i}: {e}")
                continue
            ok, bad = extract.verify(result["notes"], chunk)
            dropped += len(bad)
            cost += result["cost"] or 0
            notes += [{**n, "doc": label, "filed": day} for n in ok]
        print(f"{ticker} {label}: {len(notes)} verified notes so far, {dropped} dropped")
    if not notes:
        raise RuntimeError(f"{ticker}: no verified notes. Failures: {failures}")
    for i, n in enumerate(notes, 1):
        n["id"] = f"N{i}"
    stats = {"docs": sum(forms.values()), "by_form": dict(forms), "first": min(filed), "last": max(filed),
             "dropped": dropped, "failures": failures, "transcripts": forms["call"]}
    page, write_cost = onepager.write(company, edgar.annual_revenue(cik), notes, stats, write_model,
                                      extract_model, complete)
    os.makedirs("out", exist_ok=True)
    with open(f"out/{ticker}.md", "w") as f:
        f.write(page)
    with open(f"out/{ticker}.notes.json", "w") as f:
        json.dump(notes, f, indent=1)
    print(f"{ticker}: out/{ticker}.md | cost ${cost + (write_cost or 0):.4f} | {len(failures)} failures")
    return page


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tickers", nargs="+")
    p.add_argument("--since", required=True, help="YYYY-MM-DD; read documents filed on or after this date")
    p.add_argument("-e", "--extract-model", required=True, help="cheap model that reads every document")
    p.add_argument("-w", "--write-model", required=True, help="stronger model that writes the briefs")
    p.add_argument("--industry", help="also write an industry view with this name")
    a = p.parse_args()
    pages = {t: cover(t, a.since, a.extract_model, a.write_model) for t in a.tickers}
    if a.industry:
        view, cost = industry_view(a.industry, pages, a.write_model)
        with open(f"out/industry-{a.industry}.md", "w") as f:
            f.write(view)
        print(f"out/industry-{a.industry}.md | cost ${cost or 0:.4f}")


if __name__ == "__main__":
    main()
