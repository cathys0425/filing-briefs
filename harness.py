#!/usr/bin/env python3
"""Step 1 of the eval harness: run every task against every model and record raw results.

  python3 harness.py -m MODEL_A MODEL_B [--tasks tasks.jsonl] [--out results.jsonl]

No scoring yet. Each line of the output file is one (task, model) pair.
"""
import argparse
import json

from orc import APIError, complete


def load_tasks(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def run_one(task, model):
    """Run a single task on a single model. Never raises: errors are recorded as data."""
    row = {"task_id": task["id"], "model": model, "expected": task.get("expected")}
    try:
        text, usage, seconds = complete([{"role": "user", "content": task["prompt"]}], model)
        row.update(output=text, error=None, seconds=round(seconds, 2),
                   tokens=usage.get("total_tokens"), cost=usage.get("cost", 0))
    except APIError as e:
        row.update(output=None, error=str(e), seconds=None, tokens=None, cost=None)
    return row


def main():
    p = argparse.ArgumentParser(description="Run tasks x models and save raw results")
    p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--tasks", default="tasks.jsonl")
    p.add_argument("--out", default="results.jsonl")
    a = p.parse_args()

    tasks = load_tasks(a.tasks)
    with open(a.out, "w") as f:
        for task in tasks:
            for model in a.models:
                row = run_one(task, model)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()  # a crash halfway still leaves the finished rows on disk
                shown = row["error"] or row["output"].replace("\n", " ")[:60]
                print(f"{row['task_id']:<10} {model:<40} {shown}")
    print(f"\n{len(tasks)} tasks x {len(a.models)} models -> {a.out}")


if __name__ == "__main__":
    main()
