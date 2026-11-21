---
name: cover-company
description: Produce a one-page brief for one public company from its SEC filings and earnings call transcripts (business model, revenue build-up, core thesis, catalysts, KPIs, useful datasets). Use when asked to cover, brief or summarize a company from its public filings.
---

# Cover one company

The reading is done by fixed code in `coverage/`. Your job is to run it, check the result, and report. Do not rewrite the brief yourself and do not edit `coverage/` to make one company work.

## Before running

1. `SEC_USER_AGENT` must be set to a declared client string (SEC requires a name and contact). If it is not set, ask the user for the value; never invent a contact.
2. Earnings call transcripts are not on EDGAR. If the user has them, they go in `data/transcripts/<TICKER>/<YYYY-MM-DD>.txt` (the date is the call date). Public transcripts only; never firm-licensed text.
3. Ask which models to use if not given: a cheap one for `-e` (reads every document) and a stronger one for `-w` (writes the brief). State the expected number of documents before starting a long run.

## Run

```bash
python3 -m coverage.run <TICKER> --since <YYYY-MM-DD> -e <extract-model> -w <write-model>
```

Output: `out/<TICKER>.md` and `out/<TICKER>.notes.json`. Re-runs reuse the cache in `data/cache`, so a failed run can simply be started again.

## Check the result before reporting

Read `out/<TICKER>.md` and report these numbers from it:

- documents read, and how many sections are listed under "Not read"
- notes verified vs dropped. A drop rate above roughly 30% means the extract model is paraphrasing instead of quoting; say so and suggest another model
- every line under "Bullet without a valid citation"
- rows in the revenue table where "Later differing values" is not 0 (a restatement)

Then open three cited quotes in the Verified section and check that each bullet citing them says what the quote says. Report any that do not.

## Report format

First line: usable, usable with caveats, or not usable. Then the numbers above in a table. Do not summarize the brief; link to the file.
