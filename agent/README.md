# SENTINEL Agent — standalone edge process (Wazuh-style manager/agent split)

A lightweight, **standalone** process meant to run on OTHER machines than the
gateway. It enrolls once with the manager (the existing gateway), then runs
**semi-autonomously**:

- runs **SENTINEL Tier 0** (regex + secrets) and **Tier 1** (ONNX NER)
  detection locally, against local traffic/files
- **buffers** events durably when the manager is unreachable and **replays
  them in order** on reconnect
- **pulls policy** on an interval and enforces it locally, with **no
  round-trip per request**
- sends a **heartbeat** on an interval

The agent reuses `monoai-core` as a **library** — the exact same
`DetectionPipeline` and `PolicyEngine` the gateway, `filescan-worker`, and
`mcp-firewall` use. It has **no dependency** on the manager's database,
filesystem, or Valkey.

## Security boundary (hard requirement)

The agent generates its **own** X25519 keypair on its own host at enroll
time, and only ever holds:

1. its **own private key** (never transmitted, stored `0600` in the state dir)
2. the **manager's public key** (received in the enroll response)

It **never** has the manager's Valkey master keypair or any vault key
material — enforced structurally: `agent_config.py` has no Valkey/vault
knobs, and the crypto helper (`core/vault/box.py`) takes raw key material
only. All agent→manager `/ingest` traffic is sealed with an **authenticated**
PyNaCl `Box` (agent privkey + manager pubkey), so the manager verifies the
sender against the agent's registered pubkey — an anonymous `SealedBox`
could not do that.

**What runs where.** Tier 0/1 detection runs on the agent. Tier 2 (the LLM
injection judge) stays **manager-side** — it needs network egress + provider
keys. Vault, policy *authoring*, the hash-chained audit log, and the admin
dashboard are all manager-only.

## Enroll + run

On the **manager**, mint a one-time enrollment token (admin-gated, reuses
`MONOAI_ADMIN_KEY`):

```bash
curl -s -X POST http://MANAGER:8000/v1/admin/agents/enroll-token \
  -H "Authorization: Bearer $MONOAI_ADMIN_KEY"
# -> {"token": "et-...", "expires_at": ...}
```

On the **agent host** (a different machine), set the env and run:

```bash
export MANAGER_URL=http://MANAGER:8000
export AGENT_ENROLL_TOKEN=et-...        # only needed on first run
export AGENT_STATE_DIR=./agent_state    # keypair, buffer, cached policy live here

uv run python -m agent                  # enroll (first run) + run the daemon loop
# or verify end-to-end without a traffic tap:
uv run python -m agent --demo "email me at jane@example.com"
```

After first run, `AGENT_STATE_DIR/identity.json` holds the agent's identity;
the token is consumed and no longer needed. Re-running is idempotent.

## Config (env)

| Var | Default | Meaning |
|---|---|---|
| `MANAGER_URL` | `http://127.0.0.1:8000` | Manager (gateway) base URL |
| `AGENT_ENROLL_TOKEN` | — | One-time enroll token; first run only |
| `AGENT_POLICY_ID` | `default` | Policy the agent enrolls under |
| `AGENT_HOSTNAME` | `uname().nodename` | Reported to the manager registry |
| `AGENT_STATE_DIR` | `./agent_state` | Local identity + buffer + policy cache |
| `PII_USE_ONNX_NER` | `true` | Tier 1 NER; Tier 0 regex always runs |
| `AGENT_SYNC_INTERVAL_S` | `10` | Buffer→`/ingest` drain interval |
| `AGENT_POLICY_POLL_INTERVAL_S` | `60` | `/policy` pull interval |
| `AGENT_HEARTBEAT_INTERVAL_S` | `30` | `/heartbeat` interval |
| `AGENT_INGEST_BATCH_SIZE` | `200` | Max events per `/ingest` call |

## Layout

```
agent/
  agent_config.py   env-driven settings (NO Valkey/vault knobs — the boundary)
  identity.py       keypair gen + local identity state (0600)
  buffer.py         durable append-only SQLite event queue (ordered replay)
  client.py         outbound HTTP to the manager; seals /ingest with Box
  enroll.py         idempotent first-run enrollment
  sentinel.py       LocalSentinel: Tier 0/1 via core DetectionPipeline (unmodified)
  policy_cache.py   pull + cache policy; enforce locally, no per-request round-trip
  runner.py         AgentRunner: observe / sync_once / poll_policy_once / heartbeat_once
  __main__.py       standalone entrypoint (daemon loop or --demo)
```

The `observe()` method on `AgentRunner` is the **ingestion seam**. A real
deployment wires it to a local traffic tap or file watcher; that host
integration — plus a **Windows agent**, **FIM/rootkit parity**, and **TEE
attestation** for the private key — is explicitly **out of scope** this pass.
