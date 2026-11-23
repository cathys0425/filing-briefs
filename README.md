# openrouter-mvp

Turn a public company's SEC filings and earnings calls into a one-page research brief, with every claim traceable to a quoted passage in a source document. Run it on several companies to get an industry view.

Models are called through [OpenRouter](https://openrouter.ai). The code is plain Python with no dependencies.

This is a personal learning project, not investment advice. The briefs are model-written summaries of public documents; read the limitations before relying on one.

## What it produces

For one ticker, a Markdown page with these sections:

| Section | Content |
|---|---|
| Business model | How the company makes money |
| Revenue build-up | Segments, or volume times price, and what drives each piece |
| Core thesis | What has to be true for revenue and margins to move |
| What changed over time | Turning points, by year |
| Catalysts | Dated events still ahead |
| KPIs to track | The operating metrics management reports |
| Potentially useful datasets | Observable data that should lead a reported driver |
| Revenue as first reported | Fiscal-year revenue from XBRL, with the date it became public |
| Verified / Assumed, not verified / Checks not done | What the code checked, what it did not, and what was not read |

A bullet from [`examples/COST.md`](examples/COST.md):

> Comps = ticket × frequency; in FY2026 ticket contributed more. Q3 comps were 9.8% reported, 6.6% adjusted for gasoline and FX. [N511][N736]

`[N511]` and `[N736]` are note ids. Each cited note appears lower on the same page with the passage it was quoted from and the document it came from.

For several tickers, an industry view built from the company briefs: how the industry makes money, common drivers and KPIs, where the companies differ, shared catalysts, and datasets that cover several companies at once. See [`examples/industry-big-box-retail.md`](examples/industry-big-box-retail.md).

## How it works

```
SEC EDGAR: 10-K (Items 1, 1A, 7), 10-Q (MD&A), 8-K earnings press releases
Hugging Face dataset: earnings call transcripts
        |
        v
1. Extract    a cheap model reads each chunk and returns notes, each with a verbatim quote
2. Verify     code keeps a note only if its quote is in the source and contains the claim's numbers
3. Digest     each year's notes are condensed into cited bullets
4. Write      a stronger model writes the brief from the digests and the newest notes
5. Check      code checks every bullet's citations and the word limit
        |
        v
out/<TICKER>.md   out/<TICKER>.notes.json   out/industry-<name>.md
```

The model does the reading and writing. Code decides what counts as supported.

## How correctness is checked

- **Quotes.** A note is kept only if its quote appears verbatim in the source document and contains every number stated in the claim.
- **Citations.** Every bullet in a year digest, a brief and an industry view must cite valid notes. An industry bullet must cite a note from the brief of each company it names. Bullets that fail are dropped or listed under "Assumed, not verified".
- **Unread material.** A filing section under 2,000 characters or a transcript under 5,000 is listed under "Not read" instead of being sent to the model.
- **Revenue.** The revenue table comes from XBRL as first reported. The model never produces these numbers.
- **Length.** A brief over 450 words (an industry view over 400), not counting citation ids, gets one request to shorten. If it is still over, the page says so.
- **Dates.** The writer is told today's date, so past events are not listed as catalysts and stale guidance is called out.

A citation shows that a passage exists and contains the numbers. It does not show that the bullet reads the passage correctly. That still needs a person.

## Quick start

Requirements: Python 3.8 or later, an OpenRouter API key with credits, and a contact string for SEC.

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

```bash
export SEC_USER_AGENT="Your Name your@email"
```

SEC asks automated clients to identify themselves and refuses downloads without this.

Cover one company:

```bash
python3 -m coverage.run COST --since 2021-01-01 -e anthropic/claude-haiku-5.5 -w anthropic/claude-sonnet-5.5
```

Cover an industry:

```bash
python3 -m coverage.run UNP CSX NSC --since 2021-01-01 -e anthropic/claude-haiku-5.5 -w anthropic/claude-sonnet-5.5 --industry railroads
```

| Option | Meaning |
|---|---|
| `--since` | Read documents filed on or after this date |
| `-e` | Model that reads every document (cheap) |
| `-w` | Model that writes the briefs (stronger) |
| `--industry` | Also write an industry view with this name |

Output goes to `out/`. Downloads and model replies are cached in `data/cache`, so an interrupted run can simply be started again and a repeated run costs nothing.

Before covering a new company, check that its filings are cut into sections of plausible length (tens of thousands of characters). Filing layouts vary and this is the step that breaks most often; see Limitations.

## What has been run

All runs read documents filed since 2021-01-01, with `anthropic/claude-haiku-5.5` for extraction and `anthropic/claude-sonnet-5.5` for writing.

| Industry | Companies | Output |
|---|---|---|
| Beverages | KO | [`KO.md`](examples/KO.md) |
| Railroads | UNP, CSX, NSC | [`industry-railroads.md`](examples/industry-railroads.md) |
| Semiconductors | NVDA, AMD, INTC, TXN, QCOM, AVGO, MU, ADI, AMAT, LRCX, KLAC | [`industry-semiconductors.md`](examples/industry-semiconductors.md) |
| Big-box retail | WMT, TGT, COST, HD, LOW | [`industry-big-box-retail.md`](examples/industry-big-box-retail.md) |

- Cost was about $0.30 to $0.40 per company.
- Most companies had 50 to 75 documents and 740 to 1,350 verified notes; Intel, read from calls only, had 316. Between 0.3% and 12.5% of notes were dropped by the quote check.
- The examples were generated at different stages of the project. Only `COST.md` comes from the current code; the other briefs are over the word limit and do not include earnings press releases.

## Repository layout

| Path | Purpose |
|---|---|
| `coverage/edgar.py` | SEC filing index, downloads, earnings releases, XBRL revenue, on-disk cache |
| `coverage/transcripts.py` | Earnings call transcripts from the Hugging Face dataset |
| `coverage/text.py` | Filing HTML to text; cuts out the sections to read |
| `coverage/extract.py` | Extraction prompt, note parsing, quote verification |
| `coverage/onepager.py` | Year digests, brief writing, citation and length checks |
| `coverage/run.py` | Command-line entry point and the industry view |
| `orc.py` | OpenRouter command-line client; the pipeline calls models through it |
| `harness.py`, `tasks.jsonl` | First step of a model comparison harness (unfinished) |
| `smoke_real.py` | Checks against live sources |
| `tests/` | Offline unit tests |
| `examples/` | Generated briefs and industry views |
| `.claude/` | Skills, a reviewer subagent and a command for Claude Code |
| `.github/workflows/` | CI and the weekly smoke test |

## Other tools in this repo

### `orc.py`: OpenRouter client

```bash
python3 orc.py ask "Summarize the risks of high leverage in two sentences."
```

```bash
python3 orc.py chat
```

```bash
python3 orc.py compare "Explain EBITDA in one sentence." -m recursive/flint-v1.0:free liquid/lfm-3-1.7b:free -o compare.json
```

```bash
python3 orc.py models --free
```

- `ask` also reads piped input. `chat` keeps history; `/reset`, `/model NAME` and `/quit` control it.
- Shared options: `-m MODEL`, `-s "system prompt"`, `--max-tokens N`, `--temperature X`.
- `OPENROUTER_MODEL` sets the default model for `ask` and `chat` (default `recursive/flint-v1.0:free`).
- Rate limits and provider errors are retried three times. Free models are rate-limited and often fail anyway.

### `harness.py`: model comparison, step 1 only

```bash
python3 harness.py -m recursive/flint-v1.0:free nvidia/nemotron-3.5-lightning:free
```

Runs every task in `tasks.jsonl` against every model and writes one raw row per pair to `results.jsonl`: output, expected answer, latency, tokens and cost. There is no scoring yet, the three tasks are a smoke test rather than ground truth, and nine known defects are listed in [pull request 2](https://github.com/cathys0425/openrouter-mvp/pull/2).

### Claude Code components (`.claude/`)

| Component | Purpose |
|---|---|
| Skill `cover-company` | How to run one company, what to check afterwards, how to report |
| Skill `cover-industry` | How to cover a list of companies |
| Subagent `diff-reviewer` | Read-only reviewer that sees only a diff and the requirement; each finding needs a file, line and failing input |
| Command `/review-diff` | Runs the reviewer on the current branch |

## Tests and CI

```bash
python3 -m unittest discover -s tests -t .
```

Offline unit tests; the model and SEC are stubbed, so no key is needed.

```bash
python3 smoke_real.py
```

Live check without model calls: downloads the latest 10-K and 10-Q for KO, UNP, CSX, AMAT and COST, and checks section lengths, XBRL revenue and the transcript dataset. Each of those companies has a filing layout that broke sectioning at some point.

```bash
python3 smoke_real.py model
```

One real extraction call (about one cent) that fails if the reply is malformed, too few notes pass verification, or too many are dropped.

| Workflow | Runs | Does |
|---|---|---|
| `ci.yml` | Every pull request and push to `main` | `ruff check` and the unit tests |
| `smoke.yml` | Mondays 14:17 UTC, or on demand | Both smoke checks; needs the `SEC_USER_AGENT` and `OPENROUTER_API_KEY` repository secrets |

## Limitations

- **Sectioning is fragile.** Twenty companies exposed six different filing layouts that cut sections wrongly, each found only on a real run. A new company may expose another.
- **Some filings cannot be read.** Intel lists its items only in a page index at the end of the filing, so its 10-K and 10-Q are reported as not read and its brief rests on calls alone.
- **No earnings calls after May 2025.** The transcript dataset ends there. Later quarters are covered by earnings press releases, which have no analyst Q&A. You can add transcripts yourself as `data/transcripts/<TICKER>/<YYYY-MM-DD>.txt`.
- **US large caps only for transcripts**, and US domestic filers only: 20-F filers are not supported.
- **Citations are not interpretation checks.** Only 3 to 7 citations per brief were compared with the filing by hand.
- **Segment revenue tables are not parsed.** Segment figures in a brief come from the text.
- **Revenue table dates.** For early fiscal years the "Public on" date can be later than the true first disclosure.
- **One-shot shortening.** The word limit was verified on one company; a brief can still come out slightly over, in which case the page says so.

## Data sources

- Filings and XBRL facts: [SEC EDGAR](https://www.sec.gov/edgar), public.
- Earnings call transcripts: the Hugging Face dataset [`kurry/sp500_earnings_transcripts`](https://huggingface.co/datasets/kurry/sp500_earnings_transcripts). Its MIT label is the uploader's; the original source of the text is not documented, so check before any use beyond personal study.
