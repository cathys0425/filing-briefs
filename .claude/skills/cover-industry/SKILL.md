---
name: cover-industry
description: Cover a whole industry quickly, producing one brief per company plus an industry view. Use when asked to cover, map or get up to speed on an industry or a list of companies.
---

# Cover an industry

## 1. Settle the company list

The user decides which companies are in the industry. If they give only an industry name, propose a list of US-listed tickers and wait for them to confirm or edit it. Foreign filers (20-F, 6-K) are not supported; name any you leave out.

## 2. Run

For up to about five companies, run them in one command:

```bash
python3 -m coverage.run <T1> <T2> ... --since <YYYY-MM-DD> -e <extract-model> -w <write-model> --industry <name>
```

For more, start one subagent per company, each following the `cover-company` skill, then run the command above once at the end; the company runs are cached, so only the industry view is new work.

State the total number of companies and the model choice before starting, because cost scales with both.

## 3. Check

- Apply the `cover-company` checks to each brief. A company whose brief is not usable is listed as such; it is not dropped silently from the industry view.
- In `out/industry-<name>.md`, check that every ticker in the list appears, and that each dataset idea names the driver it tracks.

## 4. Report

One table: ticker, documents read, notes verified, notes dropped, sections not read, verdict. Then the path to the industry view.
