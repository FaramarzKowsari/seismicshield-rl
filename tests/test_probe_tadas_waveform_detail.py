from scripts import probe_tadas_waveform_detail as mod


def test_sanitize_url_redacts_sensitive_query_values():
    out = mod.sanitize_url("https://x.test/path?a=1&token=secret&sessionId=abc&b=2#frag")
    assert "a=1" in out and "b=2" in out
    assert "secret" not in out and "abc" not in out
    assert "%5BREDACTED%5D" in out
    assert "#" not in out


def test_safe_headers_never_emit_sensitive_values():
    headers = {
        "Authorization": "Bearer secret",
        "Cookie": "sid=secret",
        "X-CSRF-Token": "csrf-secret",
        "Accept": "application/json",
    }
    safe = mod.safe_headers(headers)
    assert safe == {"Accept": "application/json"}
    presence = mod.sensitive_header_presence(headers)
    assert presence["authorization"] is True
    assert presence["cookie"] is True
    assert presence["x-csrf-token"] is True
    assert presence["x-xsrf-token"] is False
