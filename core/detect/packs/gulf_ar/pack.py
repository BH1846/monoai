"""gulf_ar detection pack (Phase 4): Gulf/Arabic-region government ID
regex engines (Emirates ID, Iqama, Saudi National ID, Qatar QID,
Bahrain CPR, Kuwait Civil ID, Oman civil number) plus Arabic morphology
stripping (morphology.py) used for nearby cue-word confidence boosting.

See DECISIONS.md for which of the above checksums are confirmed
against a public reference implementation, which are best-effort/
unofficial, and which have no publicly documented checksum at all
(structural pattern matching only).
"""
from __future__ import annotations

from detect.packs.gulf_ar.ids import GulfArIdDetector

PACK_VERSION = "gulf_ar-v1"

__all__ = ["PACK_VERSION", "GulfArIdDetector"]
