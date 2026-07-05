from vault.session_tokens import derive_session_key, make_token_id


def test_same_value_same_token_within_session():
    key = derive_session_key("session-a", "server-secret")
    t1 = make_token_id(key, "a@b.com")
    t2 = make_token_id(key, "a@b.com")
    assert t1 == t2


def test_same_value_different_token_across_sessions():
    key_a = derive_session_key("session-a", "server-secret")
    key_b = derive_session_key("session-b", "server-secret")
    assert make_token_id(key_a, "a@b.com") != make_token_id(key_b, "a@b.com")


def test_nfkc_normalized_before_hmac():
    key = derive_session_key("session-a", "server-secret")
    # Full-width vs ASCII digits are NFKC-equivalent.
    t1 = make_token_id(key, "555-123-4567")
    t2 = make_token_id(key, "５５５-１２３-４５６７")
    assert t1 == t2


def test_token_id_is_fixed_width():
    key = derive_session_key("session-a", "server-secret")
    assert len(make_token_id(key, "short")) == 10
    assert len(make_token_id(key, "a much much longer value than short")) == 10
