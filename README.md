# OpenRouter MVP

One file (`orc.py`), Python 3.8+, no dependencies.

## Commands

```bash
python3 orc.py ask "Summarize the risks of high leverage in two sentences."
python3 orc.py chat
python3 orc.py compare "Explain EBITDA in one sentence." -m recursive/flint-v1.0:free liquid/lfm-3-1.7b:free -o compare.json
python3 orc.py models --free
```

- `ask` also reads piped input: `cat notes.txt | python3 orc.py ask -s "Summarize this."`
- `chat` keeps history; `/reset` clears it, `/model NAME` switches model, `/quit` exits.
- `compare` runs the models in parallel and can save everything to JSON with `-o`.
- Shared options: `-m MODEL`, `-s "system prompt"`, `--max-tokens N`, `--temperature X`.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | `proxy-injected` | Your key. Not needed in the Claude cloud session, where the proxy adds it. Required on your own computer. |
| `OPENROUTER_MODEL` | `recursive/flint-v1.0:free` | Default model for `ask` and `chat`. |

## Notes

- Free models are rate-limited (HTTP 429). The client retries 3 times with backoff, then reports the error.
- Reasoning models can spend a small `--max-tokens` budget on thinking and return nothing; the client reports this as an empty reply. Leave `--max-tokens` off unless you need it.
- For paid models, add credits at openrouter.ai and pass the model id with `-m`.

## Company and industry coverage (`coverage/`)

Reads a company's 10-K and 10-Q filings from SEC EDGAR (and earnings call transcripts you supply), and writes a one-page brief: business model, revenue build-up, core thesis, catalysts, KPIs, useful datasets.

```bash
export SEC_USER_AGENT="Your Name your@email"   # SEC requires a declared client
python3 -m coverage.run AAPL --since 2021-01-01 -e <cheap-model> -w <strong-model>
python3 -m coverage.run KO PEP KDP --since 2021-01-01 -e <cheap-model> -w <strong-model> --industry beverages
python3 -m unittest discover -s tests -t .
```

How correctness is checked:

- Every extracted note carries a verbatim quote; code drops notes whose quote is not in the source document.
- Every bullet in the brief must cite note ids; bullets without a valid citation are listed under "Assumed, not verified".
- Revenue history comes from XBRL as first reported, with the date it became public. The model never produces these numbers.

Not covered yet: 8-K earnings releases, foreign filers (20-F), segment revenue tables. Transcripts are read only from `data/transcripts/<TICKER>/<YYYY-MM-DD>.txt`.
