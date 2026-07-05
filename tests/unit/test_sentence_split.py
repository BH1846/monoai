from detect.sentence_split import split_sentences


def test_basic_split():
    text = "Hello there. How are you? I am fine!"
    sentences = split_sentences(text)
    assert [s.text.strip() for s in sentences] == ["Hello there.", "How are you?", "I am fine!"]


def test_offsets_are_correct():
    text = "First sentence. Second sentence."
    sentences = split_sentences(text)
    for s in sentences:
        assert text[s.start:s.end] == s.text


def test_abbreviation_does_not_split():
    text = "Please contact Dr. Smith about the results."
    sentences = split_sentences(text)
    assert len(sentences) == 1


def test_empty_text():
    assert split_sentences("") == []


def test_no_trailing_punctuation():
    text = "This has no ending punctuation"
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert sentences[0].text == text
