from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SpanLabel(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    CREDIT_CARD = "CREDIT_CARD"
    GOV_ID = "GOV_ID"
    SECRET = "SECRET"
    IP_ADDRESS = "IP_ADDRESS"
    DATE_TIME = "DATE_TIME"
    USERNAME = "USERNAME"
    PERSON = "PERSON"
    ADDRESS = "ADDRESS"
    ORG = "ORG"
    TITLE = "TITLE"
    DEMOGRAPHIC = "DEMOGRAPHIC"
    MISC = "MISC"


class SpanSource(str, Enum):
    REGEX = "regex"
    SECRETS = "secrets"
    NER = "ner"
    REPAIRED = "repaired"
    LOCKED = "locked"


class TextUnitLocator(BaseModel):
    """Where a TextUnit came from. `surface` grew from Phase 1's
    "chat_message"-only to also cover Phase 3's filescan-worker
    ("file_field") and Phase 4's MCP tool firewall ("mcp_arg")."""

    surface: Literal["chat_message", "file_field", "mcp_arg"]
    path: str


class TextUnit(BaseModel):
    unit_id: str
    role: Literal["system", "user", "assistant", "tool"]
    text: str
    locator: TextUnitLocator
    turn_index: int
    direction: Literal["input", "output"]


class DetectedSpan(BaseModel):
    """Output of core/detect — label + confidence only, never an action.

    Action-assignment (REVERSIBLE/PRESERVE/BLOCK) belongs to core/policy;
    see PolicyDecision. `meta` carries detection-time hints (e.g.
    {"negated": True} from locked_span_stage) that policy rules may read,
    but never an action/classification value itself.
    """

    unit_id: str
    start: int
    end: int
    text: str
    label: SpanLabel
    source: SpanSource
    confidence: float = 1.0
    meta: dict[str, Any] = Field(default_factory=dict)
