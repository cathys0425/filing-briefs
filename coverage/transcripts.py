"""Earnings call transcripts from the public Hugging Face dataset kurry/sp500_earnings_transcripts.

Assumptions:
- Coverage is S&P 500 and US large caps, 2005 to May 2025 (dataset card; KO checked: 75 calls, 2006-2025).
- `date` is the call date and time, taken as the time the text became public (guess; time zone not documented).
- The MIT license is the uploader's label; the original source of the text is not documented.
"""
import json
import os
import urllib.parse

from coverage.edgar import get

API = "https://datasets-server.huggingface.co/filter"
SHORT = 5000  # characters; a full call is typically 40,000+


def fetch(ticker):
    """Write data/transcripts/<TICKER>/<YYYY-MM-DD>.txt for every call in the dataset. Returns (count, short count)."""
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"dataset": "kurry/sp500_earnings_transcripts", "config": "default",
                                    "split": "train", "where": f"\"symbol\"='{ticker}'",
                                    "offset": offset, "length": 100})
        page = json.loads(get(f"{API}?{q}"))
        if any(r["truncated_cells"] for r in page["rows"]):
            raise RuntimeError(f"{ticker}: dataset API returned truncated transcript text")
        rows += [r["row"] for r in page["rows"]]
        offset += 100
        if offset >= page["num_rows_total"]:
            break
    days = [r["date"][:10] for r in rows]
    if len(set(days)) != len(days):
        raise RuntimeError(f"{ticker}: more than one transcript on the same date: "
                           f"{sorted(d for d in set(days) if days.count(d) > 1)}")
    os.makedirs(f"data/transcripts/{ticker}", exist_ok=True)
    for r in rows:
        with open(f"data/transcripts/{ticker}/{r['date'][:10]}.txt", "w") as f:
            f.write(r["content"])
    short = sum(len(r["content"]) < SHORT for r in rows)
    print(f"{ticker}: {len(rows)} transcripts in dataset, {short} shorter than {SHORT} characters")
    return len(rows), short
