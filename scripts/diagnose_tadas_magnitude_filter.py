#!/usr/bin/env python3
"""Diagnose whether TADAS fromMagnitude filters event-specific waveform searches.

Infrastructure/data-selection diagnostic only. The frozen SeismicShield-RL eligibility
criteria do not include earthquake magnitude, so this script compares otherwise-identical
backend requests for one queue event below magnitude 3 using the live authenticated request
contract. Sensitive authorization/header values remain in memory only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

if __package__:
    from scripts import screen_afad_tadas_backend as backend
    from scripts import screen_afad_tadas_station_summaries as base
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    import screen_afad_tadas_backend as backend
    import screen_afad_tadas_station_summaries as base
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

DEFAULT_OUT = Path("data/private/tadas-magnitude-filter-diagnostic.json")


def parse_magnitude(value: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"non-numeric queue magnitude {value!r}") from exc


def select_sub3_event(rows: list[dict[str, str]], requested_rank: int = 0) -> dict[str, str]:
    if requested_rank:
        if not 1 <= requested_rank <= len(rows):
            raise ValueError("requested rank is outside queue")
        row = rows[requested_rank - 1]
        mag = parse_magnitude(row.get("magnitude", ""))
        if mag is None or mag >= 3.0:
            raise ValueError(f"rank {requested_rank} is not a known-magnitude event below M3")
        return row
    for row in rows:
        mag = parse_magnitude(row.get("magnitude", ""))
        if mag is not None and mag < 3.0:
            return row
    raise ValueError("queue contains no known-magnitude event below M3")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def response_summary(value: object, expected_event_id: str) -> dict[str, object]:
    screen = backend.summarize_backend_json(value, expected_event_id)
    return {
        "row_count": screen["backend_row_count"],
        "unique_station_count": screen["unique_station_count"],
        "stations_at_or_above_threshold": screen["stations_at_or_above_threshold"],
        "max_summary_pga_cm_s2": screen["max_summary_pga_cm_s2"],
        "status": screen["status"],
        "canonical_json_sha256": hashlib.sha256(canonical_json_bytes(value)).hexdigest(),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("queue", type=Path)
    p.add_argument("--rank", type=int, default=0, help="optional known-magnitude rank below M3")
    p.add_argument("--bootstrap-rank", type=int, default=248)
    p.add_argument("--profile-dir", type=Path, default=base.DEFAULT_PROFILE_DIR)
    p.add_argument("--pad-days", type=int, default=1)
    p.add_argument("--timeout-ms", type=int, default=30000)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    rows = base.read_queue(args.queue)
    target = select_sub3_event(rows, args.rank)
    magnitude = parse_magnitude(target.get("magnitude", ""))
    assert magnitude is not None and magnitude < 3.0
    if not 1 <= args.bootstrap_rank <= len(rows):
        p.error("--bootstrap-rank outside queue")

    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-magnitude-filter-bootstrap-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        assert browser.context is not None
        template, headers, shift = backend._bootstrap(
            browser, rows[args.bootstrap_rank - 1], pad_days=args.pad_days, timeout_ms=args.timeout_ms
        )
        base_payload = backend.build_payload_from_live_template(
            template, target, pad_days=args.pad_days, shift=shift
        )

        payload_m3 = copy.deepcopy(base_payload)
        payload_m3["fromMagnitude"] = 3
        payload_null = copy.deepcopy(base_payload)
        payload_null["fromMagnitude"] = None

        def post(payload: dict[str, object]) -> tuple[int, str, object]:
            resp = browser.context.request.post(
                backend.BACKEND_URL,
                data=json.dumps(payload, separators=(",", ":")),
                headers=headers,
                timeout=args.timeout_ms,
            )
            body = resp.body()
            content_type = resp.headers.get("content-type", "")
            if resp.status != 200:
                raise RuntimeError(f"GetWaveforms returned HTTP {resp.status}")
            if "json" not in content_type.lower():
                raise RuntimeError(f"GetWaveforms returned non-JSON content type {content_type!r}")
            try:
                value = json.loads(body.decode("utf-8-sig"))
            except Exception as exc:
                raise RuntimeError("GetWaveforms returned invalid JSON") from exc
            return resp.status, content_type, value

        status_m3, ct_m3, value_m3 = post(payload_m3)
        status_null, ct_null, value_null = post(payload_null)

    summary_m3 = response_summary(value_m3, target["event_id"])
    summary_null = response_summary(value_null, target["event_id"])
    same_json = canonical_json_bytes(value_m3) == canonical_json_bytes(value_null)
    same_screen = all(
        summary_m3[key] == summary_null[key]
        for key in (
            "row_count",
            "unique_station_count",
            "stations_at_or_above_threshold",
            "max_summary_pga_cm_s2",
            "status",
        )
    )

    artifact = {
        "schema_version": 1,
        "privacy": {
            "authorization_recorded": False,
            "cookies_recorded": False,
            "sensitive_header_values_recorded": False,
            "output_location_expected_private": True,
        },
        "target": {
            "rank": int(target["rank"]),
            "event_id": target["event_id"],
            "magnitude": magnitude,
            "magnitude_type": target.get("magnitude_type", ""),
            "event_date_from_export": target["event_date_from_export"],
        },
        "request_a": {"fromMagnitude": 3, "http_status": status_m3, "content_type": ct_m3},
        "request_b": {"fromMagnitude": None, "http_status": status_null, "content_type": ct_null},
        "summary_a": summary_m3,
        "summary_b": summary_null,
        "canonical_json_identical": same_json,
        "prescreen_summary_identical": same_screen,
        "interpretation": (
            "NO_OBSERVED_FILTER_EFFECT" if same_json else
            "JSON_DIFFERS_BUT_PRESCREEN_IDENTICAL" if same_screen else
            "MAGNITUDE_FILTER_AFFECTS_EVENT_SPECIFIC_RESULT"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Target rank {target['rank']} EventID {target['event_id']} magnitude={magnitude:g}")
    print(f"fromMagnitude=3: rows={summary_m3['row_count']}, maxPGA={summary_m3['max_summary_pga_cm_s2']:.6g}, above={summary_m3['stations_at_or_above_threshold']}, status={summary_m3['status']}")
    print(f"fromMagnitude=null: rows={summary_null['row_count']}, maxPGA={summary_null['max_summary_pga_cm_s2']:.6g}, above={summary_null['stations_at_or_above_threshold']}, status={summary_null['status']}")
    print(f"Canonical JSON identical: {'yes' if same_json else 'no'}")
    print(f"Prescreen summary identical: {'yes' if same_screen else 'no'}")
    print(f"Interpretation: {artifact['interpretation']}")
    print(f"Wrote private diagnostic artifact: {args.out}")
    print("No Cookie, Authorization, CSRF/XSRF, or other sensitive header values are written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
