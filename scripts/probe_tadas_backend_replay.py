#!/usr/bin/env python3
"""Replay one AFAD/TADAS waveform search using an exact live browser request.

Diagnostic/provenance infrastructure only. This does not change the frozen event order,
0.15 g necessary-condition threshold, component-level eligibility rules, or confirmatory
gate.

The previous direct API probe reproduced the visible JSON payload but received HTTP 500.
The privacy-safe network trace intentionally omitted Cookie/Authorization values, so it
could not establish whether the live Angular request carried session/authentication
headers that the direct API request lacked. This probe therefore performs exactly one
known UI search, captures that request's body and headers in memory, and immediately
replays the exact request through the BrowserContext APIRequestContext.

Sensitive header *values* are never printed or serialized. The private artifact records
only their presence plus non-secret request metadata and the replay response.
"""

from __future__ import annotations

import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path

if __package__:
    from scripts import screen_afad_tadas_station_summaries as base
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    import screen_afad_tadas_station_summaries as base
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

BACKEND_URL = "https://ivmeservis.afad.gov.tr/Waveforms/GetWaveforms"
DEFAULT_OUT = Path("data/private/tadas-backend-replay.json")

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-csrf-token",
    "x-xsrf-token",
}
HOP_BY_HOP_OR_RECOMPUTED_HEADERS = {
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "transfer-encoding",
}


def _iso_utc_day(day, *, end: bool) -> str:
    suffix = "23:59:59.000Z" if end else "00:00:00.000Z"
    return f"{day.isoformat()}T{suffix}"


def build_backend_payload(queue_row: dict[str, str], *, pad_days: int = 1) -> dict[str, object]:
    """Build the minimal payload inferred before exact live-request bootstrap.

    This helper is retained for comparison/tests. The live replay path below deliberately
    does not trust this inferred date serialization until it has been validated against
    the exact request emitted by the current TADAS UI.
    """
    if pad_days < 0:
        raise ValueError("pad_days must be >= 0")
    event_id = str(queue_row["event_id"]).strip()
    if not event_id:
        raise ValueError("event_id must be nonblank")
    event_dt = base.parse_export_event_datetime(queue_row["event_date_from_export"])
    start_day = event_dt.date() - timedelta(days=pad_days)
    end_day = event_dt.date() + timedelta(days=pad_days)
    return {
        "fromMagnitude": 3,
        "startDate": _iso_utc_day(start_day, end=False),
        "endDate": _iso_utc_day(end_day, end=True),
        "fromLatitude": None,
        "toLatitude": None,
        "fromLongitude": None,
        "toLongitude": None,
        "country": None,
        "province": None,
        "district": None,
        "neighborhood": None,
        "eaEventId": event_id,
        "waveformId": 0,
    }


def response_shape(value) -> dict[str, object]:
    if isinstance(value, list):
        first_type = type(value[0]).__name__ if value else None
        first_keys = sorted(value[0].keys()) if value and isinstance(value[0], dict) else []
        return {
            "top_level_type": "list",
            "length": len(value),
            "first_item_type": first_type,
            "first_item_keys": first_keys,
        }
    if isinstance(value, dict):
        return {
            "top_level_type": "dict",
            "keys": sorted(value.keys()),
        }
    return {"top_level_type": type(value).__name__}


def forwardable_headers(headers: dict[str, str]) -> dict[str, str]:
    """Keep the exact live request headers in memory except transport-recomputed ones."""
    return {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).lower() not in HOP_BY_HOP_OR_RECOMPUTED_HEADERS
        and not str(key).startswith(":")
    }


def sensitive_header_presence(headers: dict[str, str]) -> dict[str, bool]:
    lowered = {str(key).lower() for key in headers}
    return {name: name in lowered for name in sorted(SENSITIVE_HEADER_NAMES)}


def _decode_json_or_text(body: bytes, content_type: str):
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, "<non-UTF-8 body omitted>"
    if "json" in content_type.lower():
        try:
            return json.loads(text), None
        except json.JSONDecodeError:
            return None, text[:4000]
    return None, text[:4000]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path, help="deterministic event_candidate_queue.csv")
    parser.add_argument("--rank", type=int, default=248, help="queue rank to replay; default 248")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
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

    event_id = row["event_id"]
    start, end = base.date_window(row["event_date_from_export"], pad_days=args.pad_days)

    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-backend-replay-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        assert browser.page is not None
        assert browser.context is not None
        page = browser.page

        # Re-enter the known search form after attaching the exact request/response waiters.
        page.goto(base.TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        browser._set_control("event_id", event_id)
        browser._set_control("start_date", start)
        browser._set_control("end_date", end)
        browser._verify_search_form(event_id, start, end)

        def matching_request(request) -> bool:
            if request.url != BACKEND_URL or request.method.upper() != "POST":
                return False
            post_data = request.post_data or ""
            return f'"eaEventId":"{event_id}"' in post_data.replace(" ", "")

        def matching_response(response) -> bool:
            return matching_request(response.request)

        with page.expect_request(matching_request, timeout=args.timeout_ms) as request_info:
            with page.expect_response(matching_response, timeout=args.timeout_ms) as response_info:
                browser._action("search_button", ("search", "query", "sorgula", "ara")).click()

        live_request = request_info.value
        live_response = response_info.value
        browser._verify_search_form(event_id, start, end)

        live_post_data = live_request.post_data
        if not live_post_data:
            raise RuntimeError("captured live TADAS search request had no POST body")
        try:
            live_payload = json.loads(live_post_data)
        except json.JSONDecodeError as exc:
            raise RuntimeError("captured live TADAS search request body was not JSON") from exc
        if str(live_payload.get("eaEventId", "")) != event_id:
            raise RuntimeError("captured live TADAS request EventID did not match queue EventID")

        live_headers = live_request.all_headers()
        replay_headers = forwardable_headers(live_headers)
        presence = sensitive_header_presence(live_headers)

        # Replay the *exact* live body and the live request headers in memory. Sensitive
        # values are used only for this request and never written to disk or stdout.
        replay = browser.context.request.post(
            BACKEND_URL,
            data=live_post_data,
            headers=replay_headers,
            timeout=args.timeout_ms,
        )
        replay_status = replay.status
        replay_headers_response = replay.headers
        replay_body = replay.body()

    replay_content_type = replay_headers_response.get("content-type", "")
    replay_json, replay_text = _decode_json_or_text(replay_body, replay_content_type)

    artifact = {
        "schema_version": 2,
        "privacy": {
            "cookies_recorded": False,
            "authorization_recorded": False,
            "sensitive_header_values_recorded": False,
            "output_location_expected_private": True,
        },
        "probe": {
            "rank": args.rank,
            "event_id": event_id,
            "event_date_from_export": row["event_date_from_export"],
            "ui_start_date": start,
            "ui_end_date": end,
        },
        "live_ui_request": {
            "method": live_request.method,
            "url": live_request.url,
            "payload": live_payload,
            "header_names": sorted(str(key).lower() for key in live_headers),
            "sensitive_header_presence": presence,
            "ui_response_status": live_response.status,
            "ui_response_content_type": live_response.headers.get("content-type", ""),
        },
        "exact_replay": {
            "status": replay_status,
            "content_type": replay_content_type,
            "body_sha256": hashlib.sha256(replay_body).hexdigest(),
            "body_bytes": len(replay_body),
            "shape": response_shape(replay_json) if replay_json is not None else None,
            "json": replay_json,
            "error_text": replay_text if replay_json is None else None,
        },
        "inferred_payload_for_comparison": build_backend_payload(row, pad_days=args.pad_days),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Live UI request HTTP {live_response.status}: {BACKEND_URL}")
    print(f"EventID {event_id} rank {args.rank}")
    print(
        "Sensitive header presence: "
        + ", ".join(f"{name}={'yes' if value else 'no'}" for name, value in presence.items())
    )
    print(f"Exact in-memory replay HTTP {replay_status}")
    print(f"Replay SHA256: {artifact['exact_replay']['body_sha256']}")
    print(f"Replay bytes: {len(replay_body)}")
    if replay_json is not None:
        print("Replay shape: " + json.dumps(response_shape(replay_json), ensure_ascii=False, sort_keys=True))
    else:
        print("Replay returned non-JSON/error text; saved privately for diagnosis")
    print(f"Wrote private replay artifact: {args.out}")
    print("No Cookie, Authorization, CSRF/XSRF, or other sensitive header values are written.")

    if live_response.status != 200:
        raise RuntimeError(f"live UI backend request unexpectedly returned HTTP {live_response.status}")
    if replay_status != 200:
        raise RuntimeError(
            f"exact live-request replay returned HTTP {replay_status}; inspect private artifact"
        )
    if replay_json is None:
        raise RuntimeError("exact live-request replay returned HTTP 200 but non-JSON content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
