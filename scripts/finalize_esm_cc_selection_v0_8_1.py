#!/usr/bin/env python3
"""Freeze the final explicit-CC ESM selection for preregistration v0.8.1.

The input is the already-audited 63-event ESM hash queue plus exhaustive record inventories.
Only records whose source-reported per-waveform DATA_LICENSE starts with CC-BY3_0-IT or
CC-BY4_0 are eligible. Events remain in the pre-existing salted event-hash order; events with
fewer than four explicit-CC records are skipped. The first 34 eligible events are frozen and
the first four eligible records per event are selected by the pre-existing salted record order.

This stage does not assign partitions, create the final confirmatory manifest, submit OSF,
create the confirmatory source tag, enable the confirmatory gate, or inspect outcomes.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import ESM_SOURCE, SALT, sha_key  # noqa: E402

DEFAULT_EVENT_QUEUE = Path("results/local/esm/esm_eligible_event_queue.csv")
DEFAULT_INVENTORIES = (
    Path("results/local/esm/esm_selected_event_record_inventory.json"),
    Path("results/local/esm/license_clean_tail_audit.json"),
)
DEFAULT_COMBINED_INVENTORY = Path("results/local/esm/esm_record_inventory_63_complete.json")
DEFAULT_SELECTED_EVENTS = Path("results/local/esm/esm_selected_event_preview_cc34.csv")
DEFAULT_OUTPUT = Path("results/local/esm/esm_selected_records_136.csv")
DEFAULT_AUDIT = Path("results/local/esm/esm_selected_records_136.audit.json")
DEFAULT_LOCK = Path("open_science/ground_motion_selection_lock_v0.8.1.yaml")

EXPECTED_QUEUE_EVENTS = 63
EXPECTED_EVENTS = 34
RECORDS_PER_EVENT = 4
EXPECTED_RECORDS = EXPECTED_EVENTS * RECORDS_PER_EVENT
COMPLETE_STATUS = "COMPLETE_RECORD_INVENTORY"
EXPLICIT_CC_LICENSE_PREFIXES = ("CC-BY3_0-IT", "CC-BY4_0")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SELECTED_EVENT_COLUMNS = (
    "rank", "source_queue_rank", "event_hash", "source", "event_id", "explicit_cc_record_count",
)
OUTPUT_COLUMNS = (
    "event_rank", "source_queue_rank", "event_id", "record_rank", "source", "record_id",
    "record_hash", "stream", "raw_filename", "network_code", "station_id", "location_code",
    "data_license", "source_member_sha256", "source_zip_sha256", "source_request_url",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def explicit_cc_license(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return any(text.startswith(prefix) for prefix in EXPLICIT_CC_LICENSE_PREFIXES)


def load_event_queue(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    if len(rows) != EXPECTED_QUEUE_EVENTS:
        raise ValueError(f"ESM eligible-event queue must contain exactly {EXPECTED_QUEUE_EVENTS} rows")
    seen: set[str] = set()
    for expected_rank, row in enumerate(rows, start=1):
        event_id = row.get("event_id", "")
        if not event_id:
            raise ValueError("ESM event queue contains blank event_id")
        try:
            rank = int(row.get("rank", ""))
        except ValueError as exc:
            raise ValueError(f"ESM queue event {event_id!r} has invalid rank") from exc
        if rank != expected_rank:
            raise ValueError(f"ESM event queue rank sequence is not canonical: expected {expected_rank}, found {rank}")
        if event_id in seen:
            raise ValueError(f"ESM event queue contains duplicate event_id {event_id!r}")
        seen.add(event_id)
        if row.get("source", ESM_SOURCE) not in {"", ESM_SOURCE}:
            raise ValueError(f"ESM event queue contains non-ESM source for {event_id!r}")
        expected_hash = sha_key("event", {"source": ESM_SOURCE, "event_id": event_id})
        if row.get("event_hash", "") != expected_hash:
            raise ValueError(f"ESM queue event {event_id!r} has noncanonical event hash")
    return rows


def _inventory_rows(parsed: Any, path: Path) -> Iterable[dict[str, Any]]:
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        rows = list(parsed.values())
    else:
        raise ValueError(f"inventory {path} must be a JSON list or event-id mapping")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"inventory {path} contains a non-object row")
        yield row


def merge_inventories(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for path in paths:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        for row in _inventory_rows(parsed, path):
            event_id = str(row.get("event_id", "")).strip()
            if not event_id:
                raise ValueError(f"inventory {path} contains blank event_id")
            if event_id in mapping:
                raise ValueError(f"duplicate event_id {event_id!r} across exhaustive inventories")
            mapping[event_id] = row
    return mapping


def _explicit_records(event_id: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    if row.get("status") != COMPLETE_STATUS:
        raise ValueError(f"queue event {event_id} does not have a complete record inventory")
    if int(row.get("waveform_errors") or 0) != 0:
        raise ValueError(f"queue event {event_id} has nonzero waveform_errors")
    records = row.get("passing_records_hash_order_preview")
    if not isinstance(records, list):
        raise ValueError(f"queue event {event_id} has no passing-record inventory list")

    eligible: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"queue event {event_id} contains a non-object record")
        source = str(record.get("source", "")).strip()
        record_id = str(record.get("record_id", "")).strip()
        if source != ESM_SOURCE:
            raise ValueError(f"queue event {event_id} contains non-ESM record source {source!r}")
        if not record_id:
            raise ValueError(f"queue event {event_id} contains blank record_id")
        if record_id in seen_ids:
            raise ValueError(f"queue event {event_id} contains duplicate record_id {record_id!r}")
        seen_ids.add(record_id)
        expected_hash = sha_key("record", {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id})
        if str(record.get("record_hash_preview", "")).strip() != expected_hash:
            raise ValueError(f"queue event {event_id} record {record_id!r} has a noncanonical hash")
        for field in ("source_member_sha256", "source_zip_sha256"):
            value = str(record.get(field, "")).strip().lower()
            if not SHA256_RE.fullmatch(value):
                raise ValueError(f"queue event {event_id} record {record_id!r} has invalid {field}")
        if not str(record.get("source_request_url", "")).strip():
            raise ValueError(f"queue event {event_id} record {record_id!r} has blank source request URL")
        data_license = str(record.get("data_license", "")).strip()
        if explicit_cc_license(data_license):
            eligible.append({**record, "record_hash_preview": expected_hash, "data_license": data_license})
    eligible.sort(key=lambda item: (item["record_hash_preview"], str(item["record_id"])))
    return eligible


def build_selection(queue: list[dict[str, str]], inventory: dict[str, dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    queue_ids = {row["event_id"] for row in queue}
    missing = sorted(queue_ids - set(inventory))
    extra = sorted(set(inventory) - queue_ids)
    if missing:
        raise ValueError(f"exhaustive inventories are missing queue events: {', '.join(missing[:5])}")
    if extra:
        raise ValueError(f"exhaustive inventories contain events outside the frozen queue: {', '.join(extra[:5])}")

    selected_events: list[dict[str, str]] = []
    selected_records: list[dict[str, str]] = []
    for queue_row in queue:
        event_id = queue_row["event_id"]
        explicit = _explicit_records(event_id, inventory[event_id])
        if len(explicit) < RECORDS_PER_EVENT:
            continue
        if len(selected_events) >= EXPECTED_EVENTS:
            continue
        event_rank = len(selected_events) + 1
        source_queue_rank = int(queue_row["rank"])
        selected_events.append({
            "rank": str(event_rank), "source_queue_rank": str(source_queue_rank),
            "event_hash": queue_row["event_hash"], "source": ESM_SOURCE, "event_id": event_id,
            "explicit_cc_record_count": str(len(explicit)),
        })
        for record_rank, record in enumerate(explicit[:RECORDS_PER_EVENT], start=1):
            record_id = str(record["record_id"]).strip()
            selected_records.append({
                "event_rank": str(event_rank), "source_queue_rank": str(source_queue_rank),
                "event_id": event_id, "record_rank": str(record_rank), "source": ESM_SOURCE,
                "record_id": record_id, "record_hash": str(record["record_hash_preview"]),
                "stream": str(record.get("stream", "")), "raw_filename": record_id,
                "network_code": str(record.get("network") or record.get("network_code") or ""),
                "station_id": str(record.get("station_code") or record.get("station_id") or ""),
                "location_code": str(record.get("location") or record.get("location_code") or ""),
                "data_license": str(record["data_license"]),
                "source_member_sha256": str(record.get("source_member_sha256", "")),
                "source_zip_sha256": str(record.get("source_zip_sha256", "")),
                "source_request_url": str(record.get("source_request_url", "")),
            })

    if len(selected_events) != EXPECTED_EVENTS:
        raise ValueError(f"frozen 63-event queue contains {len(selected_events)} events with >=4 explicit-CC records; expected {EXPECTED_EVENTS}")
    if len(selected_records) != EXPECTED_RECORDS:
        raise ValueError(f"license-clean selection produced {len(selected_records)} records; expected {EXPECTED_RECORDS}")
    if len({(row["event_id"], row["record_id"]) for row in selected_records}) != EXPECTED_RECORDS:
        raise ValueError("license-clean selection contains duplicate event/record identities")
    return selected_events, selected_records


def _write_csv(rows: list[dict[str, str]], path: Path, columns: tuple[str, ...]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return _sha256_path(path)


def write_combined_inventory(queue: list[dict[str, str]], inventory: dict[str, dict[str, Any]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([inventory[row["event_id"]] for row in queue], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256_path(path)


def write_lock(path: Path, *, selection_path: Path, selection_sha: str, inventory_path: Path, inventory_sha: str, event_path: Path, event_sha: str, queue_path: Path, queue_sha: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "version: v0.8.1",
            "status: explicit_cc_license_clean_selection_frozen_pre_registration",
            "canonical_source: ESM",
            f"source_queue_events: {EXPECTED_QUEUE_EVENTS}",
            f"selected_events: {EXPECTED_EVENTS}",
            f"records_per_event: {RECORDS_PER_EVENT}",
            f"selected_records: {EXPECTED_RECORDS}",
            "license_policy:",
            "  accepted_prefixes: [CC-BY3_0-IT, CC-BY4_0]",
            "  network_default_license_accepted: false",
            "  unknown_license_accepted: false",
            "selection_method:",
            "  event_order: existing ascending salted event_hash; license-ineligible events skipped",
            "  record_order: ascending salted record_hash then record_id; non-explicit-CC records excluded",
            "local_selection_artifact:",
            f"  path: {selection_path.as_posix()}",
            f"  sha256: {selection_sha}",
            "source_inventory:",
            f"  path: {inventory_path.as_posix()}",
            f"  sha256_at_selection: {inventory_sha}",
            "selected_event_preview:",
            f"  path: {event_path.as_posix()}",
            f"  sha256: {event_sha}",
            "source_event_queue:",
            f"  path: {queue_path.as_posix()}",
            f"  sha256: {queue_sha}",
            "scientific_state:",
            "  partitions_assigned: false",
            "  osf_registration_submitted: false",
            "  confirmatory_runs_allowed: false",
            "notes:",
            "  - License filtering was finalized before OSF registration and before any confirmatory outcome was inspected.",
            "  - D (network default license) and U (unknown license) records are excluded without reinterpretation.",
            "  - The v0.8.0 salt and hash ordering are preserved; only the explicit-license eligibility gate is added.",
            "",
        ]), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-queue", type=Path, default=DEFAULT_EVENT_QUEUE)
    parser.add_argument("--inventory", type=Path, action="append", dest="inventories")
    parser.add_argument("--combined-inventory-out", type=Path, default=DEFAULT_COMBINED_INVENTORY)
    parser.add_argument("--selected-events-out", type=Path, default=DEFAULT_SELECTED_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--lock-out", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()
    inventory_paths = tuple(args.inventories or DEFAULT_INVENTORIES)
    try:
        queue = load_event_queue(args.event_queue)
        inventory = merge_inventories(inventory_paths)
        selected_events, selected_records = build_selection(queue, inventory)
        inventory_sha = write_combined_inventory(queue, inventory, args.combined_inventory_out)
        event_sha = _write_csv(selected_events, args.selected_events_out, SELECTED_EVENT_COLUMNS)
        selection_sha = _write_csv(selected_records, args.output, OUTPUT_COLUMNS)
        queue_sha = _sha256_path(args.event_queue)
        audit = {
            "audit_type": "ESM_V0_8_1_EXPLICIT_CC_LICENSE_CLEAN_SELECTION",
            "canonical_source": ESM_SOURCE, "final_manifest": False, "frozen_salt": SALT,
            "generated_at_utc": _now_utc(), "source_queue_events": EXPECTED_QUEUE_EVENTS,
            "selected_events": EXPECTED_EVENTS, "records_per_event": RECORDS_PER_EVENT,
            "selected_records": EXPECTED_RECORDS,
            "explicit_cc_license_prefixes": list(EXPLICIT_CC_LICENSE_PREFIXES),
            "source_event_queue": str(args.event_queue), "source_event_queue_sha256": queue_sha,
            "source_inventories": [{"path": str(p), "sha256": _sha256_path(p)} for p in inventory_paths],
            "combined_inventory": str(args.combined_inventory_out), "combined_inventory_sha256": inventory_sha,
            "selected_event_preview": str(args.selected_events_out), "selected_event_preview_sha256": event_sha,
            "selected_records_csv": str(args.output), "selected_records_csv_sha256": selection_sha,
            "notes": [
                "All 63 queue events require complete zero-error exhaustive inventories.",
                "Only source-reported CC-BY3_0-IT and CC-BY4_0 per-waveform licenses are eligible.",
                "D and U licenses are excluded without reinterpretation.",
                "The first 34 eligible events in the pre-existing salted event order are selected.",
                "No partition assignment, final manifest, OSF registration, source tag, gate enablement, or confirmatory result is produced.",
            ],
        }
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_lock(args.lock_out, selection_path=args.output, selection_sha=selection_sha,
                   inventory_path=args.combined_inventory_out, inventory_sha=inventory_sha,
                   event_path=args.selected_events_out, event_sha=event_sha,
                   queue_path=args.event_queue, queue_sha=queue_sha)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(f"Frozen ESM queue events audited: {EXPECTED_QUEUE_EVENTS}")
    print(f"Selected explicit-CC events: {EXPECTED_EVENTS}")
    print(f"Selected records: {EXPECTED_RECORDS}")
    print(f"Selection SHA-256: {selection_sha}")
    print(f"Combined inventory SHA-256: {inventory_sha}")
    print(f"Selection lock: {args.lock_out}")
    print("No partition assignment, final manifest, OSF registration, source tag, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
