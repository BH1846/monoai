Phase 4: Gulf/Arabic sovereignty detection pack (closes the gulf_ar half of
`policies/gulf_sovereign.yaml`, which previously only activated `base_en`).

- `ids.py` — regex + checksum engines for Emirates ID, Iqama, Saudi National
  ID, Qatar QID, Bahrain CPR, Kuwait Civil ID, and Oman civil number, plus
  Arabic-Indic/Eastern Arabic-Indic digit folding so the patterns match
  regardless of which digit script a document uses. See DECISIONS.md for
  which checksums are confirmed against a public reference implementation
  (Saudi National ID/Iqama, Kuwait Civil ID) vs. best-effort/unofficial (UAE
  Emirates ID) vs. structural-pattern-only, no public checksum found (Qatar
  QID, Bahrain CPR, Oman civil number).
- `morphology.py` — light Arabic prefix/suffix stripping, used to recognize
  an ID-related cue word (هوية / بطاقة / اقامة / رقم / …) near a candidate
  digit span even when it's grammatically fused (بالهوية, للاقامة, …).
- `pack.py` — `GulfArIdDetector` + `PACK_VERSION`, selected per-policy via
  `detectors.packs` (see `core/detect/pipeline.py`'s pack-selection logic);
  not activated unconditionally for every request.
