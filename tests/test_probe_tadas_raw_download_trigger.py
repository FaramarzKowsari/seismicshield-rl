from scripts.probe_tadas_raw_download_trigger import redact_json


def test_redact_json_redacts_sensitive_keys_recursively():
    value = {
        "waveformId": 2136302,
        "token": "secret",
        "nested": {"authorizationKey": "secret2", "station": 1658},
        "items": [{"csrfValue": "secret3", "ok": True}],
    }
    redacted = redact_json(value)
    assert redacted["waveformId"] == 2136302
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["authorizationKey"] == "[REDACTED]"
    assert redacted["nested"]["station"] == 1658
    assert redacted["items"][0]["csrfValue"] == "[REDACTED]"
    assert redacted["items"][0]["ok"] is True


def test_redact_json_preserves_non_sensitive_sequences():
    value = [1, "x", {"recordId": "00456", "eventId": "543428"}]
    assert redact_json(value) == value
