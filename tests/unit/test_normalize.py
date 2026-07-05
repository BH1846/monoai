from detect.normalize import map_span, normalize_with_offsets


def test_empty_string():
    norm, offsets = normalize_with_offsets("")
    assert norm == ""
    assert offsets == []


def test_no_change_on_plain_text():
    text = "The quick brown fox jumps over the lazy dog."
    norm, offsets = normalize_with_offsets(text)
    assert norm == text
    assert offsets == list(range(len(text)))


def test_strips_zero_width_characters():
    text = "jo​hn@ma​il.com"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "john@mail.com"
    assert len(offsets) == len(norm)


def test_folds_fullwidth_digits_and_letters():
    text = "５５５－１２３－４５６７"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "555-123-4567"
    assert len(offsets) == len(norm)


def test_collapses_spaced_out_word():
    text = "j o h n @ m a i l . c o m"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "john@mail.com"
    assert len(offsets) == len(norm)


def test_does_not_bleed_into_following_word():
    text = "contact me at j o h n @ m a i l . c o m today"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "contact me at john@mail.com today"


def test_does_not_bleed_into_preceding_word():
    text = "reach me at j o h n now"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "reach me at john now"


def test_short_spaced_run_not_collapsed():
    text = "a b c"
    norm, offsets = normalize_with_offsets(text)
    assert norm == "a b c"


def test_map_span_round_trips_for_identity_normalization():
    text = "no changes here"
    norm, offsets = normalize_with_offsets(text)
    start, end = map_span(offsets, len(text), 3, 10)
    assert text[start:end] == norm[3:10]


def test_map_span_after_deobfuscation():
    text = "email j o h n @ x . c o m please"
    norm, offsets = normalize_with_offsets(text)
    idx = norm.index("john@x.com")
    start, end = map_span(offsets, len(text), idx, idx + len("john@x.com"))
    assert text[start:end] == "j o h n @ x . c o m"
