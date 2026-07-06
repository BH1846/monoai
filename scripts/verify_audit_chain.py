#!/usr/bin/env python3
"""Standalone audit-chain verifier — give this to auditors.

Usage: python scripts/verify_audit_chain.py <path-to-audit.jsonl>
           [--require-signed] [--public-key <hex>]
Exits 0 if the hash chain (and, when requested, every record's Ed25519
signature) verifies, 1 if tampering / an unsigned entry is detected.

--require-signed rejects the file outright if any record lacks a
signature (G13's reading-side enforcement) -- pair with --public-key to
also cryptographically verify each signature, not just check presence.
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="path to audit.jsonl")
    parser.add_argument(
        "--require-signed", action="store_true",
        help="reject the file if any record is missing a signature (G13)",
    )
    parser.add_argument(
        "--public-key", default=None,
        help="hex Ed25519 public key -- if given, verify every record's signature, not just its presence",
    )
    args = parser.parse_args()

    from audit.chain import verify
    from audit.sinks import UnsignedAuditRecordError, read_jsonl

    try:
        records = read_jsonl(args.path, require_signature=args.require_signed)
    except UnsignedAuditRecordError as err:
        print(f"UNSIGNED: {err}")
        return 1

    ok = verify(records, public_key_hex=args.public_key)
    print("OK: chain verifies" if ok else "TAMPERED: chain does not verify")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
