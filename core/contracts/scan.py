from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel

from contracts.policy import PolicyDecision
from contracts.spans import TextUnit


class ScanRequest(BaseModel):
    request_id: str
    session_id: str
    text_units: list[TextUnit]
    locale_hint: str = "en"
    policy_id: str
    direction: Literal["input", "output"]


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_REDACTION = "ALLOW_WITH_REDACTION"
    BLOCK = "BLOCK"


class ScanResult(BaseModel):
    request_id: str
    session_id: str
    verdict: Verdict
    decisions: list[PolicyDecision]
    blocked_labels: list[str]
    policy_id: str
    policy_version: str
    detector_versions: dict[str, str]
