#!/usr/bin/env python3
"""Materialize the frozen v0.8.1 34x4 explicit-CC ESM selection into private SI records.

This wrapper reuses the v0.8.0 byte-level materialization logic but changes only the frozen
selection/inventory/lock contract to the v0.8.1 license-clean 34-event, 136-record design.
It does not assign partitions, create the final confirmatory manifest, submit OSF, create a source
tag, enable the confirmatory gate, or inspect confirmatory results.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.materialize_esm_selected_records import (  # noqa: E402
    _load_inventory,
    _verify_locked_inputs,
    _write_staging,
    materialize_one,
)

DEFAULT_SELECTION = Path("results/local/esm/esm_selected_records_136.csv")
DEFAULT_INVENTORY = Path("results/local/esm/esm_record_inventory_63_complete.json")
DEFAULT_SELECTION_LOCK = Path("open_science/ground_motion_selection_lock_v0.8.1.yaml")
DEFAULT_PROCESSED_DIR = Path("data/private/esm/processed-selected-v0.8.1")
DEFAULT_STAGING = Path("results/local/esm/esm_selected_records_136_manifest_staging.csv")
DEFAULT_AUDIT = Path("results/local/esm/esm_selected_records_136_materialization.audit.json")
EXPECTED_EVENTS = 34
EXPECTED_RECORDS = 136
EXPECTED_PER_EVENT = 4
EXPLICIT_CC_PREFIXES = ("CC-BY3_0-IT", "CC-BY4_0")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _explicit_cc(value: str) -> bool:
    text = str(value or "").strip().upper()
    return any(text.startswith(prefix) for prefix in EXPLICIT_CC_PREFIXES)


def load_selection(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"v0.8.1 selection must contain exactly {EXPECTED_RECORDS} rows")
    event_counts: dict[str, int] = {}
    identities: set[tuple[str, str]] = set()
    for row in rows:
        event_id = row.get("event_id", "")
        record_id = row.get("record_id", "")
        if not event_id or not record_id:
            raise ValueError("v0.8.1 selection contains blank event_id/record_id")
        identity = (event_id, record_id)
        if identity in identities:
            raise ValueError(f"duplicate selected identity: {identity}")
        identities.add(identity)
        event_counts[event_id] = event_counts.get(event_id, 0) + 1
        if not _explicit_cc(row.get("data_license", "")):
            raise ValueError(f"selected record {event_id}/{record_id} lacks an explicit frozen CC license")
    if len(event_counts) != EXPECTED_EVENTS:
        raise ValueError(f"v0.8.1 selection must contain exactly {EXPECTED_EVENTS} events")
    if any(count != EXPECTED_PER_EVENT for count in event_counts.values()):
        raise ValueError("v0.8.1 selection must contain exactly four records per event")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--selection-lock", type=Path, default=DEFAULT_SELECTION_LOCK)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--staging-out", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    try:
        selection_sha, inventory_sha = _verify_locked_inputs(
            args.selection_lock, args.selection, args.inventory
        )
        selections = load_selection(args.selection)
        inventory = _load_inventory(args.inventory)
        missing = sorted({row["event_id"] for row in selections} - set(inventory))
        if missing:
            raise ValueError(f"combined inventory is missing selected events: {missing[:5]}")

        rows: list[dict[str, str]] = []
        for selection in selections:
            row = materialize_one(selection, inventory[selection["event_id"]], args.processed_dir)
            if row["data_license"] != selection["data_license"]:
                raise ValueError(
                    f"source DATA_LICENSE changed after selection for {selection['event_id']} / {selection['record_id']}"
                )
            if not _explicit_cc(row["data_license"]):
                raise ValueError("materialized source no longer carries an accepted explicit CC license")
            rows.append(row)

        staging_sha = _write_staging(rows, args.staging_out)
        digest_lines = [
            f"{row['event_id']}\0{row['record_id']}\0{row['processed_sha256']}\n" for row in rows
        ]
        processed_set_sha = hashlib.sha256("".join(digest_lines).encode("utf-8")).hexdigest()
        audit = {
            "audit_type": "ESM_V0_8_1_EXPLICIT_CC_136_PRIVATE_SI_MATERIALIZATION",
            "final_manifest": False,
            "partition_assignment_performed": False,
            "selected_events": EXPECTED_EVENTS,
            "selected_records": EXPECTED_RECORDS,
            "records_per_event": EXPECTED_PER_EVENT,
            "accepted_license_prefixes": list(EXPLICIT_CC_PREFIXES),
            "selection_lock": str(args.selection_lock),
            "selection_csv": str(args.selection),
            "selection_csv_sha256": selection_sha,
            "source_inventory": str(args.inventory),
            "source_inventory_sha256": inventory_sha,
            "staging_csv": str(args.staging_out),
            "staging_csv_sha256": staging_sha,
            "processed_record_set_sha256": processed_set_sha,
            "processed_private_dir": args.processed_dir.as_posix(),
            "notes": [
                "Source license text is re-read from each ESM ASCII member and must exactly match the frozen selection.",
                "Only frozen explicit-CC records are materialized; D and U license states remain excluded.",
                "No final manifest, partition assignment, OSF registration, source tag, gate enablement, or confirmatory result is produced.",
            ],
        }
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))

    print(f"Materialized v0.8.1 ESM records: {len(rows)}")
    print(f"Private normalized record directory: {args.processed_dir}")
    print(f"Staging metadata: {args.staging_out}")
    print(f"Staging SHA-256: {staging_sha}")
    print(f"Processed record-set SHA-256: {processed_set_sha}")
    print(f"Audit: {args.audit_out}")
    print("No final manifest, partition assignment, OSF registration, source tag, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
