#!/usr/bin/env python3
"""Generates bench/corpora/routing_labeled.jsonl — a small English-only
starter corpus for the G7 embedding-style router classifier. Same caveat
as the injection corpus: template-generated, not production-curated."""
from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(7)

_SIMPLE_TEMPLATES = [
    "Hi, how are you?",
    "What's the weather like?",
    "Thanks for your help!",
    "What time is it?",
    "Hello there.",
    "Can you say hi to {name}?",
    "What is {n} plus {n2}?",
    "Tell me a joke.",
    "What's your name?",
    "Good morning!",
]

_MODERATE_TEMPLATES = [
    "Write a Python function to reverse a {thing}.",
    "Can you help me debug this {lang} error?",
    "Explain how a {ds} works.",
    "Write a SQL query to find duplicate rows in a table.",
    "Implement a cache with a simple eviction policy.",
    "How do I write unit tests for a {lang} function?",
    "Refactor this code to use a {ds} instead of a list.",
    "Write a function to calculate {n}th Fibonacci number with error handling.",
    "Design a simple REST API endpoint for {thing}.",
    "Explain the difference between {lang} and another language.",
]

_COMPLEX_TEMPLATES = [
    "Design a thread-safe, async, distributed cache with unit tests and error handling, "
    "and prove its correctness step by step.",
    "Prove that there are infinitely many prime numbers, step by step.",
    "Design a system architecture for a distributed, fault-tolerant message queue, "
    "explaining the trade-offs at each step.",
    "Derive the time complexity of merge sort step by step and optimize it for concurrent execution.",
    "Design a thread-safe rate limiter with distributed state, unit tests, and error handling.",
    "Walk me through, step by step, how to design a fault-tolerant distributed system "
    "with async replication and error handling.",
    "Prove the correctness of a distributed consensus algorithm step by step.",
    "Design and implement a thread-safe, async job scheduler with comprehensive error handling and unit tests.",
]

_NAMES = ["Alex", "Sam", "Priya", "Jordan"]
_THINGS = ["linked list", "array", "string", "binary tree"]
_LANGS = ["Python", "JavaScript", "Rust", "Go"]
_DS = ["hash map", "binary search tree", "queue", "stack"]


def _fill(template: str) -> str:
    return template.format(
        name=random.choice(_NAMES), n=random.randint(1, 20), n2=random.randint(1, 20),
        thing=random.choice(_THINGS), lang=random.choice(_LANGS), ds=random.choice(_DS),
    )


def main() -> None:
    rows = []
    for _ in range(40):
        rows.append({"text": _fill(random.choice(_SIMPLE_TEMPLATES)), "difficulty": "simple"})
    for _ in range(40):
        rows.append({"text": _fill(random.choice(_MODERATE_TEMPLATES)), "difficulty": "moderate"})
    for _ in range(40):
        rows.append({"text": random.choice(_COMPLEX_TEMPLATES), "difficulty": "complex"})

    out_path = Path(__file__).parent / "routing_labeled.jsonl"
    with open(out_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(rows)} labeled routing examples to {out_path}")


if __name__ == "__main__":
    main()
