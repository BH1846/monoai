#!/usr/bin/env python3
"""Interactive REPL for the monoai gateway.

Usage: python chat.py
Requires the gateway server running (see README): uvicorn monoai_gateway.app:app --port 8000
"""
import sys

import httpx

URL = "http://127.0.0.1:8000/v1/chat/completions"


def main() -> None:
    print("monoai gateway chat -- Ctrl+C or Ctrl+D to quit")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not prompt:
            continue

        try:
            resp = httpx.post(URL, json={"messages": [{"role": "user", "content": prompt}]}, timeout=60)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"error: {e}", file=sys.stderr)
            continue

        data = resp.json()
        meta = data.get("monoai", {})
        usage = data.get("usage", {})

        print(f"  [1] masked prompt sent to LLM : {meta.get('sanitized_prompt')}")
        print(f"  [2] model selected            : {data.get('model')} ({meta.get('provider')}/{meta.get('difficulty')} tier)")
        print(f"  [3] raw LLM output (masked)   : {meta.get('raw_model_output')}")
        print(f"  [4] rehydrated final answer   : {data['choices'][0]['message']['content']}")
        cost = meta.get("cost_usd")
        cost_str = f"${cost:.6f}" if cost is not None else "n/a (provider doesn't report cost)"
        print(f"  [5] tokens: {usage.get('total_tokens')} (prompt {usage.get('prompt_tokens')} + completion {usage.get('completion_tokens')})  cost: {cost_str}")
        if meta.get("review_required"):
            print(f"  [!] review required, unresolved tokens: {meta.get('unresolved_tokens')}")


if __name__ == "__main__":
    main()
