"""base_en detection pack: English regex + secrets detectors, so audit
records have a concrete pack_versions value to cite.
"""
from __future__ import annotations

from detect.stages.regex_stage import RegexDetector
from detect.stages.secrets_stage import SecretsDetector

PACK_VERSION = "base_en-v1"

__all__ = ["PACK_VERSION", "RegexDetector", "SecretsDetector"]
