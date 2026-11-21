"""Reduce step: write the company one-pager from verified notes, then check its citations."""
import datetime
import hashlib
import json
import os
import re

CACHE = os.environ.get("COVERAGE_CACHE", "data/cache")

PER_CATEGORY = 40  # newest notes kept per category for the writer; the rest are counted, not hidden

PROMPT = """Write a one-page company brief for a systematic long/short equity researcher.
Use ONLY the year digests and numbered notes below. Every bullet must end with the ids of the
notes it rests on, like [N12] or [N3][N40]; ids that appear in a digest bullet may be cited.
Do not state anything the notes do not support. No filler words such as "promising".
At most 450 words. Markdown, exactly these sections:

## Business model
## Revenue build-up
(segments or volume x price; what drives each piece)
## Core thesis
(2-3 bullets: what has to be true for revenue and margins to move, and in which direction)
## What changed over time
(3-5 bullets, oldest first: turning points only, each with its year)
## Catalysts
(events still ahead of {today}, dated or datable, nearest first; an event that has already
happened is not a catalyst and belongs under "What changed over time" if it matters)
## KPIs to track
## Potentially useful datasets
(each: the dataset, the driver or KPI it would track, and why it should lead reported numbers)

Company: {name} ({sic})
Today: {today}. The newest document below may be older than today; say so in Core thesis if
the latest guidance is more than six months old.

Year digests, oldest first:
{digests}

Most recent notes (id | document | category | claim):
{notes}
"""


DIGEST_PROMPT = """Below are notes from one company's filings and earnings calls for {year}.
Write at most 8 bullets on what a researcher must remember about this year: changes to the
business model or segments, what moved revenue and margins, guidance given and whether earlier
guidance was met, dated events, new risks. Prefer changes over facts that are true every year.
Every bullet must end with the ids of the notes it rests on, like [N12][N40]. Use only the notes.
Bullets only, no headings.

{notes}
"""


def digest(year, notes, model, complete):
    """Summarize one year's notes. Returns (bullets with valid citations, number dropped, cost)."""
    prompt = DIGEST_PROMPT.format(year=year, notes=listing(notes))
    path = os.path.join(CACHE, "digest-" + hashlib.sha1((model + prompt).encode()).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path) as f:
            reply, cost = json.load(f)
    else:
        reply, usage, _ = complete([{"role": "user", "content": prompt}], model)
        cost = usage.get("cost")
        os.makedirs(CACHE, exist_ok=True)
        with open(path, "w") as f:
            json.dump([reply, cost], f)
    bullets = [line.strip() for line in reply.splitlines() if line.lstrip().startswith(("-", "*"))]
    bad = check_citations("\n".join(bullets), {n["id"] for n in notes})
    return [b for b in bullets if b not in bad], len(bad), cost


def listing(notes):
    return "\n".join(f"{n['id']} | {n['doc']} | {n['category']} | {n['claim']}" for n in notes)


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


def write(company, revenue, notes, stats, model, digest_model, complete):
    kept, left_out = select(notes)
    digests, digest_dropped, cost = [], 0, 0.0
    for year in sorted({n["filed"][:4] for n in notes}):
        bullets, bad, c = digest(year, [n for n in notes if n["filed"][:4] == year], digest_model, complete)
        digests.append(f"{year}\n" + "\n".join(bullets))
        digest_dropped += bad
        cost += c or 0
    body, usage, _ = complete([{"role": "user", "content": PROMPT.format(
        name=company["name"], sic=company["sic_description"], today=datetime.date.today().isoformat(),
        digests="\n\n".join(digests),
        notes=listing(kept))}], model)
    cost += usage.get("cost") or 0
    by_id = {n["id"]: n for n in notes}
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
            f"{stats['dropped']} notes dropped because the quote was not found or lacked a number stated in the claim.",
            f"- {len(cited)} notes cited above. Quotes:"]
    out += [f"  - {i} ({by_id[i]['doc']}): \"{by_id[i]['quote']}\"" for i in cited]
    out += ["", "## Assumed, not verified", "",
            "- A verified quote shows the passage exists; it does not show the claim reads it correctly.",
            "- The writer model chose which notes matter. Omitted notes may contradict the brief."]
    out += [f"- Bullet without a valid citation: {b}" for b in unsupported]
    out += ["", "## Checks not done", "",
            f"- {left_out} older notes reached the writer only through {len(digests)} year digests "
            f"(limit {PER_CATEGORY} full notes per category); {digest_dropped} digest bullets were dropped "
            "for lacking a valid citation."]
    out += [f"- Not read: {f}" for f in stats["failures"]]
    out += [f"- Earnings call transcripts read: {stats['transcripts']} (dataset ends May 2025; later calls are missing). "
                 "8-K earnings releases are not read yet.",
            "- No comparison against consensus, price, or peers."]
    return "\n".join(out) + "\n", cost
