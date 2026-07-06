from __future__ import annotations

from contracts.policy import Action
from contracts.spans import SpanLabel
from pydantic import BaseModel, Field


class PolicyRule(BaseModel):
    action: Action
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    below_min_confidence_action: Action | None = None
    subtypes: dict[str, Action] | None = None


class PolicyOverride(BaseModel):
    when_meta_negated: bool
    action: Action


class DetectorsConfig(BaseModel):
    packs: list[str]
    min_global_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class OutputScanConfig(BaseModel):
    enabled: bool = True
    reuse_input_rules: bool = True


class Policy(BaseModel):
    policy_id: str
    description: str = ""
    locale_hint: str = "en"
    detectors: DetectorsConfig
    rules: dict[SpanLabel, PolicyRule]
    overrides: dict[str, PolicyOverride] = Field(default_factory=dict)
    token_budget_mode: bool = False
    compressible_length_threshold: int = 20
    output_scan: OutputScanConfig = Field(default_factory=OutputScanConfig)
    version: str = ""
