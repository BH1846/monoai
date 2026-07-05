#!/usr/bin/env python3
"""Standalone audit-chain verifier — give this to auditors.

Usage: python scripts/verify_audit_chain.py <path-to-audit.jsonl>
Exits 0 if the hash chain verifies, 1 if tampering is detected.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_audit_chain.py <path-to-audit.jsonl>", file=sys.stderr)
        return 2

    from audit.chain import verify
    from audit.sinks import read_jsonl

    records = read_jsonl(sys.argv[1])
    ok = verify(records)
    print("OK: chain verifies" if ok else "TAMPERED: chain does not verify")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
