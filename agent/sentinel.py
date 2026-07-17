"""Local SENTINEL detection on the agent: Tier 0 (regex + secrets) + Tier 1
(ONNX NER), run against local traffic/files, producing NON-sensitive event
payloads for the manager's audit log.

This reuses core/detect/pipeline.py UNMODIFIED -- the exact same
DetectionPipeline the gateway, filescan-worker, and mcp-firewall construct.
Tier 2 (the LLM injection judge, core/detect/stages/injection_judge.py) is
deliberately NOT wired here: it needs network egress + provider keys and
stays manager-side per scope. The agent does regex/NER locally and, if it
ever needs a Tier-2 opinion, that is a manager concern.

The agent applies the cached policy locally (policy_cache.py -> core/policy/
engine.evaluate) so it can decide completed-vs-blocked without a per-request
round-trip to the manager. Only the resulting counts/labels are emitted --
never the detected text (invariant #1).
"""
from __future__ import annotations

import time
import uuid
from collections import Counter

from contracts.agent import AgentEventPayload
from contracts.policy import Action
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from policy.engine import evaluate
from policy.schema import Policy


class LocalSentinel:
    def __init__(self, pipeline: DetectionPipeline, detector_versions: dict[str, str], pack_versions: dict[str, str]) -> None:
        self._pipeline = pipeline
        self._detector_versions = detector_versions
        self._pack_versions = pack_versions

    def scan_text(self, text: str, policy: Policy, policy_version: str, session_id: str | None = None) -> AgentEventPayload:
        """Run Tier 0 + Tier 1 against one piece of local text, apply the
        cached policy, and return a manager-ready event. `policy_version` is
        the manager's authoritative version string for the cached policy (so
        the manager can attribute the record to the right policy revision and
        detect drift)."""
        t0 = time.monotonic()
        session_id = session_id or uuid.uuid4().hex
        request_id = uuid.uuid4().hex

        unit = TextUnit(
            unit_id="local", role="user", text=text,
            locator=TextUnitLocator(surface="chat_message", path="agent/local"),
            turn_index=0, direction="input",
        )
        spans = self._pipeline.run([unit], locale_hint=policy.locale_hint, policy_ctx=policy)
        decisions = evaluate(spans, policy)

        counts: Counter[str] = Counter()
        blocked_labels: list[str] = []
        redacted = 0
        for d in decisions:
            label = d.span.label.value
            counts[label] += 1
            if d.action == Action.BLOCK:
                blocked_labels.append(label)
            elif d.action == Action.REVERSIBLE:
                # REVERSIBLE == tokenized/redacted-with-restore, the gateway's
                # reversible-PII-token path (core/contracts/policy.py).
                redacted += 1

        event = "blocked" if blocked_labels else "completed"
        pii_sanitize_ms = (time.monotonic() - t0) * 1000.0

        return AgentEventPayload(
            ts=time.time(),
            request_id=request_id,
            session_id=session_id,
            event=event,
            policy_id=policy.policy_id,
            policy_version=policy_version,
            detector_versions=self._detector_versions,
            pack_versions=self._pack_versions,
            span_counts_by_label=dict(counts),
            blocked_labels=sorted(set(blocked_labels)),
            redacted_count=redacted,
            pii_sanitize_ms=round(pii_sanitize_ms, 3),
        )
