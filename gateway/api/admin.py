"""Admin CRUD: keys, policy reload, budgets. Gated behind a single
MONOAI_ADMIN_KEY bearer -- same single-shared-secret pattern used
elsewhere in this codebase (MONOAI_BEARER_TOKEN historically), scoped
only to admin operations, not the chat endpoint.
"""
from __future__ import annotations

from typing import Any

from contracts.audit import AuditRecord
from fastapi import APIRouter, Header, HTTPException, Request
from key_events import KeyForwardEvent, KeyRevokeEvent
from key_forward_hook import forward_key_event as _forward_key_event
from pydantic import ValidationError
from vault.box import seal as box_seal

router = APIRouter()


def _check_admin(authorization: str | None, admin_key: str | None) -> None:
    if not admin_key:
        raise HTTPException(status_code=403, detail="admin endpoints disabled (MONOAI_ADMIN_KEY not set)")
    if authorization != f"Bearer {admin_key}":
        raise HTTPException(status_code=401, detail="missing or invalid admin key")


def _reject_if_provider_synced(request: Request) -> None:
    """On a syncing instance the manager is the exclusive source of truth for
    providers/models, so local add/delete is refused -- otherwise a local edit
    would be silently wiped on the next sync. Configure providers on the
    manager instead."""
    if getattr(request.app.state, "provider_sync", None) is not None:
        raise HTTPException(
            status_code=409,
            detail="providers/models are managed centrally on the manager (this instance syncs them); "
                   "configure them on the manager gateway",
        )


@router.post("/v1/admin/keys")
async def create_key(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    raw_key, key = key_store.create_key(
        team_id=body.get("team_id"),
        policy_id=body.get("policy_id", "default"),
        model_allowlist=body.get("model_allowlist"),
        budget_usd_monthly=body.get("budget_usd_monthly"),
        rate_limit_rps=body.get("rate_limit_rps", 5.0),
        rate_limit_burst=body.get("rate_limit_burst", 20),
    )
    # Forward the newly-created key to the manager (visibility in its Users
    # tab). Never carries the raw key -- only the VirtualKey (hash, not secret).
    _forward_key_event(request, "created", key.key_id, key=key)
    return {"key": raw_key, "key_id": key.key_id, "policy_id": key.policy_id, "team_id": key.team_id}


@router.get("/v1/admin/keys")
async def list_keys(
    request: Request,
    team_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    keys = key_store.list_keys(team_id=team_id)
    return {"keys": [k.model_dump(exclude={"key_hash"}) for k in keys]}


@router.delete("/v1/admin/keys/{key_id}")
async def revoke_key(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store

    # Look up first so we can tell a locally-created key from one forwarded in
    # from a peer -- they revoke differently.
    key = key_store.get_by_id(key_id) if hasattr(key_store, "get_by_id") else None

    if key is not None and key.origin_gateway is not None:
        # A key that belongs to another gateway. Revoke our local (display)
        # copy immediately (optimistic), then propagate the revoke BACK to the
        # origin so it actually stops working there. Forwarding is one-way, so
        # without this the origin would keep honouring the key.
        key_store.revoke(key_id)
        reverse = getattr(request.app.state, "key_reverse_forwarder", None)
        if reverse is None or not key.origin_callback_url:
            # Can't reach the origin (reverse forwarding not configured, or the
            # origin never advertised a callback URL). The local copy is
            # revoked, but the origin still honours the key -- report honestly.
            return {
                "revoked": key_id, "origin_gateway": key.origin_gateway,
                "propagated": False,
                "detail": "local copy revoked; could not reach origin gateway to propagate",
            }
        event = KeyRevokeEvent(key_id=key_id, gateway_id=request.app.state.settings.gateway_id)
        payload = event.model_dump(mode="json")
        payload["_target_url"] = key.origin_callback_url.rstrip("/") + "/v1/admin/keys/revoke-ingest"
        reverse.enqueue(event.event_id, payload)
        return {"revoked": key_id, "origin_gateway": key.origin_gateway, "propagated": True}

    # A locally-created key: revoke it, and forward the revoke to the manager
    # so its copy reflects the change too.
    key_store.revoke(key_id)
    _forward_key_event(request, "revoked", key_id)
    return {"revoked": key_id}


@router.get("/v1/admin/transactions")
async def list_transactions(
    request: Request,
    team_id: str | None = None,
    virtual_key_id: str | None = None,
    limit: int = 100,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Per-user prompt/reply history backing the Users-tab drill-down. Returns
    the real Original -> Redacted -> Reply -> Rehydrated flow per request for a
    given virtual key (or team). Admin-gated: the raw prompt/reply text this
    exposes is the most sensitive data the gateway holds."""
    _check_admin(authorization, request.app.state.settings.admin_key)
    store = getattr(request.app.state, "transaction_store", None)
    if store is None:
        return {"transactions": []}
    txns = store.list_transactions(team_id=team_id, virtual_key_id=virtual_key_id, limit=min(limit, 500))
    return {
        "transactions": [
            {
                "id": t.request_id,
                "session_id": t.session_id,
                "timestamp": t.ts,
                "team_id": t.team_id,
                "virtual_key_id": t.virtual_key_id,
                "model": t.model,
                "status": t.status,
                "redactionRulesTriggered": t.redaction_rules,
                "inputTokens": t.input_tokens,
                "outputTokens": t.output_tokens,
                "cost": t.cost,
                "originalPrompt": t.original_prompt,
                "redactedPrompt": t.redacted_prompt,
                "llmReply": t.llm_reply,
                "rehydratedReply": t.rehydrated_reply,
            }
            for t in txns
        ]
    }


@router.post("/v1/admin/account")
async def save_admin_account(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Associates the admin key that was just used to authenticate this
    call with `email`, so a future GET /v1/admin/account/{email} can hand
    it back without the console asking the admin to re-paste it."""
    admin_key = request.app.state.settings.admin_key
    _check_admin(authorization, admin_key)
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    request.app.state.admin_account_store.save(email, admin_key)
    return {"email": email, "saved": True}


@router.get("/v1/admin/account/{email}")
async def get_admin_account(email: str, request: Request) -> dict[str, Any]:
    """Deliberately unauthenticated -- see gateway/auth/admin_account_store.py
    module docstring for the security tradeoff this accepts."""
    account = request.app.state.admin_account_store.get(email.strip().lower())
    if account is None:
        raise HTTPException(status_code=404, detail="no admin account saved for this email")
    return {"email": account.email, "admin_key": account.admin_key}


@router.post("/v1/admin/audit/ingest")
async def ingest_audit_record(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Accept one AuditRecord forwarded from a PEER gateway instance and
    append it into THIS gateway's own hash chain, so it shows up in the
    Audit Log exactly like a locally-generated record (no parallel store).
    The sender is core/audit/sinks.py's ForwardingSink.

    Trust model: a shared admin key, deliberately -- this is trusted
    gateway-to-gateway (each operator runs their own full Torqk stack), not
    the untrusted-remote-source case that the enrollment/keypair flow in
    api/agents.py exists for.

    `async def` is load-bearing: AuditChain.append() is a read-modify-write
    of the running last_hash and is NOT thread-safe. As an async handler this
    runs on the event loop with no await between read and write, so
    concurrent forwarders can't interleave and corrupt the chain. A plain
    `def` would be handed to FastAPI's threadpool and race.

    Idempotent: delivery is at-least-once, so an already-seen record_id is
    answered 200 (not re-appended), letting the sender dequeue cleanly.
    """
    _check_admin(authorization, request.app.state.settings.admin_key)

    try:
        record = AuditRecord.model_validate(body)
    except ValidationError as err:
        raise HTTPException(status_code=400, detail=f"malformed audit record: {err.error_count()} error(s)")

    dedupe = getattr(request.app.state, "audit_ingest_dedupe", None)
    if dedupe is not None and dedupe.seen(record.record_id):
        return {"accepted": False, "duplicate": True, "record_id": record.record_id}

    # The sender stamps origin_gateway; refuse an unattributed record rather
    # than silently filing a peer's record as locally-generated.
    if not record.origin_gateway:
        raise HTTPException(status_code=400, detail="forwarded record must carry origin_gateway")

    appended = request.app.state.audit_chain.append(record)
    if dedupe is not None:
        dedupe.mark(record.record_id, record.origin_gateway)
    return {
        "accepted": True,
        "duplicate": False,
        "record_id": appended.record_id,
        "origin_gateway": appended.origin_gateway,
        "hash": appended.hash,
    }


@router.post("/v1/admin/keys/ingest")
async def ingest_key_event(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive a key created/revoked event forwarded from a PEER gateway and
    reflect it into THIS gateway's own KeyStore, so the key shows up in the
    Users tab alongside local ones (tagged origin_gateway). Sibling of
    /v1/admin/audit/ingest; same shared-admin-key trust model + dedupe.

    A forwarded key is visibility-only -- authenticate() (auth/middleware.py)
    refuses any key with origin_gateway set, so mirroring a peer's key here
    never makes it valid against this gateway.
    """
    _check_admin(authorization, request.app.state.settings.admin_key)

    try:
        event = KeyForwardEvent.model_validate(body)
    except ValidationError as err:
        raise HTTPException(status_code=400, detail=f"malformed key event: {err.error_count()} error(s)")

    if not event.gateway_id:
        raise HTTPException(status_code=400, detail="forwarded key event must carry gateway_id")

    dedupe = getattr(request.app.state, "key_ingest_dedupe", None)
    if dedupe is not None and dedupe.seen(event.event_id):
        return {"accepted": False, "duplicate": True, "event_id": event.event_id}

    key_store = request.app.state.key_store
    if event.event_type == "created":
        if event.key is None:
            raise HTTPException(status_code=400, detail="created event must include the key body")
        # Stamp provenance so this row is a foreign, visibility-only copy and
        # is reverse-revocable back to its origin.
        forwarded = event.key.model_copy(update={
            "origin_gateway": event.gateway_id,
            "origin_callback_url": event.callback_url,
        })
        key_store.add_forwarded_key(forwarded)
    else:  # revoked
        key_store.revoke(event.key_id)

    if dedupe is not None:
        dedupe.mark(event.event_id, event.gateway_id)
    return {"accepted": True, "duplicate": False, "event_id": event.event_id, "origin_gateway": event.gateway_id}


@router.post("/v1/admin/keys/revoke-ingest")
async def revoke_ingest_key(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive a REVERSE revoke pushed by a manager (which revoked a key this
    gateway had forwarded to it) and apply it to THIS gateway's own KeyStore,
    so the key actually stops working here.

    Deliberately does NOT re-forward the revoke -- that would loop back to the
    manager, which already marked its own copy when it initiated the revoke.
    Deduped on event_id (at-least-once delivery).
    """
    _check_admin(authorization, request.app.state.settings.admin_key)

    try:
        event = KeyRevokeEvent.model_validate(body)
    except ValidationError as err:
        raise HTTPException(status_code=400, detail=f"malformed revoke event: {err.error_count()} error(s)")

    dedupe = getattr(request.app.state, "key_revoke_ingest_dedupe", None)
    if dedupe is not None and dedupe.seen(event.event_id):
        return {"accepted": False, "duplicate": True, "event_id": event.event_id}

    request.app.state.key_store.revoke(event.key_id)  # no re-forward: breaks the loop
    if dedupe is not None:
        dedupe.mark(event.event_id, event.gateway_id)
    return {"accepted": True, "duplicate": False, "event_id": event.event_id, "key_id": event.key_id}


@router.post("/v1/admin/providers/sync")
async def providers_sync(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Manager side of provider/model config sync (manager -> instance, the
    OPPOSITE direction from audit/key forwarding). A forwarding instance PULLS
    this gateway's provider/model registry; the manager is the single source
    of truth (gateway/provider_sync.py is the client).

    Trust model: the shared admin key, same as the ingest endpoints. The
    caller supplies its X25519 Box public key; every provider API key is
    DECRYPTED here (from this gateway's own VaultCrypto, which the caller
    can't read) and RE-SEALED to the caller's pubkey with the existing
    authenticated Box (core/vault/box.py) -- keys are never on the wire in
    plaintext. Non-secret config (names, base_urls, model ids) travels as
    plain JSON under the admin-key auth.
    """
    _check_admin(authorization, request.app.state.settings.admin_key)

    instance_pubkey = (body or {}).get("pubkey")
    if not instance_pubkey:
        raise HTTPException(status_code=400, detail="pubkey (the requesting instance's X25519 Box public key) is required")
    try:
        bytes.fromhex(instance_pubkey)
    except ValueError:
        raise HTTPException(status_code=400, detail="pubkey must be hex-encoded")

    store = request.app.state.provider_store
    manager_key = request.app.state.manager_agent_key
    manager_priv_hex = manager_key.encode().hex()
    manager_pubkey_hex = manager_key.public_key.encode().hex()

    providers_out = []
    for p in store.list_providers():
        sealed = None
        plaintext_key = store.get_decrypted_key(p.provider_id)
        if plaintext_key:
            nonce, ciphertext = box_seal(manager_priv_hex, instance_pubkey, plaintext_key)
            sealed = {"nonce": nonce, "ciphertext": ciphertext}
        providers_out.append({
            "provider_id": p.provider_id, "name": p.name, "kind": p.kind, "base_url": p.base_url,
            "enabled": p.enabled, "created_at": p.created_at, "key_last4": p.key_last4,
            "sealed_api_key": sealed,
        })

    models_out = [
        {
            "model_id": m.model_id, "provider_id": m.provider_id, "upstream_model": m.upstream_model,
            "display_name": m.display_name, "enabled": m.enabled, "created_at": m.created_at,
        }
        for m in store.list_models()
    ]

    return {
        "manager_gateway_id": request.app.state.settings.gateway_id,
        "manager_pubkey": manager_pubkey_hex,
        "providers": providers_out,
        "models": models_out,
    }


@router.post("/v1/admin/policies/reload")
async def reload_policies(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    policy_store = request.app.state.policy_store
    loaded = policy_store.load_dir(request.app.state.settings.policy_dir)
    return {"loaded": [{"policy_id": p.policy_id, "version": p.version} for p in loaded]}


@router.delete("/v1/admin/vault/{session_id}")
async def erase_session(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Right-to-erasure API (G11, DPDP/GDPR): permanently deletes every
    vaulted value for a session_id from whichever backend is configured
    (SQLite or Postgres)."""
    _check_admin(authorization, request.app.state.settings.admin_key)
    removed = request.app.state.vault_store.erase_session(session_id)
    return {"session_id": session_id, "erased_count": removed}


@router.post("/v1/admin/vault/sweep-expired")
async def sweep_expired_vault_entries(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """TTL sweeper (G11), triggerable on a schedule (cron/systemd timer)
    against a running gateway rather than needing its own process."""
    _check_admin(authorization, request.app.state.settings.admin_key)
    removed = request.app.state.vault_store.sweep_expired()
    return {"swept_count": removed}


@router.get("/v1/admin/keys/{key_id}")
async def get_key(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    keys = [k for k in request.app.state.key_store.list_keys() if k.key_id == key_id]
    if not keys:
        raise HTTPException(status_code=404, detail="unknown key_id")
    return keys[0].model_dump(exclude={"key_hash"})


@router.post("/v1/admin/providers")
async def create_provider(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    _reject_if_provider_synced(request)
    name = body.get("name")
    kind = body.get("kind")
    base_url = body.get("base_url")
    if not name or not kind or not base_url:
        raise HTTPException(status_code=400, detail="name, kind, and base_url are required")
    try:
        record = request.app.state.provider_store.add_provider(
            name=name, kind=kind, base_url=base_url, api_key=body.get("api_key"),
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {
        "provider_id": record.provider_id, "name": record.name, "kind": record.kind,
        "base_url": record.base_url, "key_last4": record.key_last4, "enabled": record.enabled,
    }


@router.get("/v1/admin/providers")
async def list_providers(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    providers = request.app.state.provider_store.list_providers()
    return {
        "providers": [
            {
                "provider_id": p.provider_id, "name": p.name, "kind": p.kind, "base_url": p.base_url,
                "key_last4": p.key_last4, "enabled": p.enabled, "origin_gateway": p.origin_gateway,
            }
            for p in providers
        ]
    }


@router.delete("/v1/admin/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    _reject_if_provider_synced(request)
    if not request.app.state.provider_store.delete_provider(provider_id):
        raise HTTPException(status_code=404, detail="unknown provider_id")
    return {"deleted": provider_id}


@router.post("/v1/admin/models")
async def create_model(
    request: Request,
    body: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    _reject_if_provider_synced(request)
    store = request.app.state.provider_store
    model_id = body.get("model_id")
    provider_id = body.get("provider_id")
    if not model_id or not provider_id:
        raise HTTPException(status_code=400, detail="model_id and provider_id are required")
    try:
        record = store.add_model(
            model_id=model_id, provider_id=provider_id,
            upstream_model=body.get("upstream_model"), display_name=body.get("display_name"),
        )
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {
        "model_id": record.model_id, "provider_id": record.provider_id, "provider_name": record.provider_name,
        "upstream_model": record.upstream_model, "display_name": record.display_name, "enabled": record.enabled,
    }


@router.get("/v1/admin/models")
async def list_models(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    models = request.app.state.provider_store.list_models()
    return {
        "models": [
            {
                "model_id": m.model_id, "provider_id": m.provider_id, "provider_name": m.provider_name,
                "upstream_model": m.upstream_model, "display_name": m.display_name, "enabled": m.enabled,
                "origin_gateway": m.origin_gateway,
            }
            for m in models
        ]
    }


@router.delete("/v1/admin/models/{model_id}")
async def delete_model(
    model_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    _reject_if_provider_synced(request)
    if not request.app.state.provider_store.delete_model(model_id):
        raise HTTPException(status_code=404, detail="unknown model_id")
    return {"deleted": model_id}


@router.get("/v1/admin/budgets/{key_id}")
async def get_budget(
    key_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_admin(authorization, request.app.state.settings.admin_key)
    key_store = request.app.state.key_store
    keys = [k for k in key_store.list_keys() if k.key_id == key_id]
    if not keys:
        raise HTTPException(status_code=404, detail="unknown key_id")
    key = keys[0]
    return {
        "key_id": key.key_id,
        "budget_usd_monthly": key.budget_usd_monthly,
        "budget_usd_spent": key.budget_usd_spent,
    }
