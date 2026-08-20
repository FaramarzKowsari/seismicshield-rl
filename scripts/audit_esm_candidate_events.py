#!/usr/bin/env python3
"""Audit ESM prescreen candidates with authoritative Event-Data ASCII components.

Source-discovery/data-selection infrastructure only. This script consumes the broad ESM
necessary-condition candidate inventory, retrieves only the candidate waveform identities via the
public Event-Data service, and applies the already-frozen component checks to authoritative ASCII
headers. An event is source-eligible once at least four distinct horizontal acceleration records
pass. If fewer than four pass and any candidate waveform failed to audit, the event remains
ERROR_INCOMPLETE_COMPONENT_AUDIT rather than being falsely rejected.

The audit is resumable. Raw ESM ZIPs stay under data/private and are not publication artifacts.
No cross-source AFAD/ESM deduplication, source ordering, final 40-event selection, manifest, OSF
registration, source tag, or confirmatory simulation/result is produced here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from scripts.probe_esm_eventdata_direct import (
    EVENTDATA_BASE,
    PGA_THRESHOLD_CM_S2,
    inspect_ascii_zip,
    normalize_instrument_pattern,
    normalize_location,
    normalize_processing,
    parse_header,
)

DEFAULT_CANDIDATES = Path("results/local/esm/dataset_selection_event_candidates.json")
DEFAULT_LEDGER = Path("results/local/esm/eventdata_component_event_audit.json")
DEFAULT_SUMMARY = Path("results/local/esm/eventdata_component_event_audit_summary.json")
DEFAULT_RAW_DIR = Path("data/private/esm/eventdata-candidate-audit")
TERMINAL_STATUSES = {"ELIGIBLE_EVENT_COMPONENT_AUDIT", "REJECT_COMPONENT_AUDIT"}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text or "unknown"


def _float(value: Any) -> float | None:
    try:
        if value is None or not str(value).strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_eventdata_url(event_id: str, waveform: dict[str, Any]) -> str:
    row = {
        "event_id": event_id,
        "net_name": waveform.get("network"),
        "station_code": waveform.get("station"),
        "location_code": waveform.get("location"),
        "instr_code": waveform.get("instrument"),
        "processing_type": waveform.get("processing_type"),
    }
    quality = str(waveform.get("quality_class") or "").strip().upper()
    query = {
        "eventid": event_id,
        "catalog": "ESM",
        "network": str(row["net_name"] or "").strip(),
        "station": str(row["station_code"] or "").strip(),
        "location": normalize_location(row.get("location_code")),
        "channel": normalize_instrument_pattern(row.get("instr_code")),
        "format": "ascii",
        "processing-type": normalize_processing(row.get("processing_type")),
        "data-type": "ACC",
    }
    if quality in {"BEST", "GOOD", "BAD", "UNDEF"}:
        query["quality-class"] = quality
    return EVENTDATA_BASE + "?" + urlencode(query)


def fetch_bytes(url: str, timeout_s: float) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "SeismicShield-RL/0.8 ESM candidate component audit"})
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed HTTPS ESM service
            body = response.read()
            status = int(getattr(response, "status", response.getcode()))
            content_type = response.headers.get("Content-Type", "")
        return status, content_type, body
    except HTTPError as exc:
        excerpt = exc.read(1200).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}; ESM response: {excerpt}") from exc


def _probe_row(event_id: str, waveform: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "net_name": waveform.get("network"),
        "station_code": waveform.get("station"),
        "location_code": waveform.get("location"),
        "instr_code": waveform.get("instrument"),
        "processing_type": waveform.get("processing_type"),
        "class": waveform.get("quality_class"),
        "corr_hz_PGA": waveform.get("corr_hz_PGA_cm_s2"),
    }


def _stream_family_matches(stream: str, instrument: Any) -> bool:
    family = str(instrument or "").strip().upper()[:2]
    stream = str(stream or "").strip().upper()
    return len(family) == 2 and stream.startswith(family)


def passing_records(inspection: dict[str, Any], waveform: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for component in inspection.get("components", []):
        if not component.get("component_pass"):
            continue
        if not _stream_family_matches(str(component.get("stream", "")), waveform.get("instrument")):
            continue
        records.append(component)
    return records


def extract_event_metadata(body: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            return {}
        header = parse_header(archive.read(names[0]).decode("utf-8-sig", errors="replace"))
    return {
        "event_id_header": header.get("EVENT_ID"),
        "event_date_yyyymmdd": header.get("EVENT_DATE_YYYYMMDD"),
        "event_time_hhmmss": header.get("EVENT_TIME_HHMMSS"),
        "event_latitude_degree": _float(header.get("EVENT_LATITUDE_DEGREE")),
        "event_longitude_degree": _float(header.get("EVENT_LONGITUDE_DEGREE")),
        "event_depth_km": _float(header.get("EVENT_DEPTH_KM")),
        "magnitude_w": _float(header.get("MAGNITUDE_W")),
        "magnitude_l": _float(header.get("MAGNITUDE_L")),
        "hypocenter_reference": header.get("HYPOCENTER_REFERENCE"),
        "data_citation": header.get("DATA_CITATION"),
    }


def record_identity(component: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(component.get("event_id", "")).strip(),
        str(component.get("network", "")).strip(),
        str(component.get("station_code", "")).strip(),
        str(component.get("location", "")).strip(),
        str(component.get("stream", "")).strip().upper(),
    )


def audit_event(
    event: dict[str, Any],
    raw_dir: Path,
    timeout_s: float,
    delay_s: float,
) -> dict[str, Any]:
    event_id = str(event.get("event_id", "")).strip()
    if not event_id:
        raise ValueError("candidate event is missing event_id")
    waveforms = list(event.get("candidate_waveforms") or [])
    if not waveforms:
        raise ValueError(f"candidate event {event_id} has no candidate_waveforms")

    event_dir = raw_dir / _safe(event_id)
    event_dir.mkdir(parents=True, exist_ok=True)
    unique_pass: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    waveform_results: list[dict[str, Any]] = []
    errors = 0
    metadata: dict[str, Any] = {}

    for index, waveform in enumerate(waveforms, start=1):
        if len(unique_pass) >= 4:
            break
        url = build_eventdata_url(event_id, waveform)
        label = "__".join(
            _safe(waveform.get(key)) for key in ("network", "station", "location", "instrument")
        )
        zip_path = event_dir / f"{index:03d}__{label}.zip"
        try:
            status, content_type, body = fetch_bytes(url, timeout_s)
            if status != 200:
                raise RuntimeError(f"ESM Event-Data returned HTTP {status}")
            if not zipfile.is_zipfile(io.BytesIO(body)):
                raise RuntimeError("ESM Event-Data response is not a ZIP archive")
            zip_path.write_bytes(body)
            inspection = inspect_ascii_zip(body, _probe_row(event_id, waveform))
            if not metadata:
                metadata = extract_event_metadata(body)
            passed = passing_records(inspection, waveform)
            for component in passed:
                unique_pass.setdefault(record_identity(component), component)
            waveform_results.append(
                {
                    "status": "AUDITED",
                    "request_url": url,
                    "network": waveform.get("network"),
                    "station": waveform.get("station"),
                    "location": waveform.get("location"),
                    "instrument": waveform.get("instrument"),
                    "processing_type": waveform.get("processing_type"),
                    "quality_class": waveform.get("quality_class"),
                    "prescreen_corr_hz_PGA_cm_s2": waveform.get("corr_hz_PGA_cm_s2"),
                    "http_status": status,
                    "content_type": content_type,
                    "zip_sha256": hashlib.sha256(body).hexdigest(),
                    "zip_bytes": len(body),
                    "zip_path": str(zip_path),
                    "passing_horizontal_records_added": len(passed),
                    "inspection": inspection,
                }
            )
        except Exception as exc:  # noqa: BLE001 - ledger must preserve source/network failures
            errors += 1
            waveform_results.append(
                {
                    "status": "ERROR",
                    "request_url": url,
                    "network": waveform.get("network"),
                    "station": waveform.get("station"),
                    "location": waveform.get("location"),
                    "instrument": waveform.get("instrument"),
                    "processing_type": waveform.get("processing_type"),
                    "quality_class": waveform.get("quality_class"),
                    "prescreen_corr_hz_PGA_cm_s2": waveform.get("corr_hz_PGA_cm_s2"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if delay_s > 0:
            time.sleep(delay_s)

    pass_count = len(unique_pass)
    if pass_count >= 4:
        status = "ELIGIBLE_EVENT_COMPONENT_AUDIT"
    elif errors:
        status = "ERROR_INCOMPLETE_COMPONENT_AUDIT"
    else:
        status = "REJECT_COMPONENT_AUDIT"

    return {
        "event_id": event_id,
        "status": status,
        "audited_at_utc": _now_utc(),
        "prescreen_event_times": event.get("event_times", []),
        "prescreen_rows_at_or_above_0p15g": event.get("rows_at_or_above_0p15g"),
        "prescreen_max_corr_hz_PGA_cm_s2": event.get("max_corr_hz_PGA_cm_s2"),
        "candidate_waveforms_total": len(waveforms),
        "candidate_waveforms_audited": len(waveform_results),
        "waveform_errors": errors,
        "early_stop_after_four_passing_horizontals": pass_count >= 4 and len(waveform_results) < len(waveforms),
        "passing_horizontal_count": pass_count,
        "passing_horizontal_records": list(unique_pass.values()),
        "event_metadata": metadata,
        "waveforms": waveform_results,
    }


def load_ledger(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError(f"ledger must contain a JSON list: {path}")
    return {str(row.get("event_id", "")): row for row in parsed if isinstance(row, dict)}


def save_ledger(path: Path, ledger: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(ledger.values(), key=lambda row: str(row.get("event_id", "")))
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary_payload(ledger: dict[str, dict[str, Any]], candidates_count: int) -> dict[str, Any]:
    rows = list(ledger.values())
    eligible = sum(row.get("status") == "ELIGIBLE_EVENT_COMPONENT_AUDIT" for row in rows)
    rejected = sum(row.get("status") == "REJECT_COMPONENT_AUDIT" for row in rows)
    incomplete = sum(row.get("status") == "ERROR_INCOMPLETE_COMPONENT_AUDIT" for row in rows)
    return {
        "audit_type": "ESM_EVENTDATA_COMPONENT_EVENT_AUDIT_SOURCE_DISCOVERY_ONLY",
        "final_manifest": False,
        "generated_at_utc": _now_utc(),
        "prescreen_candidate_events": candidates_count,
        "events_in_ledger": len(rows),
        "eligible_events": eligible,
        "rejected_events": rejected,
        "incomplete_error_events": incomplete,
        "pga_threshold_cm_s2": PGA_THRESHOLD_CM_S2,
        "notes": [
            "Final component eligibility is based on authoritative Event-Data ASCII headers.",
            "An event is source-eligible only after at least four distinct horizontal acceleration records pass the frozen component checks.",
            "Events with fewer than four passing horizontals and any unaudited/error waveform remain incomplete rather than being rejected.",
            "Eligible-event audits may stop after four passing horizontals; selected final records are intentionally not chosen here.",
            "No AFAD/ESM deduplication, source ordering, final 40-event selection, manifest, OSF registration, source tag, or confirmatory result is produced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--delay-s", type=float, default=0.10)
    parser.add_argument("--max-events", type=int, default=0, help="0 means audit all non-terminal candidates")
    args = parser.parse_args()
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")
    if args.delay_s < 0:
        parser.error("--delay-s must be >= 0")
    if args.max_events < 0:
        parser.error("--max-events must be >= 0")
    if not args.candidates.exists():
        parser.error(f"candidate inventory not found: {args.candidates}")

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        parser.error("candidate inventory must contain a JSON list")
    ledger = load_ledger(args.ledger)
    processed = 0

    print(f"ESM prescreen candidate events: {len(candidates)}")
    for ordinal, event in enumerate(candidates, start=1):
        event_id = str(event.get("event_id", "")).strip()
        previous = ledger.get(event_id)
        if previous and previous.get("status") in TERMINAL_STATUSES:
            continue
        if args.max_events and processed >= args.max_events:
            break
        print(
            f"[candidate {ordinal}/{len(candidates)}] EventID {event_id} "
            f"prescreen waveforms={len(event.get('candidate_waveforms') or [])} ...",
            flush=True,
        )
        result = audit_event(event, args.raw_dir, args.timeout_s, args.delay_s)
        ledger[event_id] = result
        save_ledger(args.ledger, ledger)
        processed += 1
        print(
            f"  {result['status']}: pass horizontals={result['passing_horizontal_count']} "
            f"audited waveforms={result['candidate_waveforms_audited']}/{result['candidate_waveforms_total']} "
            f"errors={result['waveform_errors']}",
            flush=True,
        )

    summary = summary_payload(ledger, len(candidates))
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Event component-audit ledger: {args.ledger}")
    print(f"Eligible events accumulated: {summary['eligible_events']}")
    print(f"Rejected events accumulated: {summary['rejected_events']}")
    print(f"Incomplete/error events: {summary['incomplete_error_events']}")
    print(f"Events in ledger: {summary['events_in_ledger']} / {len(candidates)}")
    print("Raw ESM ZIPs remain under data/private and are not publication artifacts.")
    print("No final source ordering, manifest, OSF registration, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
