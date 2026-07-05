"""PolicyStore: versioned policies loaded from YAML, content-hash = version."""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from policy.schema import Policy


class PolicyLoadError(Exception):
    pass


def _content_hash(raw: str) -> str:
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PolicyStore:
    def __init__(self) -> None:
        self._policies: dict[str, dict[str, Policy]] = {}
        self._latest_version: dict[str, str] = {}

    def load_file(self, path: str | Path) -> Policy:
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        version = _content_hash(raw)
        data = yaml.safe_load(raw) or {}
        try:
            policy = Policy(**data, version=version)
        except ValidationError as exc:
            raise PolicyLoadError(f"invalid policy YAML at {path}: {exc}") from exc

        self._policies.setdefault(policy.policy_id, {})[version] = policy
        self._latest_version[policy.policy_id] = version
        return policy

    def load_dir(self, directory: str | Path) -> list[Policy]:
        loaded = []
        for yaml_path in sorted(Path(directory).glob("*.yaml")):
            loaded.append(self.load_file(yaml_path))
        return loaded

    def get(self, policy_id: str, version: str | None = None) -> Policy:
        if policy_id not in self._policies:
            raise KeyError(f"unknown policy_id: {policy_id!r}")
        version = version or self._latest_version[policy_id]
        return self._policies[policy_id][version]

    def latest_version(self, policy_id: str) -> str:
        return self._latest_version[policy_id]
