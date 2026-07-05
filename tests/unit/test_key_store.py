from auth.store import SqliteKeyStore


def test_key_stored_hashed_not_raw(tmp_path):
    store = SqliteKeyStore(storage_path=str(tmp_path / "keys.sqlite"))
    raw_key, key = store.create_key(team_id="team-a")

    assert raw_key.startswith("mk-")
    assert key.key_id.startswith("vk_")
    assert key.key_hash != raw_key

    # The raw key string must never appear anywhere in the sqlite file's bytes.
    db_bytes = (tmp_path / "keys.sqlite").read_bytes()
    assert raw_key.encode("utf-8") not in db_bytes


def test_get_by_hash_round_trip(tmp_path):
    store = SqliteKeyStore(storage_path=str(tmp_path / "keys.sqlite"))
    raw_key, key = store.create_key(policy_id="finance_strict", budget_usd_monthly=10.0)

    import hashlib
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    fetched = store.get_by_hash(key_hash)

    assert fetched is not None
    assert fetched.key_id == key.key_id
    assert fetched.policy_id == "finance_strict"
    assert fetched.budget_usd_monthly == 10.0


def test_update_budget_spent(tmp_path):
    store = SqliteKeyStore(storage_path=str(tmp_path / "keys.sqlite"))
    _, key = store.create_key()
    store.update_budget_spent(key.key_id, 5.5)

    fetched = store.get_by_hash(key.key_hash)
    assert fetched.budget_usd_spent == 5.5


def test_revoke_deactivates_key(tmp_path):
    store = SqliteKeyStore(storage_path=str(tmp_path / "keys.sqlite"))
    _, key = store.create_key()
    store.revoke(key.key_id)

    fetched = store.get_by_hash(key.key_hash)
    assert fetched.active is False
    assert fetched.revoked_at is not None


def test_model_allowlist_persisted(tmp_path):
    store = SqliteKeyStore(storage_path=str(tmp_path / "keys.sqlite"))
    _, key = store.create_key(model_allowlist=["gpt-4o", "llama-3.1-8b"])

    fetched = store.get_by_hash(key.key_hash)
    assert fetched.model_allowlist == ["gpt-4o", "llama-3.1-8b"]
