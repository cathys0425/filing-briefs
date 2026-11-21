"""Reduce step: write the company one-pager from verified notes, then check its citations."""
import re

PER_CATEGORY = 40  # newest notes kept per category for the writer; the rest are counted, not hidden

PROMPT = """Write a one-page company brief for a systematic long/short equity researcher.
Use ONLY the numbered notes below. Every bullet must end with the ids of the notes it
rests on, like [N12] or [N3][N40]. Do not state anything the notes do not support.
No filler words such as "promising". At most 350 words. Markdown, exactly these sections:

## Business model
## Revenue build-up
(segments or volume x price; what drives each piece)
## Core thesis
(2-3 bullets: what has to be true for revenue and margins to move, and in which direction)
## Catalysts
(dated or datable; newest first)
## KPIs to track
## Potentially useful datasets
(each: the dataset, the driver or KPI it would track, and why it should lead reported numbers)

Company: {name} ({sic})

Notes (id | document | category | claim):
{notes}
"""


def select(notes):
    """Newest PER_CATEGORY notes per category. Returns (kept, number left out)."""
    kept, seen = [], {}
    for n in sorted(notes, key=lambda n: n["filed"], reverse=True):
        seen[n["category"]] = seen.get(n["category"], 0) + 1
        if seen[n["category"]] <= PER_CATEGORY:
            kept.append(n)
    return kept, len(notes) - len(kept)


def check_citations(body, ids):
    """Bullets citing no note, or a note id that does not exist."""
    bad = []
    for line in body.splitlines():
        if line.lstrip().startswith(("-", "*")):
            cited = re.findall(r"\[(N\d+)\]", line)
            if not cited or any(c not in ids for c in cited):
                bad.append(line.strip())
    return bad


def write(company, revenue, notes, stats, model, complete):
    kept, left_out = select(notes)
    listing = "\n".join(f"{n['id']} | {n['doc']} | {n['category']} | {n['claim']}" for n in kept)
    body, usage, _ = complete([{"role": "user", "content": PROMPT.format(
        name=company["name"], sic=company["sic_description"], notes=listing)}], model)
    by_id = {n["id"]: n for n in kept}
    unsupported = check_citations(body, set(by_id))
    cited = sorted(set(re.findall(r"\[(N\d+)\]", body)) & set(by_id), key=lambda i: int(i[1:]))

    out = [f"# {company['name']} ({', '.join(company['tickers'])})", "", body.strip(), "",
           "## Revenue as first reported (XBRL, not model-generated)", "",
           "| Fiscal year end | Revenue (USD m) | Public on | Later differing values |", "|---|---|---|---|"]
    out += [f"| {r['period_end']} | {r['value'] / 1e6:,.0f} | {r['filed']} | {r['later_differing_values']} |"
            for r in revenue]
    out += ["", "## Verified", "",
            f"- {stats['docs']} documents read ({stats['by_form']}), filed {stats['first']} to {stats['last']}.",
            f"- {len(notes)} notes whose quote was found verbatim in its source document; "
            f"{stats['dropped']} notes dropped because the quote was not found.",
            f"- {len(cited)} notes cited above. Quotes:"]
    out += [f"  - {i} ({by_id[i]['doc']}): \"{by_id[i]['quote']}\"" for i in cited]
    out += ["", "## Assumed, not verified", "",
            "- A verified quote shows the passage exists; it does not show the claim reads it correctly.",
            "- The writer model chose which notes matter. Omitted notes may contradict the brief."]
    out += [f"- Bullet without a valid citation: {b}" for b in unsupported]
    out += ["", "## Checks not done", "",
            f"- {left_out} older notes were not shown to the writer (limit {PER_CATEGORY} per category)."]
    out += [f"- Not read: {f}" for f in stats["failures"]]
    out += [f"- Earnings call transcripts read: {stats['transcripts']}. 8-K earnings releases are not read yet.",
            "- No comparison against consensus, price, or peers."]
    return "\n".join(out) + "\n", usage.get("cost")
