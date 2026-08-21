#!/usr/bin/env python3
"""Select the frozen four ESM records per selected event from the exhaustive inventory.

This is preregistration/data-selection infrastructure only. It consumes the already frozen
40-event preview and the complete exhaustive record inventory, recomputes every salted record
hash from canonical identity, and selects the first four records per event by
(record_hash, record_id). It writes a deterministic 160-row selection CSV plus a provenance
audit JSON. It does not create the final ground-motion manifest, assign partitions, submit OSF
registration, create the source tag, enable the confirmatory gate, or inspect confirmatory results.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts.ground_motion_manifest import ESM_SOURCE, SALT, sha_key

DEFAULT_SELECTED_EVENTS = Path("results/local/esm/esm_selected_event_preview.csv")
DEFAULT_INVENTORY = Path("results/local/esm/esm_selected_event_record_inventory.json")
DEFAULT_OUTPUT = Path("results/local/esm/esm_selected_records_160.csv")
DEFAULT_AUDIT = Path("results/local/esm/esm_selected_records_160.audit.json")
EXPECTED_EVENTS = 40
RECORDS_PER_EVENT = 4
EXPECTED_RECORDS = EXPECTED_EVENTS * RECORDS_PER_EVENT
COMPLETE_STATUS = "COMPLETE_RECORD_INVENTORY"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

OUTPUT_COLUMNS = (
    "event_rank",
    "event_id",
    "record_rank",
    "source",
    "record_id",
    "record_hash",
    "stream",
    "raw_filename",
    "network_code",
    "station_id",
    "location_code",
    "source_member_sha256",
    "source_zip_sha256",
    "source_request_url",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _event_order(path: Path) -> list[tuple[int, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_EVENTS:
        raise ValueError(f"selected-event preview must contain exactly {EXPECTED_EVENTS} rows")
    ordered: list[tuple[int, str]] = []
    seen: set[str] = set()
    for expected_rank, row in enumerate(rows, start=1):
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("selected-event preview contains blank event_id")
        try:
            rank = int(str(row.get("rank", "")).strip())
        except ValueError as exc:
            raise ValueError(f"selected event {event_id!r} has invalid rank") from exc
        if rank != expected_rank:
            raise ValueError(
                f"selected-event preview rank sequence is not canonical: expected {expected_rank}, found {rank}"
            )
        if event_id in seen:
            raise ValueError(f"selected-event preview contains duplicate event_id {event_id!r}")
        seen.add(event_id)
        ordered.append((rank, event_id))
    return ordered


def _inventory_by_event(path: Path) -> dict[str, dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("record-inventory ledger must be a JSON list")
    mapping: dict[str, dict[str, Any]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            raise ValueError("record-inventory ledger contains a non-object row")
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("record-inventory ledger contains blank event_id")
        if event_id in mapping:
            raise ValueError(f"record-inventory ledger contains duplicate event_id {event_id!r}")
        mapping[event_id] = row
    return mapping


def _pick_four(event_id: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    if row.get("status") != COMPLETE_STATUS:
        raise ValueError(f"selected event {event_id} does not have a complete record inventory")
    if int(row.get("waveform_errors") or 0) != 0:
        raise ValueError(f"selected event {event_id} has nonzero waveform_errors")
    records = row.get("passing_records_hash_order_preview")
    if not isinstance(records, list):
        raise ValueError(f"selected event {event_id} has no passing-record inventory list")
    if len(records) < RECORDS_PER_EVENT:
        raise ValueError(f"selected event {event_id} has fewer than four passing records")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"selected event {event_id} contains a non-object record")
        source = str(record.get("source", "")).strip()
        record_id = str(record.get("record_id", "")).strip()
        if source != ESM_SOURCE:
            raise ValueError(f"selected event {event_id} contains non-ESM record source {source!r}")
        if not record_id:
            raise ValueError(f"selected event {event_id} contains blank record_id")
        if record_id in seen_ids:
            raise ValueError(f"selected event {event_id} contains duplicate record_id {record_id!r}")
        seen_ids.add(record_id)

        expected_hash = sha_key(
            "record",
            {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id},
        )
        preview_hash = str(record.get("record_hash_preview", "")).strip()
        if preview_hash != expected_hash:
            raise ValueError(f"selected event {event_id} record {record_id!r} has a noncanonical hash")

        member_sha = str(record.get("source_member_sha256", "")).strip().lower()
        zip_sha = str(record.get("source_zip_sha256", "")).strip().lower()
        if not SHA256_RE.fullmatch(member_sha):
            raise ValueError(f"selected event {event_id} record {record_id!r} has invalid member SHA-256")
        if not SHA256_RE.fullmatch(zip_sha):
            raise ValueError(f"selected event {event_id} record {record_id!r} has invalid ZIP SHA-256")
        if not str(record.get("source_request_url", "")).strip():
            raise ValueError(f"selected event {event_id} record {record_id!r} has blank source request URL")

        normalized.append({**record, "record_hash_preview": expected_hash})

    normalized.sort(key=lambda item: (item["record_hash_preview"], str(item["record_id"])))
    return normalized[:RECORDS_PER_EVENT]


def build_selection(
    selected_events: list[tuple[int, str]],
    inventory: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    selected_ids = {event_id for _, event_id in selected_events}
    missing = sorted(selected_ids - set(inventory))
    if missing:
        raise ValueError(f"record-inventory ledger is missing selected events: {', '.join(missing)}")

    output: list[dict[str, str]] = []
    for event_rank, event_id in selected_events:
        chosen = _pick_four(event_id, inventory[event_id])
        for record_rank, record in enumerate(chosen, start=1):
            raw_filename = str(record.get("file_name") or record.get("raw_filename") or record.get("record_id") or "").strip()
            output.append(
                {
                    "event_rank": str(event_rank),
                    "event_id": event_id,
                    "record_rank": str(record_rank),
                    "source": ESM_SOURCE,
                    "record_id": str(record["record_id"]),
                    "record_hash": str(record["record_hash_preview"]),
                    "stream": str(record.get("stream", "")),
                    "raw_filename": raw_filename,
                    "network_code": str(record.get("network") or record.get("network_code") or ""),
                    "station_id": str(record.get("station_code") or record.get("station_id") or ""),
                    "location_code": str(record.get("location") or record.get("location_code") or ""),
                    "source_member_sha256": str(record.get("source_member_sha256", "")),
                    "source_zip_sha256": str(record.get("source_zip_sha256", "")),
                    "source_request_url": str(record.get("source_request_url", "")),
                }
            )

    if len(output) != EXPECTED_RECORDS:
        raise ValueError(f"deterministic selection produced {len(output)} rows; expected {EXPECTED_RECORDS}")
    identities = {(row["event_id"], row["record_id"]) for row in output}
    if len(identities) != EXPECTED_RECORDS:
        raise ValueError("deterministic selection contains duplicate event/record identities")
    return output


def write_selection(rows: list[dict[str, str]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return _sha256_path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-events", type=Path, default=DEFAULT_SELECTED_EVENTS)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    try:
        selected_events = _event_order(args.selected_events)
        inventory = _inventory_by_event(args.inventory)
        rows = build_selection(selected_events, inventory)
        output_sha = write_selection(rows, args.output)
        audit = {
            "audit_type": "ESM_DETERMINISTIC_FOUR_RECORD_SELECTION",
            "canonical_source": ESM_SOURCE,
            "final_manifest": False,
            "frozen_salt": SALT,
            "generated_at_utc": _now_utc(),
            "selected_events": EXPECTED_EVENTS,
            "records_per_event": RECORDS_PER_EVENT,
            "selected_records": EXPECTED_RECORDS,
            "record_key_formula": "SHA-256(salt + ':record:' + source + ':' + event_id + ':' + record_id)",
            "ordering": "ascending record_hash, then record_id tie-break",
            "selected_event_preview": str(args.selected_events),
            "selected_event_preview_sha256": _sha256_path(args.selected_events),
            "source_inventory": str(args.inventory),
            "source_inventory_sha256": _sha256_path(args.inventory),
            "selected_records_csv": str(args.output),
            "selected_records_csv_sha256": output_sha,
            "notes": [
                "All 40 selected events must have COMPLETE_RECORD_INVENTORY with zero waveform errors.",
                "Every stored record hash is recomputed from the frozen salt and canonical ESM identity before selection.",
                "Exactly four records per event are selected; no partition assignment or final manifest is produced here.",
                "No OSF registration, source tag, confirmatory-gate enablement, or confirmatory result is produced.",
            ],
        }
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(f"Selected ESM events: {EXPECTED_EVENTS}")
    print(f"Records per event: {RECORDS_PER_EVENT}")
    print(f"Selected records: {EXPECTED_RECORDS}")
    print(f"Wrote deterministic selection: {args.output}")
    print(f"Selection SHA-256: {output_sha}")
    print(f"Wrote audit: {args.audit_out}")
    print("No final manifest, partition assignment, OSF registration, source tag, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
