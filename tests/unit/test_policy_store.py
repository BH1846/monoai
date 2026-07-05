from pathlib import Path

from policy.store import PolicyStore

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = REPO_ROOT / "policies"


def test_version_is_content_hash(tmp_path):
    content = (
        "policy_id: a\n"
        "detectors:\n  packs: [base_en]\n"
        "rules:\n  EMAIL: { action: REVERSIBLE }\n"
    )
    file_a = tmp_path / "a.yaml"
    file_a.write_text(content)
    file_b = tmp_path / "b.yaml"
    # Same content, different policy_id so it's a distinct entry, but if we
    # instead give it the SAME policy_id+content the version must match.
    file_b.write_text(content)

    store = PolicyStore()
    policy_a = store.load_file(file_a)
    policy_b = store.load_file(file_b)
    assert policy_a.version == policy_b.version

    file_c = tmp_path / "c.yaml"
    file_c.write_text(content.replace("REVERSIBLE", "PRESERVE"))
    policy_c = store.load_file(file_c)
    assert policy_c.version != policy_a.version


def test_load_dir_loads_shipped_policies():
    store = PolicyStore()
    loaded = store.load_dir(POLICIES_DIR)
    ids = {p.policy_id for p in loaded}
    assert {"default", "finance_strict", "gulf_sovereign"} <= ids


def test_get_returns_latest_version_by_default():
    store = PolicyStore()
    store.load_dir(POLICIES_DIR)
    policy = store.get("default")
    assert policy.policy_id == "default"
    assert policy.version == store.latest_version("default")
