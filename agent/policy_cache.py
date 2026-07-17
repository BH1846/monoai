"""Local policy cache: the agent pulls SENTINEL policy from the manager on
an interval, caches it on local disk, and enforces it WITHOUT a per-request
round-trip.

Version handling is the subtle part. The manager's content-hash version
string is authoritative; the agent stores it verbatim (in policy_meta.json)
and reports it back on /heartbeat and /ingest so drift detection lines up
exactly. The agent does NOT re-hash its own YAML rendering (that would
produce a different string and make every agent look permanently drifted).
The YAML body is only used to reconstruct a core/policy Policy object for
local evaluation.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from policy.schema import Policy

_POLICY_YAML = "policy.yaml"
_POLICY_META = "policy_meta.json"


class PolicyCache:
    def __init__(self, state_dir: str) -> None:
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._policy: Policy | None = None
        self._version: str = ""
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        meta_p = self._dir / _POLICY_META
        yaml_p = self._dir / _POLICY_YAML
        if not (meta_p.is_file() and yaml_p.is_file()):
            return
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        data = yaml.safe_load(yaml_p.read_text(encoding="utf-8")) or {}
        self._version = meta.get("version", "")
        self._policy = Policy(**data, version=self._version)

    def update(self, policy_yaml: str, version: str) -> None:
        """Persist a freshly pulled policy + its manager-authoritative
        version, and build the in-memory Policy used for local evaluation."""
        (self._dir / _POLICY_YAML).write_text(policy_yaml, encoding="utf-8")
        (self._dir / _POLICY_META).write_text(json.dumps({"version": version}), encoding="utf-8")
        data = yaml.safe_load(policy_yaml) or {}
        self._policy = Policy(**data, version=version)
        self._version = version

    @property
    def policy(self) -> Policy | None:
        return self._policy

    @property
    def version(self) -> str:
        return self._version

    @property
    def ready(self) -> bool:
        return self._policy is not None
