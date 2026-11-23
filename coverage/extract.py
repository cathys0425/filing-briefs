"""Map step: read one chunk of one document and return notes backed by verbatim quotes."""
import hashlib
import json
import os
import re
import time

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


def request(label, text, model):
    """(cache file, prompt) for one chunk. The cache is keyed by model + prompt, which includes the text."""
    prompt = PROMPT.format(categories=CATEGORIES, label=label, text=text)
    return os.path.join(CACHE, "notes-" + hashlib.sha1((model + prompt).encode()).hexdigest() + ".json"), prompt


def extract(label, text, model, complete):
    """Notes for one chunk, cached on disk by model + prompt + text. `cost` is 0 when served from the cache."""
    path, prompt = request(label, text, model)
    if os.path.exists(path):
        with open(path) as f:
            return {"notes": json.load(f)["notes"], "cost": 0}
    reply, usage, _ = complete([{"role": "user", "content": prompt}], model)
    result = {"notes": parse_notes(reply), "cost": usage.get("cost")}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f)
    return result


PENDING = "pending-batch.json"  # in CACHE: the batch submitted but not yet collected
FINAL = {"completed", "failed", "expired", "cancelled"}


def batch(pending, model, submit, get, wait=60):
    """Fill the notes cache for {cache file: prompt} through one asynchronous batch.

    The batch id is saved before waiting, so an interrupted run collects the same batch
    when started again instead of paying for a second one. A request that fails or returns
    malformed notes leaves no cache file; the normal run then extracts it at the sync price.
    Returns (requests filled, requests not filled, cost).
    """
    state = os.path.join(CACHE, PENDING)
    if os.path.exists(state):
        with open(state) as f:
            saved = json.load(f)
        if saved["model"] != model:
            raise RuntimeError(f"A batch for {saved['model']} is still pending ({saved['id']}); "
                               f"run with that model again to collect it, or delete {state}.")
        batch_id, paths = saved["id"], saved["paths"]
        print(f"Resuming batch {batch_id} ({len(paths)} requests)")
    else:
        if not pending:
            return 0, 0, 0.0
        paths = {hashlib.sha1(p.encode()).hexdigest(): p for p in pending}
        batch_id = submit(model, {k: {"messages": [{"role": "user", "content": pending[p]}]} for k, p in paths.items()})
        os.makedirs(CACHE, exist_ok=True)
        with open(state, "w") as f:
            json.dump({"id": batch_id, "model": model, "paths": paths}, f)
        print(f"Submitted batch {batch_id}: {len(paths)} requests")
    while True:
        b = get(batch_id)
        # a completed batch can briefly report results as null while they are written
        if b["status"] in FINAL and (b["status"] != "completed" or b["results"] is not None):
            break
        print(f"Batch {batch_id}: {b['status']} {b.get('request_counts')}")
        time.sleep(wait)
    os.remove(state)
    if b["status"] != "completed":
        raise RuntimeError(f"Batch {batch_id} ended as {b['status']}: {(b.get('error') or {}).get('message')}")
    filled = 0
    for r in b["results"]:
        try:
            notes = parse_notes(r["response"]["body"]["choices"][0]["message"]["content"] or "")
        except (TypeError, KeyError, IndexError, ValueError):
            continue  # request error, empty reply or malformed notes
        with open(paths[r["custom_id"]], "w") as f:
            json.dump({"notes": notes, "cost": None}, f)
        filled += 1
    return filled, len(paths) - filled, (b.get("usage") or {}).get("cost") or 0.0
