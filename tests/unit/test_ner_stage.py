from contracts.spans import SpanLabel
from detect.stages.ner_stage import MiniLMNER


def test_falls_back_to_rule_based_without_model_path():
    ner = MiniLMNER()
    assert ner.backend_name == "rule_based"


def test_falls_back_when_model_path_missing():
    ner = MiniLMNER(model_path="/nonexistent/model.onnx")
    assert ner.backend_name == "rule_based"


def test_name_cue_detects_person():
    ner = MiniLMNER()
    spans = ner.predict("My name is Jane Doe and I need help.")
    persons = [s for s in spans if s.label == SpanLabel.PERSON]
    assert any(s.text == "Jane Doe" for s in persons)


def test_title_prefix_not_captured_as_name():
    ner = MiniLMNER()
    spans = ner.predict("Please contact Dr. John Smith about this.")
    persons = [s for s in spans if s.label == SpanLabel.PERSON]
    assert any(s.text == "John Smith" for s in persons)
    assert not any(s.text.strip() in ("Dr", "Dr.") for s in persons)


def test_address_pattern_detected():
    ner = MiniLMNER()
    spans = ner.predict("I live at 742 Evergreen Terrace, Springfield, IL 62704.")
    addresses = [s for s in spans if s.label == SpanLabel.ADDRESS]
    assert len(addresses) == 1
    assert "742 Evergreen Terrace" in addresses[0].text


def test_org_suffix_detected():
    ner = MiniLMNER()
    spans = ner.predict("I work at Acme Technologies Inc. every day.")
    orgs = [s for s in spans if s.label == SpanLabel.ORG]
    assert any("Acme Technologies Inc" in s.text for s in orgs)


def test_onnx_backend_used_when_model_path_given():
    from detect.stages.ner_stage import DEFAULT_MODEL_PATH
    ner = MiniLMNER(model_path=DEFAULT_MODEL_PATH)
    assert ner.backend_name == "onnx_minilm_int8"
