"""G3 proof test: policy is declarative and versioned, not hardcoded in
Python. Full end-to-end (via HTTP + virtual keys) is exercised again in
Step 9's gateway test suite once auth/orchestrator exist; this test
proves the underlying detect -> policy substance is correct.
"""
from pathlib import Path

from contracts.policy import Action
from contracts.scan import ScanResult, Verdict
from contracts.spans import TextUnit, TextUnitLocator
from detect.pipeline import DetectionPipeline
from policy.engine import evaluate
from policy.store import PolicyStore

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = REPO_ROOT / "policies"


def _unit(text: str) -> TextUnit:
    return TextUnit(
        unit_id="u1", role="user", text=text,
        locator=TextUnitLocator(surface="chat_message", path="messages[0].content"),
        turn_index=0, direction="input",
    )


def test_same_prompt_two_keys_two_outcomes():
    """A 'key' maps to a policy_id (gateway/auth wires this in Step 7); at
    this layer, two different policy_ids over the same detected spans is
    the substance of the guarantee."""
    store = PolicyStore()
    store.load_dir(POLICIES_DIR)
    pipeline = DetectionPipeline(use_onnx_ner=False)

    prompt = "call me at +44 7911 123456"
    spans = pipeline.run([_unit(prompt)])
    assert spans, "expected at least one detected span (phone number)"

    default_decisions = evaluate(spans, store.get("default"))
    finance_decisions = evaluate(spans, store.get("finance_strict"))

    default_actions = {d.action for d in default_decisions}
    finance_actions = {d.action for d in finance_decisions}
    # PHONE is REVERSIBLE under both policies today -- use IP_ADDRESS,
    # which differs (REVERSIBLE under default, BLOCK under finance_strict).
    assert default_actions == {Action.REVERSIBLE}

    ip_prompt = "server logged from 10.0.0.1"
    ip_spans = pipeline.run([_unit(ip_prompt)])
    ip_default = evaluate(ip_spans, store.get("default"))
    ip_finance = evaluate(ip_spans, store.get("finance_strict"))
    assert ip_default[0].action == Action.REVERSIBLE
    assert ip_finance[0].action == Action.BLOCK


def test_policy_version_cited_in_audit():
    store = PolicyStore()
    store.load_dir(POLICIES_DIR)
    pipeline = DetectionPipeline(use_onnx_ner=False)

    policy = store.get("default")
    spans = pipeline.run([_unit("email me at a@b.com")])
    decisions = evaluate(spans, policy)

    result = ScanResult(
        request_id="r1",
        session_id="s1",
        verdict=Verdict.ALLOW,
        decisions=decisions,
        blocked_labels=[],
        policy_id=policy.policy_id,
        policy_version=policy.version,
        detector_versions={"base_en": "base_en-v1"},
    )

    assert result.policy_version == store.latest_version("default")
    assert result.policy_version.startswith("sha256:")
