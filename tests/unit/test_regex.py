from contracts.spans import SpanLabel
from detect.stages.regex_stage import RegexDetector
from detect.stages.secrets_stage import SecretsDetector


def _labels(text):
    return [s.label for s in RegexDetector().detect(text)]


def _secret_labels(text):
    return [s.label for s in SecretsDetector().detect(text)]


def test_email_detected():
    assert SpanLabel.EMAIL in _labels("contact me at a.b+c@example.co.uk")


def test_valid_luhn_credit_card_detected():
    labels = _labels("card 4111 1111 1111 1111 please")
    assert SpanLabel.CREDIT_CARD in labels


def test_invalid_luhn_credit_card_not_detected():
    labels = _labels("card 4111 1111 1111 1112 please")
    assert SpanLabel.CREDIT_CARD not in labels


def test_ssn_dashed_detected():
    spans = RegexDetector().detect("SSN 123-45-6789 on file")
    ssn = [s for s in spans if s.label == SpanLabel.GOV_ID]
    assert len(ssn) == 1
    assert ssn[0].text == "123-45-6789"
    assert ssn[0].confidence >= 0.85


def test_phone_various_formats():
    for text in ["(555) 123-4567", "555-123-4567", "555.123.4567", "5551234567"]:
        assert SpanLabel.PHONE in _labels(f"call {text} now")


def test_ipv4_detected():
    assert SpanLabel.IP_ADDRESS in _labels("server at 10.0.0.1 responded")


def test_aws_secret_key_detected():
    assert SpanLabel.SECRET in _secret_labels("key AKIAABCDEFGHIJKLMNOP is active")


def test_no_false_positive_on_plain_text():
    spans = RegexDetector().detect("The quick brown fox jumps over the lazy dog.")
    assert spans == []


def test_international_phone_detected():
    assert SpanLabel.PHONE in _labels("call +44 7911 123456 now")


def test_date_month_day_year_detected():
    spans = RegexDetector().detect("The meeting is on November 20th, 1934 sharp.")
    dates = [s for s in spans if s.label == SpanLabel.DATE_TIME]
    assert any("November 20th, 1934" in s.text for s in dates)


def test_date_numeric_detected():
    assert SpanLabel.DATE_TIME in _labels("expires 07/02/2053 next")


def test_time_detected():
    assert SpanLabel.DATE_TIME in _labels("meet me at 3:45 PM today")


def test_username_handle_detected():
    spans = RegexDetector().detect("reach out to @jane_doe for details")
    usernames = [s for s in spans if s.label == SpanLabel.USERNAME]
    assert len(usernames) == 1
    assert usernames[0].text == "@jane_doe"


def test_username_cue_detected():
    spans = RegexDetector().detect("my username: jdoe_99 is active")
    usernames = [s for s in spans if s.label == SpanLabel.USERNAME]
    assert any(s.text == "jdoe_99" for s in usernames)


def test_alnum_gov_id_requires_cue():
    assert SpanLabel.GOV_ID not in _labels("the product code is VT31867ES")


def test_alnum_gov_id_detected_with_cue():
    spans = RegexDetector().detect("my ID card is VT31867ES today")
    gov_ids = [s for s in spans if s.label == SpanLabel.GOV_ID]
    assert any(s.text == "VT31867ES" for s in gov_ids)


def test_password_cue_plain_text():
    spans = SecretsDetector().detect("Password: XG|90c(1( Last_Name: Smith")
    secrets = [s for s in spans if s.label == SpanLabel.SECRET]
    assert any(s.text == "XG|90c(1(" for s in secrets)


def test_password_cue_json_style():
    spans = SecretsDetector().detect('"PASS": "ZAn4H", "TIME": "10:20"')
    secrets = [s for s in spans if s.label == SpanLabel.SECRET]
    assert any(s.text == "ZAn4H" for s in secrets)


def test_password_cue_xml_style():
    spans = SecretsDetector().detect("<password>Sup3rSecret</password>")
    secrets = [s for s in spans if s.label == SpanLabel.SECRET]
    assert any(s.text == "Sup3rSecret" for s in secrets)


def test_no_password_false_positive_without_cue():
    assert SpanLabel.SECRET not in _secret_labels("I need to pass the exam tomorrow")


def test_geocoord_detected():
    spans = RegexDetector().detect("issued on 07/02/2053 at [52.9615, -2.05246].")
    addresses = [s for s in spans if s.label == SpanLabel.ADDRESS]
    assert any(s.text == "[52.9615, -2.05246]" for s in addresses)


def test_address_field_cues_detected_as_separate_spans():
    text = (
        "<li>Building: <strong>534</strong></li>\n"
        "<li>Street: <strong>Moores Meadow Road</strong></li>\n"
        "<li>City: <strong>Tabernacle</strong></li>"
    )
    spans = RegexDetector().detect(text)
    addresses = {s.text for s in spans if s.label == SpanLabel.ADDRESS}
    assert addresses == {"534", "Moores Meadow Road", "Tabernacle"}
