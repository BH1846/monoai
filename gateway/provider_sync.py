"""ProviderSyncClient: pulls provider/model config DOWN from the manager.

This is the reverse direction from audit/key forwarding (which go
instance -> manager). Here a forwarding instance periodically polls the
manager's POST /v1/admin/providers/sync and reconciles its LOCAL registry to
match -- the manager is the single source of truth for which providers/models
exist ("manager-exclusive": a syncing instance's registry mirrors only the
manager's, and local provider adds are refused; see api/admin.py).

Security: provider API keys are never on the wire in plaintext. The instance
sends its X25519 Box public key; the manager re-seals each key to it with the
authenticated Box (core/vault/box.py, the Wazuh-agent channel primitive); this
client opens them with its own private key and hands the plaintext to
SqliteProviderStore, which re-encrypts under THIS instance's VaultCrypto.

Resilience: a failed poll (manager down, bad response, crypto failure) leaves
the existing registry untouched -- the instance keeps serving last-known-good
config. Reconciliation only happens on a validated response, and only when the
config actually changed (so cached provider adapters aren't dropped every
poll). Runs on a background daemon thread; never blocks or crashes the gateway.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx
from providers.registry_store import SqliteProviderStore, SyncModel, SyncProvider
from vault.box import open_sealed

logger = logging.getLogger(__name__)


def _provider_signature(providers) -> frozenset:
    """Comparable fingerprint of a provider set. Works for both the manager's
    response dicts and local ProviderRecords (a changed API key shows up as a
    changed key_last4)."""
    out = set()
    for p in providers:
        if isinstance(p, dict):
            out.add((p["provider_id"], p["name"], p["kind"], p["base_url"], bool(p["enabled"]), p.get("key_last4")))
        else:
            out.add((p.provider_id, p.name, p.kind, p.base_url, bool(p.enabled), p.key_last4))
    return frozenset(out)


def _model_signature(models) -> frozenset:
    out = set()
    for m in models:
        if isinstance(m, dict):
            out.add((m["model_id"], m["provider_id"], m["upstream_model"], m["display_name"], bool(m["enabled"])))
        else:
            out.add((m.model_id, m.provider_id, m.upstream_model, m.display_name, bool(m.enabled)))
    return frozenset(out)


class ProviderSyncClient:
    def __init__(
        self,
        sync_url: str,
        admin_key: str,
        instance_private_key_hex: str,
        instance_public_key_hex: str,
        gateway_id: str,
        store: SqliteProviderStore,
        dynamic_router,
        interval_s: float = 60.0,
        timeout: float = 10.0,
        start_worker: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sync_url = sync_url
        self._priv = instance_private_key_hex
        self._pub = instance_public_key_hex
        self._gateway_id = gateway_id
        self._store = store
        self._router = dynamic_router
        self._interval_s = interval_s
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {admin_key}", "Content-Type": "application/json"},
            transport=transport,
        )
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._thread = threading.Thread(target=self._run, name="provider-sync", daemon=True)
            self._thread.start()

    def _run(self) -> None:  # pragma: no cover - exercised via poll_once in tests
        # Pull once promptly on startup, then on the interval.
        while not self._stopped.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 -- the poller must never die
                logger.warning("provider sync poll failed", exc_info=True)
            self._stopped.wait(self._interval_s)

    def poll_once(self) -> bool:
        """Fetch the manager's registry and reconcile if it changed. Returns
        True if the local registry was replaced. Any failure returns False and
        leaves the local registry untouched (last-known-good)."""
        try:
            resp = self._client.post(self._sync_url, json={"gateway_id": self._gateway_id, "pubkey": self._pub})
        except httpx.HTTPError as err:
            logger.warning("provider sync: manager unreachable (%s)", err)
            return False
        if resp.status_code >= 400:
            logger.warning("provider sync: manager returned %s", resp.status_code)
            return False
        data = resp.json()

        # Change detection first (cheap, avoids re-decrypting keys and dropping
        # adapter caches every poll when nothing changed).
        remote_providers = data.get("providers", [])
        remote_models = data.get("models", [])
        if (
            _provider_signature(remote_providers) == _provider_signature(self._store.list_providers())
            and _model_signature(remote_models) == _model_signature(self._store.list_models())
        ):
            return False

        manager_gateway_id = data.get("manager_gateway_id")
        manager_pubkey = data.get("manager_pubkey")
        if not manager_gateway_id or not manager_pubkey:
            logger.warning("provider sync: response missing manager identity; skipping")
            return False

        try:
            providers = [self._to_sync_provider(p, manager_pubkey) for p in remote_providers]
        except Exception:  # noqa: BLE001 -- a bad/forged sealed key must not wipe the registry
            logger.warning("provider sync: failed to open a sealed provider key; skipping this cycle", exc_info=True)
            return False
        models = [
            SyncModel(
                model_id=m["model_id"], provider_id=m["provider_id"], upstream_model=m["upstream_model"],
                display_name=m["display_name"], enabled=bool(m["enabled"]),
                created_at=float(m.get("created_at") or time.time()),
            )
            for m in remote_models
        ]

        self._store.replace_registry(manager_gateway_id, providers, models)
        # Config changed -> drop cached adapters so a changed base_url/key is
        # picked up on the next request (resolve() reads the store live).
        self._router.invalidate()
        logger.info("provider sync: reconciled %d providers / %d models from %s",
                    len(providers), len(models), manager_gateway_id)
        return True

    def _to_sync_provider(self, p: dict, manager_pubkey: str) -> SyncProvider:
        api_key = None
        sealed = p.get("sealed_api_key")
        if sealed:
            api_key = open_sealed(self._priv, manager_pubkey, sealed["nonce"], sealed["ciphertext"])
        return SyncProvider(
            provider_id=p["provider_id"], name=p["name"], kind=p["kind"], base_url=p["base_url"],
            api_key=api_key, enabled=bool(p["enabled"]), created_at=float(p.get("created_at") or time.time()),
        )

    def close(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._client.close()
