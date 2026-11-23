"""Map step: read one chunk of one document and return notes backed by verbatim quotes."""
import hashlib
import json
import os
import re

from coverage.text import normalize

CACHE = os.environ.get("COVERAGE_CACHE", "data/cache")
CATEGORIES = ["business_model", "revenue_driver", "kpi", "guidance", "catalyst", "risk", "dataset_idea"]

PROMPT = """You are reading a public company document for an equity research analyst.
Extract only facts that help answer:
- business_model: how the company makes money, who pays, pricing and contract structure
- revenue_driver: segments, volume x price build-up, mix, seasonality, customer concentration
- kpi: operating metrics management reports or emphasizes (units, stores, ARPU, backlog, ...)
- guidance: forward statements with a number or direction
- catalyst: dated or datable events that could change results (launches, contracts, regulation, capacity)
- risk: specific risks, not boilerplate
- dataset_idea: an observable real-world quantity that tracks a revenue driver or KPI above
  (for example foot traffic, app downloads, shipping volumes, web prices, job postings)

Return JSON only: a list of objects {{"category": one of {categories}, "claim": one sentence
in your words, "quote": an exact, contiguous passage copied from the document that supports
the claim}}. For dataset_idea the quote is the passage naming the driver the dataset would track.
Copy quotes character for character. Every number in a claim must appear in its quote, written the
same way (do not convert units or round); extend the quote until it contains the number.
Do not include a note you cannot quote. At most 15 notes.

Document: {label}
---
{text}
"""


def parse_notes(reply):
    """Parse the model's JSON list. Raises ValueError on anything else."""
    start, end = reply.find("["), reply.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("no JSON list in reply")
    notes = json.loads(reply[start:end + 1])
    for n in notes:
        if set(n) != {"category", "claim", "quote"} or n["category"] not in CATEGORIES:
            raise ValueError(f"malformed note: {n}")
    return notes


def numbers(s):
    """Numbers in a string, ignoring years and period labels (Q3, FY2025, H1), which come from the document label."""
    s = re.sub(r"\b(?:Q|FY|H)\s?\d+\b|\b(?:19|20)\d\d\b", " ", s, flags=re.I)
    return {m.replace(",", "").rstrip(".") for m in re.findall(r"\d[\d,]*\.?\d*", s)}


def verify(notes, source):
    """Split notes into (supported, not supported).

    Supported means the quote is found verbatim in the source and every number in the claim
    also appears in the quote, so a quote cannot back a figure it does not contain.
    """
    src = normalize(source)
    ok = [n for n in notes if len(n["quote"]) >= 20 and normalize(n["quote"]) in src
          and numbers(n["claim"]) <= numbers(n["quote"])]
    return ok, [n for n in notes if n not in ok]


def extract(label, text, model, complete):
    """Notes for one chunk, cached on disk by model + prompt + text. `cost` is 0 when served from the cache."""
    prompt = PROMPT.format(categories=CATEGORIES, label=label, text=text)
    path = os.path.join(CACHE, "notes-" + hashlib.sha1((model + prompt).encode()).hexdigest() + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return {"notes": json.load(f)["notes"], "cost": 0}
    reply, usage, _ = complete([{"role": "user", "content": prompt}], model)
    result = {"notes": parse_notes(reply), "cost": usage.get("cost")}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f)
    return result
