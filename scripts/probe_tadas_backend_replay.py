#!/usr/bin/env python3
"""Replay one AFAD/TADAS waveform search directly against the discovered backend.

Diagnostic/provenance infrastructure only. This does not change the frozen event order,
0.15 g necessary-condition threshold, component-level eligibility rules, or confirmatory
gate. The probe reuses the persistent authenticated Chromium context, sends one direct
POST to the backend endpoint observed in the privacy-safe network trace, and writes the
response only under data/private by default.

Cookie/Authorization values are never serialized by this script. The API request context
may share the browser session internally, but authentication material is not written to
output.
"""

from __future__ import annotations

import argparse
from datetime import timedelta, timezone
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


def _iso_utc_day(day, *, end: bool) -> str:
    suffix = "23:59:59.000Z" if end else "00:00:00.000Z"
    return f"{day.isoformat()}T{suffix}"


def build_backend_payload(queue_row: dict[str, str], *, pad_days: int = 1) -> dict[str, object]:
    """Build the minimal payload observed in the live TADAS Search request.

    The exact event id is authoritative for this replay. The date window is retained as a
    fail-safe server-side constraint and spans whole UTC days around the exported event
    date. It is not used to alter deterministic event selection.
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

    payload = build_backend_payload(row, pad_days=args.pad_days)

    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-backend-replay-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        assert browser.context is not None
        response = browser.context.request.post(
            BACKEND_URL,
            data=payload,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Referer": "https://tadas.afad.gov.tr/",
            },
            timeout=args.timeout_ms,
        )
        status = response.status
        headers = response.headers
        body = response.body()

    if status != 200:
        raise RuntimeError(f"backend replay returned HTTP {status}")
    content_type = headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise RuntimeError(f"backend replay returned non-JSON content type {content_type!r}")
    try:
        response_json = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("backend replay response was not valid UTF-8 JSON") from exc

    artifact = {
        "schema_version": 1,
        "privacy": {
            "cookies_recorded": False,
            "authorization_recorded": False,
            "output_location_expected_private": True,
        },
        "probe": {
            "rank": args.rank,
            "event_id": row["event_id"],
            "event_date_from_export": row["event_date_from_export"],
        },
        "request": {
            "method": "POST",
            "url": BACKEND_URL,
            "payload": payload,
        },
        "response": {
            "status": status,
            "content_type": content_type,
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_bytes": len(body),
            "shape": response_shape(response_json),
            "json": response_json,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    shape = artifact["response"]["shape"]
    print(f"Backend replay HTTP {status}: {BACKEND_URL}")
    print(f"EventID {row['event_id']} rank {args.rank}")
    print(f"Response SHA256: {artifact['response']['body_sha256']}")
    print(f"Response bytes: {len(body)}")
    print("Response shape: " + json.dumps(shape, ensure_ascii=False, sort_keys=True))
    print(f"Wrote private replay artifact: {args.out}")
    print("No Cookie or Authorization values are written to the artifact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
