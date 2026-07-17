"""Standalone agent entrypoint.

    uv run python -m agent            # from the repo root (workspace)
or, with the agent dir on sys.path:
    python __main__.py

Two modes:
  * default: enroll (if needed) and run the daemon loop forever.
  * --demo "<text>": enroll, pull policy, run local SENTINEL over the given
    text, buffer + sync the one event, print the result, and exit. Useful
    for verifying an enrolled agent end-to-end without wiring a traffic tap.

The agent is fully independent of the manager's DB/filesystem: it only needs
MANAGER_URL, an AGENT_ENROLL_TOKEN on first run, and a local AGENT_STATE_DIR.
"""
from __future__ import annotations

import sys

from agent_config import load_settings
from client import ManagerUnreachable
from enroll import EnrollmentRequired
from runner import AgentRunner


def main(argv: list[str]) -> int:
    settings = load_settings()
    runner = AgentRunner(settings)
    try:
        try:
            runner.start()
        except EnrollmentRequired as err:
            print(f"[agent] not enrolled: {err}", file=sys.stderr)
            return 2
        except ManagerUnreachable as err:
            # First-run enrollment genuinely requires the manager to be
            # reachable; report cleanly instead of a stack trace.
            print(f"[agent] manager unreachable during enrollment: {err}", file=sys.stderr)
            return 3

        print(f"[agent] enrolled as {runner.identity.agent_id} -> manager {settings.manager_url}")

        if len(argv) >= 2 and argv[0] == "--demo":
            text = argv[1]
            if runner.observe(text):
                acked = runner.sync_once()
                print(f"[agent] observed 1 event, manager acked {acked}")
            else:
                print("[agent] no policy cached yet -- could not evaluate (is the manager reachable?)")
            return 0

        print("[agent] entering daemon loop (ctrl-c to stop)")
        runner.run_forever()
        return 0
    finally:
        runner.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
