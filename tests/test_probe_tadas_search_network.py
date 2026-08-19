import subprocess
import sys

from scripts.probe_tadas_search_network import (
    sanitize_post_data,
    sanitize_url,
    select_headers,
    should_capture_request,
)


def test_sanitize_url_redacts_sensitive_query_keys():
    value = sanitize_url(
        "https://tadas.afad.gov.tr/api/search?eventId=551067&token=abc&session_id=xyz"
    )
    assert "eventId=551067" in value
    assert "abc" not in value
    assert "xyz" not in value
    assert "%3Credacted%3E" in value


def test_sanitize_json_body_preserves_search_fields_but_redacts_secrets():
    body = sanitize_post_data(
        '{"eventId":"551067","start":"15-10-2014","csrfToken":"secret"}',
        "application/json",
    )
    assert body["eventId"] == "551067"
    assert body["start"] == "15-10-2014"
    assert body["csrfToken"] == "<redacted>"


def test_sanitize_form_body_redacts_authentication_fields():
    body = sanitize_post_data(
        "eventId=551067&password=nope&x=1",
        "application/x-www-form-urlencoded",
    )
    assert body == {"eventId": "551067", "password": "<redacted>", "x": "1"}


def test_header_allowlist_never_emits_cookie_or_authorization():
    result = select_headers(
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": "session=secret",
            "Authorization": "Bearer secret",
        },
        {"content-type", "accept", "cookie", "authorization"},
    )
    assert result == {"content-type": "application/json", "accept": "application/json"}


def test_capture_policy_includes_navigation_xhr_fetch_and_other():
    origin = "https://tadas.afad.gov.tr"
    assert should_capture_request(origin + "/list-waveform", "document")
    assert should_capture_request(origin + "/api/search", "xhr")
    assert should_capture_request(origin + "/api/search", "fetch")
    assert should_capture_request(origin + "/backend/action", "other")


def test_capture_policy_excludes_static_and_cross_origin():
    origin = "https://tadas.afad.gov.tr"
    assert not should_capture_request(origin + "/site.css", "stylesheet")
    assert not should_capture_request(origin + "/logo.png", "image")
    assert not should_capture_request("https://example.com/api/search", "xhr")


def test_direct_entrypoint_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/probe_tadas_search_network.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--rank" in completed.stdout
    assert "--out" in completed.stdout
