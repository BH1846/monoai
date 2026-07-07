"""Tool-call argument scanning + action application (Phase 4 MCP
firewall): directly reuses core/detect's DetectionPipeline (the same
cascade the main gateway and filescan-worker use) over each
string-valued tool-call argument, then applies the per-(tool, arg)
action from rules.py.

Action semantics (deliberately symmetric with core/policy's
Action enum, applied to a whole argument value rather than a per-span
decision):
  - BLOCK: the argument must be completely free of detectable
    PII/secrets, or the WHOLE tool call is refused. Not "always refuse
    this tool" -- that would make exposing the tool pointless.
  - REVERSIBLE: detected spans are tokenized in place (vault-backed,
    same TOKEN_PREFIX/session_tokens mechanism as gateway/pii.py) so
    the value that actually reaches the downstream tool node never
    contains the raw sensitive value.
  - PRESERVE: passed through unmodified -- still scanned, for audit
    visibility, but never blocks or rewrites.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from vault.session_tokens import TOKEN_PREFIX, derive_session_key, make_token_id
from vault.storage.base import VaultStore

from rules import ToolFirewallConfig


class ToolCallBlockedError(Exception):
    def __init__(self, tool_name: str, arg_name: str, span_labels: list[str]) -> None:
        super().__init__(
            f"tool call to {tool_name!r} blocked: argument {arg_name!r} contains "
            f"detected {', '.join(span_labels) or 'sensitive content'}"
        )
        self.tool_name = tool_name
        self.arg_name = arg_name
        self.span_labels = span_labels


@dataclass
class ArgScanResult:
    value: Any  # possibly-rewritten value to forward downstream
    action: str
    span_labels: list[str] = field(default_factory=list)
    token_ids: set[str] = field(default_factory=set)


class ToolFirewall:
    def __init__(
        self,
        pipeline: DetectionPipeline,
        vault: VaultStore,
        config: ToolFirewallConfig,
        server_secret: str,
    ) -> None:
        self._pipeline = pipeline
        self._vault = vault
        self._config = config
        self._server_secret = server_secret

    def scan_call(self, session_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, ArgScanResult]:
        """Scans every string-valued argument; raises
        ToolCallBlockedError on the first BLOCK-triggering match.
        Non-string args (numbers, bools, nested objects) pass straight
        through untouched and aren't included in the result -- core/detect
        operates on text, not arbitrary JSON structure."""
        results: dict[str, ArgScanResult] = {}
        for arg_name, value in arguments.items():
            if not isinstance(value, str):
                continue
            action = self._config.action_for(tool_name, arg_name)
            results[arg_name] = self._scan_one(session_id, tool_name, arg_name, value, action)
        return results

    def _scan_one(
        self, session_id: str, tool_name: str, arg_name: str, value: str, action: str
    ) -> ArgScanResult:
        spans = self._detect(value)
        labels = [s.label.value for s in spans]

        if not spans or action == "PRESERVE":
            return ArgScanResult(value=value, action=action, span_labels=labels)

        if action == "BLOCK":
            raise ToolCallBlockedError(tool_name, arg_name, labels)

        # REVERSIBLE
        session_key = derive_session_key(session_id, self._server_secret)
        ordered = sorted(spans, key=lambda s: s.start)
        out: list[str] = []
        last_end = 0
        token_ids: set[str] = set()
        for span in ordered:
            if span.start < last_end:
                continue
            out.append(value[last_end:span.start])
            token_id = make_token_id(session_key, span.text)
            out.append(f"[{TOKEN_PREFIX}{token_id}]")
            self._vault.write_async(session_id, token_id, span.text)
            token_ids.add(token_id)
            last_end = span.end
        out.append(value[last_end:])
        return ArgScanResult(value="".join(out), action=action, span_labels=labels, token_ids=token_ids)

    def _detect(self, value: str) -> list[Any]:
        unit = TextUnit(
            unit_id="arg", role="tool", text=value,
            locator=TextUnitLocator(surface="mcp_arg", path="argument"),
            turn_index=0, direction="input",
        )
        return self._pipeline.run([unit])
