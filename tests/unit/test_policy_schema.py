import pytest
import yaml
from policy.schema import Policy
from pydantic import ValidationError


def _base_policy_dict(**overrides):
    data = {
        "policy_id": "test",
        "detectors": {"packs": ["base_en"]},
        "rules": {"EMAIL": {"action": "REVERSIBLE"}},
    }
    data.update(overrides)
    return data


def test_valid_policy_loads():
    Policy(**_base_policy_dict())


def test_unknown_label_rejected():
    data = _base_policy_dict(rules={"NOT_A_LABEL": {"action": "REVERSIBLE"}})
    with pytest.raises(ValidationError):
        Policy(**data)


def test_out_of_range_min_confidence_rejected():
    data = _base_policy_dict(
        rules={"EMAIL": {"action": "REVERSIBLE", "min_confidence": 1.5}}
    )
    with pytest.raises(ValidationError):
        Policy(**data)


def test_invalid_action_rejected():
    data = _base_policy_dict(rules={"EMAIL": {"action": "DESTROY"}})
    with pytest.raises(ValidationError):
        Policy(**data)


def test_shipped_default_yaml_is_valid():
    from pathlib import Path

    raw = Path(__file__).resolve().parents[2].joinpath("policies", "default.yaml").read_text()
    Policy(**yaml.safe_load(raw))
