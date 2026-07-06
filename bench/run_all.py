#!/usr/bin/env python3
"""Runs all bench scripts and writes bench/REPORT.md."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import run_latency_bench
import run_pii_bench
import run_router_bench

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    sections = [
        f"# MonoAI Gateway 2.0 — Bench Report\n\nGenerated: {datetime.now(timezone.utc).isoformat()}\n",
        "See `DECISIONS.md` for the honest caveats on corpus size/curation "
        "and the TF-IDF-classifier-instead-of-transformer substitutions "
        "behind these numbers.\n",
        run_pii_bench.render_markdown(run_pii_bench.run()),
        run_router_bench.render_markdown(run_router_bench.run()),
        run_latency_bench.render_markdown(asyncio.run(run_latency_bench.run())),
    ]

    report_path = REPO_ROOT / "bench" / "REPORT.md"
    report_path.write_text("\n\n".join(sections) + "\n")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
