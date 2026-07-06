"""Evidence export: hash-chained JSONL bundle, Ed25519-signed (G10).

An auditor with only the public key can verify the bundle offline --
they never need this deployment's private signing key.
"""
from __future__ import annotations

import json

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from contracts.audit import AuditRecord

from audit.chain import verify


def export(records: list[AuditRecord]) -> bytes:
    manifest = {
        "record_count": len(records),
        "chain_verified": verify(records),
    }
    lines = [json.dumps(manifest, sort_keys=True)]
    lines.extend(record.model_dump_json() for record in records)
    return ("\n".join(lines) + "\n").encode("utf-8")


def sign_evidence(bundle: bytes, signing_key: SigningKey) -> dict[str, str]:
    """Returns {"signature": hex, "public_key": hex}. Ship both alongside
    the bundle -- verify_signature() only needs the public key."""
    signed = signing_key.sign(bundle)
    return {
        "signature": signed.signature.hex(),
        "public_key": bytes(signing_key.verify_key).hex(),
    }


def verify_signature(bundle: bytes, signature_hex: str, public_key_hex: str) -> bool:
    verify_key = VerifyKey(bytes.fromhex(public_key_hex))
    try:
        verify_key.verify(bundle, bytes.fromhex(signature_hex))
        return True
    except BadSignatureError:
        return False
