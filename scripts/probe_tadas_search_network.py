#!/usr/bin/env python3
"""Capture privacy-safe TADAS search XHR/fetch metadata for backend discovery.

This is diagnostic/provenance infrastructure only. It does not change any frozen
selection rule and does not inspect confirmatory performance results.

The probe reuses the authenticated persistent Chromium profile and the strict Kendo
form adapter, performs exactly one known event search, and writes a sanitized JSON
trace under data/private by default. Authentication/session secrets are deliberately
not recorded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if __package__:
    from scripts import screen_afad_tadas_station_summaries as base
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser, TADAS_ORIGIN
else:
    import screen_afad_tadas_station_summaries as base
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser, TADAS_ORIGIN

SENSITIVE_KEY_PARTS = (
    "authorization", "cookie", "csrf", "xsrf", "token", "secret", "password",
    "passwd", "session", "credential", "apikey", "api_key",
)
SAFE_REQUEST_HEADERS = {
    "accept", "content-type", "origin", "referer", "x-requested-with",
}
SAFE_RESPONSE_HEADERS = {
    "content-type", "content-disposition", "cache-control",
}
DEFAULT_TRACE = Path("data/private/tadas-search-network.json")


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_mapping(value):
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if _is_sensitive_key(key) else _redact_mapping(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_mapping(item) for item in value]
    return value


def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        pairs.append((key, "<redacted>" if _is_sensitive_key(key) else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


def sanitize_post_data(post_data: str | None, content_type: str | None = None):
    if not post_data:
        return None
    text = str(post_data)
    ctype = (content_type or "").lower()
    if "json" in ctype or text.lstrip().startswith(("{", "[")):
        try:
            return _redact_mapping(json.loads(text))
        except json.JSONDecodeError:
            return "<non-json body omitted>"
    if "application/x-www-form-urlencoded" in ctype or "=" in text:
        try:
            return {
                key: ("<redacted>" if _is_sensitive_key(key) else value)
                for key, value in parse_qsl(text, keep_blank_values=True)
            }
        except ValueError:
            return "<form body omitted>"
    return "<body omitted>"


def select_headers(headers: dict[str, str], allowlist: set[str]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in allowlist and not _is_sensitive_key(key)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path, help="deterministic event_candidate_queue.csv")
    parser.add_argument("--rank", type=int, default=248, help="queue rank to probe; default 248")
    parser.add_argument("--out", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--profile-dir", type=Path, default=base.DEFAULT_PROFILE_DIR)
    parser.add_argument("--pad-days", type=int, default=1)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    if args.rank < 1:
        parser.error("--rank must be >= 1")
    if args.pad_days < 0:
        parser.error("--pad-days must be >= 0")

    rows = base.read_queue(args.queue)
    if args.rank > len(rows):
        parser.error(f"--rank {args.rank} exceeds queue length {len(rows)}")
    row = rows[args.rank - 1]
    if int(row["rank"]) != args.rank:
        parser.error("queue rank mismatch")

    captured: list[dict[str, object]] = []
    response_index: dict[str, list[int]] = {}

    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-network-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        assert browser.page is not None
        page = browser.page

        def on_request(request) -> None:
            if not request.url.startswith(TADAS_ORIGIN):
                return
            if request.resource_type not in {"xhr", "fetch"}:
                return
            headers = request.headers
            safe_headers = select_headers(headers, SAFE_REQUEST_HEADERS)
            record = {
                "kind": "request",
                "resource_type": request.resource_type,
                "method": request.method,
                "url": sanitize_url(request.url),
                "headers": safe_headers,
                "post_data": sanitize_post_data(
                    request.post_data,
                    safe_headers.get("content-type"),
                ),
            }
            captured.append(record)
            response_index.setdefault(request.url, []).append(len(captured) - 1)

        def on_response(response) -> None:
            if not response.url.startswith(TADAS_ORIGIN):
                return
            request = response.request
            if request.resource_type not in {"xhr", "fetch"}:
                return
            captured.append({
                "kind": "response",
                "resource_type": request.resource_type,
                "method": request.method,
                "url": sanitize_url(response.url),
                "status": response.status,
                "headers": select_headers(response.headers, SAFE_RESPONSE_HEADERS),
            })

        page.on("request", on_request)
        page.on("response", on_response)

        start, end = base.date_window(row["event_date_from_export"], pad_days=args.pad_days)
        page.goto(base.TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        browser._set_control("event_id", row["event_id"])
        browser._set_control("start_date", start)
        browser._set_control("end_date", end)
        browser._verify_search_form(row["event_id"], start, end)

        # Drop page-load traffic; retain only the network activity caused by Search.
        captured.clear()
        response_index.clear()
        browser._action("search_button", ("search", "query", "sorgula", "ara")).click()
        try:
            page.wait_for_load_state("networkidle", timeout=min(args.timeout_ms, 15000))
        except Exception:
            page.wait_for_timeout(2500)
        browser._verify_search_form(row["event_id"], start, end)
        page.wait_for_timeout(1000)

    trace = {
        "schema_version": 1,
        "privacy": {
            "cookies_recorded": False,
            "authorization_recorded": False,
            "sensitive_query_or_body_keys_redacted": True,
        },
        "probe": {
            "rank": args.rank,
            "event_id": row["event_id"],
            "event_date_from_export": row["event_date_from_export"],
            "start_date": start,
            "end_date": end,
        },
        "network": captured,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote sanitized trace: {args.out}")
    print(f"Captured {sum(1 for x in captured if x['kind'] == 'request')} XHR/fetch requests")
    print("No Cookie or Authorization header values are written to the trace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
