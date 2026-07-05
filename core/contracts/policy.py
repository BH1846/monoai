from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from contracts.spans import DetectedSpan


class Action(str, Enum):
    REVERSIBLE = "REVERSIBLE"
    PRESERVE = "PRESERVE"
    BLOCK = "BLOCK"


class PolicyDecision(BaseModel):
    span: DetectedSpan
    action: Action
    rule_id: str
    min_confidence_applied: float | None = None
    compressible: bool = False
