#!/usr/bin/env python3
"""Exhaustively inventory eligible ESM records for the 40-event selection preview.

Preregistration/data-selection infrastructure only. Unlike the earlier event-eligibility audit,
this pass MUST NOT stop after four passing horizontals: every prescreen waveform identity for each
selected event is audited so later salted record ordering cannot depend on request order or early
stopping. Source-distributed ESM MP ASCII members are sample-count/PGA checked against their own
headers and hashed individually. No final four-record choice, partition assignment, final manifest,
OSF registration, source tag, or confirmatory result is produced here.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import time
from typing import Any
import zipfile

from scripts.audit_esm_candidate_events import (
    _probe_row,
    build_eventdata_url,
    fetch_bytes,
    passing_records,
)
from scripts.ground_motion_manifest import PGA_TOLERANCE_CM_S2, sha_key
from scripts.probe_esm_eventdata_direct import inspect_ascii_zip, parse_header

ESM_SOURCE = "ESM"
DEFAULT_SELECTED = Path("results/local/esm/esm_selected_event_preview.csv")
DEFAULT_CANDIDATES = Path("results/local/esm/dataset_selection_event_candidates.json")
DEFAULT_LEDGER = Path("results/local/esm/esm_selected_event_record_inventory.json")
DEFAULT_SUMMARY = Path("results/local/esm/esm_selected_event_record_inventory_summary.json")
DEFAULT_RAW_DIR = Path("data/private/esm/eventdata-candidate-audit")
COMPLETE = "COMPLETE_RECORD_INVENTORY"
INCOMPLETE = "ERROR_INCOMPLETE_RECORD_INVENTORY"
INCONSISTENT = "REJECT_INCONSISTENT_RECORD_INVENTORY"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return text or "unknown"


def load_selected_event_ids(path: Path, expected_count: int = 40) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    event_ids = [str(row.get("event_id", "")).strip() for row in rows]
    if len(event_ids) != expected_count:
        raise ValueError(f"selected-event preview must contain exactly {expected_count} rows")
    if any(not event_id for event_id in event_ids):
        raise ValueError("selected-event preview contains blank event_id")
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("selected-event preview contains duplicate event_id")
    return event_ids


def load_candidates(path: Path) -> dict[str, dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("ESM candidate inventory must be a JSON list")
    mapping: dict[str, dict[str, Any]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            raise ValueError("ESM candidate inventory contains a non-object row")
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("ESM candidate inventory contains blank event_id")
        if event_id in mapping:
            raise ValueError(f"duplicate ESM candidate event_id {event_id!r}")
        mapping[event_id] = row
    return mapping


def parse_numeric_samples(text: str) -> list[float]:
    """Parse the numeric DYNA sample section without treating numeric header values as samples."""
    samples: list[float] = []
    started = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not started:
            if ":" in line:
                continue
            tokens = line.replace(",", " ").split()
            try:
                values = [float(token) for token in tokens]
            except ValueError:
                continue
            if not values:
                continue
            started = True
            samples.extend(values)
            continue
        tokens = line.replace(",", " ").split()
        if not tokens:
            continue
        try:
            samples.extend(float(token) for token in tokens)
        except ValueError as exc:
            raise ValueError("non-numeric text encountered after DYNA sample section began") from exc
    if not samples:
        raise ValueError("no numeric acceleration samples found in ESM ASCII member")
    if not all(math.isfinite(value) for value in samples):
        raise ValueError("ESM ASCII acceleration samples must all be finite")
    return samples


def validate_member_samples(member_bytes: bytes) -> dict[str, Any]:
    text = member_bytes.decode("utf-8-sig", errors="replace")
    header = parse_header(text)
    samples = parse_numeric_samples(text)
    try:
        ndata = int(header.get("NDATA", ""))
    except ValueError as exc:
        raise ValueError("ESM ASCII member has invalid or missing NDATA") from exc
    if len(samples) != ndata:
        raise ValueError(f"ESM ASCII sample count {len(samples)} disagrees with NDATA {ndata}")
    raw_pga = max(abs(value) for value in samples)
    pga_text = header.get("PGA_CM/S^2", "") or header.get("PGA_CM_S2", "")
    try:
        header_pga = abs(float(pga_text))
    except ValueError as exc:
        raise ValueError("ESM ASCII member has invalid or missing PGA header") from exc
    difference = abs(raw_pga - header_pga)
    if difference > PGA_TOLERANCE_CM_S2 and not math.isclose(
        difference, PGA_TOLERANCE_CM_S2, abs_tol=1e-12
    ):
        raise ValueError(
            f"parsed PGA disagrees with ESM header by {difference:.12g} cm/s^2 (> {PGA_TOLERANCE_CM_S2})"
        )
    return {
        "parsed_sample_count": len(samples),
        "parsed_pga_cm_s2": raw_pga,
        "header_pga_cm_s2": header_pga,
        "pga_abs_difference_cm_s2": difference,
        "source_member_sha256": hashlib.sha256(member_bytes).hexdigest(),
    }


def esm_record_id(file_name: str) -> str:
    """Use the exact source-distributed ESM ASCII basename as the provisional canonical record ID."""
    name = PurePosixPath(str(file_name).replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError("blank/invalid ESM source member filename")
    return name


def _load_ledger(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("record-inventory ledger must be a JSON list")
    return {
        str(row.get("event_id", "")).strip(): row
        for row in parsed
        if isinstance(row, dict) and str(row.get("event_id", "")).strip()
    }


def _save_ledger(path: Path, ledger: dict[str, dict[str, Any]], selected_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [ledger[event_id] for event_id in selected_order if event_id in ledger]
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _zip_path(raw_dir: Path, event_id: str, index: int, waveform: dict[str, Any]) -> Path:
    label = "__".join(_safe(waveform.get(key)) for key in ("network", "station", "location", "instrument"))
    return raw_dir / _safe(event_id) / f"{index:03d}__{label}.zip"


def audit_one_event(
    event_id: str,
    candidate: dict[str, Any],
    raw_dir: Path,
    timeout_s: float,
    delay_s: float,
) -> dict[str, Any]:
    waveforms = list(candidate.get("candidate_waveforms") or [])
    if not waveforms:
        raise ValueError(f"selected ESM event {event_id} has no candidate waveforms")
    unique_records: dict[str, dict[str, Any]] = {}
    waveform_results: list[dict[str, Any]] = []
    errors = 0

    for index, waveform in enumerate(waveforms, start=1):
        url = build_eventdata_url(event_id, waveform)
        zip_path = _zip_path(raw_dir, event_id, index, waveform)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache_used = zip_path.exists() and zipfile.is_zipfile(zip_path)
            if cache_used:
                body = zip_path.read_bytes()
                status = 200
                content_type = "application/zip; cached"
            else:
                status, content_type, body = fetch_bytes(url, timeout_s)
                if status != 200:
                    raise RuntimeError(f"ESM Event-Data returned HTTP {status}")
                if not zipfile.is_zipfile(io.BytesIO(body)):
                    raise RuntimeError("ESM Event-Data response is not a ZIP archive")
                zip_path.write_bytes(body)

            inspection = inspect_ascii_zip(body, _probe_row(event_id, waveform))
            passed = passing_records(inspection, waveform)
            member_checks: dict[str, dict[str, Any]] = {}
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                for component in passed:
                    member_name = str(component.get("file_name", ""))
                    if member_name not in archive.namelist():
                        raise ValueError(f"passing ESM component {member_name!r} missing from ZIP")
                    validation = validate_member_samples(archive.read(member_name))
                    record_id = esm_record_id(member_name)
                    record = {
                        **component,
                        **validation,
                        "source": ESM_SOURCE,
                        "record_id": record_id,
                        "record_hash_preview": sha_key(
                            "record",
                            {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id},
                        ),
                        "source_request_url": url,
                        "source_zip_sha256": hashlib.sha256(body).hexdigest(),
                        "source_zip_path": str(zip_path),
                    }
                    previous = unique_records.get(record_id)
                    if previous is not None and previous["source_member_sha256"] != record["source_member_sha256"]:
                        raise ValueError(f"ESM record_id collision with different bytes: {record_id}")
                    unique_records.setdefault(record_id, record)
                    member_checks[record_id] = validation

            waveform_results.append(
                {
                    "status": "AUDITED",
                    "request_url": url,
                    "cache_used": cache_used,
                    "http_status": status,
                    "content_type": content_type,
                    "zip_path": str(zip_path),
                    "zip_sha256": hashlib.sha256(body).hexdigest(),
                    "network": waveform.get("network"),
                    "station": waveform.get("station"),
                    "location": waveform.get("location"),
                    "instrument": waveform.get("instrument"),
                    "processing_type": waveform.get("processing_type"),
                    "quality_class": waveform.get("quality_class"),
                    "passing_records_in_request": sorted(member_checks),
                }
            )
        except Exception as exc:  # noqa: BLE001 - source/network failures must remain visible
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
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if delay_s > 0:
            time.sleep(delay_s)

    passing = sorted(unique_records.values(), key=lambda row: (row["record_hash_preview"], row["record_id"]))
    if errors:
        status = INCOMPLETE
    elif len(passing) < 4:
        status = INCONSISTENT
    else:
        status = COMPLETE
    return {
        "event_id": event_id,
        "status": status,
        "audited_at_utc": _now_utc(),
        "candidate_waveforms_total": len(waveforms),
        "candidate_waveforms_audited": len(waveform_results),
        "waveform_errors": errors,
        "unique_passing_horizontal_records": len(passing),
        "passing_records_hash_order_preview": passing,
        "waveforms": waveform_results,
        "final_record_selection_performed": False,
    }


def summary_payload(ledger: dict[str, dict[str, Any]], selected_order: list[str]) -> dict[str, Any]:
    rows = [ledger[event_id] for event_id in selected_order if event_id in ledger]
    complete = sum(row.get("status") == COMPLETE for row in rows)
    incomplete = sum(row.get("status") == INCOMPLETE for row in rows)
    inconsistent = sum(row.get("status") == INCONSISTENT for row in rows)
    counts = [int(row.get("unique_passing_horizontal_records") or 0) for row in rows if row.get("status") == COMPLETE]
    return {
        "audit_type": "ESM_SELECTED_EVENT_EXHAUSTIVE_RECORD_INVENTORY_PREVIEW_ONLY",
        "final_manifest": False,
        "generated_at_utc": _now_utc(),
        "selected_events_expected": len(selected_order),
        "events_in_ledger": len(rows),
        "complete_record_inventories": complete,
        "incomplete_error_inventories": incomplete,
        "inconsistent_inventories": inconsistent,
        "minimum_complete_event_passing_records": min(counts) if counts else None,
        "maximum_complete_event_passing_records": max(counts) if counts else None,
        "total_unique_passing_records_across_complete_events": sum(counts),
        "record_id_preview_contract": "exact source-distributed ESM ASCII basename",
        "record_hash_preview_formula": "SHA-256(salt + ':record:' + source + ':' + event_id + ':' + record_id)",
        "notes": [
            "Every prescreen waveform identity for each selected event is audited; there is no early stop at four records.",
            "Source-distributed ASCII member sample count must equal NDATA and parsed PGA must match the header within the frozen 0.01 cm/s^2 tolerance.",
            "Record hashes are previewed only; the final four records per event are intentionally not selected here.",
            "No partition assignment, final manifest, OSF registration, source tag, or confirmatory result is produced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--delay-s", type=float, default=0.10)
    parser.add_argument("--max-events", type=int, default=0, help="0 means all non-complete selected events")
    args = parser.parse_args()
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")
    if args.delay_s < 0:
        parser.error("--delay-s must be >= 0")
    if args.max_events < 0:
        parser.error("--max-events must be >= 0")
    if not args.selected.exists():
        parser.error(f"selected-event preview not found: {args.selected}")
    if not args.candidates.exists():
        parser.error(f"candidate inventory not found: {args.candidates}")

    selected_order = load_selected_event_ids(args.selected)
    candidates = load_candidates(args.candidates)
    missing = [event_id for event_id in selected_order if event_id not in candidates]
    if missing:
        parser.error(f"selected events missing from candidate inventory: {missing[:5]}")
    ledger = _load_ledger(args.ledger)
    processed = 0
    print(f"Selected ESM events for exhaustive record inventory: {len(selected_order)}")
    for ordinal, event_id in enumerate(selected_order, start=1):
        previous = ledger.get(event_id)
        if previous and previous.get("status") == COMPLETE:
            continue
        if args.max_events and processed >= args.max_events:
            break
        candidate = candidates[event_id]
        print(
            f"[selected {ordinal}/{len(selected_order)}] EventID {event_id} "
            f"waveforms={len(candidate.get('candidate_waveforms') or [])} ...",
            flush=True,
        )
        result = audit_one_event(event_id, candidate, args.raw_dir, args.timeout_s, args.delay_s)
        ledger[event_id] = result
        _save_ledger(args.ledger, ledger, selected_order)
        processed += 1
        print(
            f"  {result['status']}: passing records={result['unique_passing_horizontal_records']} "
            f"audited waveforms={result['candidate_waveforms_audited']}/{result['candidate_waveforms_total']} "
            f"errors={result['waveform_errors']}",
            flush=True,
        )

    summary = summary_payload(ledger, selected_order)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Record-inventory ledger: {args.ledger}")
    print(f"Complete record inventories: {summary['complete_record_inventories']}")
    print(f"Incomplete/error inventories: {summary['incomplete_error_inventories']}")
    print(f"Inconsistent inventories: {summary['inconsistent_inventories']}")
    print(f"Events in ledger: {summary['events_in_ledger']} / {len(selected_order)}")
    print(f"Minimum passing records in complete event: {summary['minimum_complete_event_passing_records']}")
    print(f"Maximum passing records in complete event: {summary['maximum_complete_event_passing_records']}")
    print("No final four-record selection, manifest, OSF registration, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
