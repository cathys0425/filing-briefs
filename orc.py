#!/usr/bin/env python3
"""OpenRouter MVP: one file, no dependencies.

  python3 orc.py ask "your question"            one-shot answer
  python3 orc.py chat                           interactive chat (keeps history)
  python3 orc.py compare "prompt" -m A B C      same prompt across models
  python3 orc.py models [--free] [--grep TEXT]  list available models

Key: read from OPENROUTER_API_KEY. In the Claude cloud session the network
proxy injects the real key, so the placeholder default works there.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
KEY = os.environ.get("OPENROUTER_API_KEY", "proxy-injected")
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "recursive/flint-v1.0:free")


class APIError(Exception):
    retryable = False


def call(path, payload=None, timeout=120, retries=3):
    """POST/GET with retry on rate limits (429) and provider hiccups (5xx)."""
    for attempt in range(retries + 1):
        try:
            return _call_once(path, payload, timeout)
        except APIError as e:
            if not e.retryable or attempt == retries:
                raise
            time.sleep(2 ** attempt * 2)  # 2s, 4s, 8s


def _call_once(path, payload, timeout):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            msg = json.loads(raw)["error"]["message"]
        except Exception:
            msg = raw[:300]
        err = APIError(f"HTTP {e.code}: {msg}")
        err.retryable = e.code == 429 or e.code >= 500
        raise err from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise APIError(f"network error: {getattr(e, 'reason', e)}") from None
    if isinstance(body, dict) and body.get("error"):  # OpenRouter can return errors with HTTP 200
        raise APIError(str(body["error"].get("message", body["error"])))
    return body


def complete(messages, model, max_tokens=None, temperature=None):
    """Return (text, usage dict, seconds)."""
    payload = {"model": model, "messages": messages}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    t = time.time()
    body = call("/chat/completions", payload)
    choice = body["choices"][0]
    text = (choice["message"].get("content") or "").strip()
    if not text:  # reasoning models can spend the whole token budget thinking
        why = "hit --max-tokens before answering; raise or drop it" if choice.get("finish_reason") == "length" else f"finish_reason={choice.get('finish_reason')}"
        raise APIError(f"empty reply ({why})")
    return text, body.get("usage", {}), time.time() - t


def build_messages(prompt, system):
    msgs = [{"role": "system", "content": system}] if system else []
    return msgs + [{"role": "user", "content": prompt}]


def read_prompt(arg):
    if arg and arg != "-":
        return arg
    if sys.stdin.isatty():
        sys.exit("Give a prompt as an argument, or pipe text in.")
    return sys.stdin.read().strip()


def cmd_ask(a):
    text, usage, secs = complete(build_messages(read_prompt(a.prompt), a.system), a.model, a.max_tokens, a.temperature)
    print(text)
    print(f"\n[{a.model} | {usage.get('total_tokens', '?')} tokens | ${usage.get('cost', 0):.6f} | {secs:.1f}s]", file=sys.stderr)


def cmd_chat(a):
    msgs = [{"role": "system", "content": a.system}] if a.system else []
    print(f"Chatting with {a.model}. Commands: /reset, /model NAME, /quit")
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return
        if line == "/reset":
            msgs = msgs[:1] if a.system else []
            print("(history cleared)")
            continue
        if line.startswith("/model"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                a.model = parts[1]
            print(f"(model: {a.model})")
            continue
        msgs.append({"role": "user", "content": line})
        try:
            text, _, _ = complete(msgs, a.model, a.max_tokens, a.temperature)
        except APIError as e:
            msgs.pop()
            print(f"error: {e}")
            continue
        msgs.append({"role": "assistant", "content": text})
        print(f"\n{a.model}> {text}")


def cmd_compare(a):
    msgs = build_messages(read_prompt(a.prompt), a.system)

    def run(model):
        try:
            return model, complete(msgs, model, a.max_tokens, a.temperature), None
        except APIError as e:
            return model, None, str(e)

    with cf.ThreadPoolExecutor(max_workers=len(a.models)) as ex:
        results = list(ex.map(run, a.models))
    for model, ok, err in results:
        print(f"\n===== {model} =====")
        if err:
            print(f"FAILED: {err}")
        else:
            text, usage, secs = ok
            print(text)
            print(f"-- {usage.get('total_tokens', '?')} tokens | ${usage.get('cost', 0):.6f} | {secs:.1f}s")
    if a.out:
        rows = [
            {"model": m, "error": err, "text": ok[0] if ok else None,
             "usage": ok[1] if ok else None, "seconds": round(ok[2], 2) if ok else None}
            for m, ok, err in results
        ]
        with open(a.out, "w") as f:
            json.dump({"messages": msgs, "results": rows}, f, indent=2)
        print(f"\nSaved to {a.out}")
    if all(err for _, _, err in results):
        sys.exit(1)


def cmd_models(a):
    rows = call("/models")["data"]
    if a.free:
        rows = [m for m in rows if m["id"].endswith(":free")]
    if a.grep:
        rows = [m for m in rows if a.grep.lower() in m["id"].lower()]
    for m in sorted(rows, key=lambda m: m["id"]):
        p = m.get("pricing", {})
        try:
            price = f"${float(p.get('prompt', 0)) * 1e6:.2f} in / ${float(p.get('completion', 0)) * 1e6:.2f} out per 1M"
        except (TypeError, ValueError):
            price = "price n/a"
        print(f"{m['id']:<55} ctx {m.get('context_length') or '?':>8}  {price}")
    print(f"\n{len(rows)} models", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="OpenRouter MVP client")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, multi=False):
        if multi:
            sp.add_argument("-m", "--models", nargs="+", required=True, help="model ids to compare")
        else:
            sp.add_argument("-m", "--model", default=DEFAULT_MODEL)
        sp.add_argument("-s", "--system", help="system prompt")
        sp.add_argument("--max-tokens", type=int)
        sp.add_argument("--temperature", type=float)

    sp = sub.add_parser("ask", help="one-shot answer"); sp.add_argument("prompt", nargs="?"); common(sp); sp.set_defaults(fn=cmd_ask)
    sp = sub.add_parser("chat", help="interactive chat"); common(sp); sp.set_defaults(fn=cmd_chat)
    sp = sub.add_parser("compare", help="same prompt, several models"); sp.add_argument("prompt", nargs="?"); common(sp, multi=True)
    sp.add_argument("-o", "--out", help="save results as JSON"); sp.set_defaults(fn=cmd_compare)
    sp = sub.add_parser("models", help="list models"); sp.add_argument("--free", action="store_true"); sp.add_argument("--grep"); sp.set_defaults(fn=cmd_models)

    a = p.parse_args()
    try:
        a.fn(a)
    except APIError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
