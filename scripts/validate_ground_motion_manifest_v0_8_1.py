#!/usr/bin/env python3
"""Validate the post-registration v0.8.1 34-event / 136-record ground-motion manifest."""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import ESM_SOURCE, eligibility_errors, read_csv, sha_key  # noqa: E402
from scripts.build_ground_motion_manifest_v0_8_1 import (  # noqa: E402
    EXPECTED_EVENTS,
    EXPECTED_RECORDS,
    EXPLICIT_CC_PREFIXES,
    PARTITIONS_V0_8_1,
    RECORDS_PER_EVENT,
    partition_for_event_rank,
)


def _explicit_cc(value: str) -> bool:
    text = str(value or "").strip().upper()
    return any(text.startswith(prefix) for prefix in EXPLICIT_CC_PREFIXES)


def validate(path: Path, digest_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    try:
        rows = read_csv(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    if len(rows) != EXPECTED_RECORDS:
        errors.append(f"expected {EXPECTED_RECORDS} rows, found {len(rows)}")

    by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    record_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        source = row.get("source", "").strip()
        if source != ESM_SOURCE:
            errors.append(f"row {index}: final manifest source must be ESM, found {source!r}")
        record_id = row.get("record_id", "")
        if record_id in record_ids:
            errors.append(f"duplicate record_id {record_id!r}")
        record_ids.add(record_id)
        row_errors = eligibility_errors(row)
        if row.get("eligibility_status") != "eligible" or row.get("eligibility_reason"):
            row_errors.append("manifest row is not unconditionally eligible")
        if not _explicit_cc(row.get("data_license", "")):
            row_errors.append("manifest row lacks explicit frozen CC license")
        errors.extend(f"row {index}: {message}" for message in row_errors)
        by_event[row.get("event_id", "")].append(row)

    if len(by_event) != EXPECTED_EVENTS:
        errors.append(f"expected {EXPECTED_EVENTS} unique event IDs, found {len(by_event)}")

    for event_id, group in by_event.items():
        if len(group) != RECORDS_PER_EVENT:
            errors.append(f"event {event_id!r} has {len(group)} records, expected {RECORDS_PER_EVENT}")
        partitions = {row.get("partition", "") for row in group}
        if len(partitions) != 1:
            errors.append(f"event leakage for {event_id!r}: {sorted(partitions)}")

    event_counts = Counter(group[0].get("partition", "") for group in by_event.values() if group)
    record_counts = Counter(row.get("partition", "") for row in rows)
    expected_partition_names = {name for name, _ in PARTITIONS_V0_8_1}
    for name, expected_events in PARTITIONS_V0_8_1:
        if event_counts[name] != expected_events:
            errors.append(f"{name}: expected {expected_events} events, found {event_counts[name]}")
        if record_counts[name] != expected_events * RECORDS_PER_EVENT:
            errors.append(
                f"{name}: expected {expected_events * RECORDS_PER_EVENT} records, found {record_counts[name]}"
            )
    unexpected = (set(event_counts) | set(record_counts)) - expected_partition_names
    if unexpected:
        errors.append(f"unexpected partitions: {sorted(unexpected)}")

    ordered_events = sorted(by_event.values(), key=lambda group: sha_key("event", group[0]))
    expected_rows: list[dict[str, str]] = []
    for event_rank, group in enumerate(ordered_events, start=1):
        expected_partition = partition_for_event_rank(event_rank)
        ordered_records = sorted(group, key=lambda row: (sha_key("record", row), row.get("record_id", "")))
        if any(row.get("partition", "") != expected_partition for row in ordered_records):
            errors.append(
                f"event rank {event_rank}: partition differs from OSF deterministic positional rule"
            )
        expected_rows.extend(ordered_records)

    if len(rows) == EXPECTED_RECORDS:
        if [row.get("record_id", "") for row in rows] != [row.get("record_id", "") for row in expected_rows]:
            errors.append("row ordering differs from frozen salted event/record ordering")

    sidecar = digest_path or path.with_suffix(path.suffix + ".sha256")
    try:
        expected_digest = sidecar.read_text(encoding="utf-8").split()[0].lower()
    except (OSError, IndexError):
        errors.append(f"missing or unreadable SHA-256 sidecar: {sidecar}")
    else:
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_digest != actual_digest:
            errors.append("manifest SHA-256 does not match sidecar")

    pilot_ids = {event for event, group in by_event.items() if group and group[0].get("partition") == "pilot"}
    confirmatory_ids = {
        event for event, group in by_event.items() if group and group[0].get("partition") == "confirmatory"
    }
    if pilot_ids & confirmatory_ids:
        errors.append("pilot exclusion contract violated")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--digest", type=Path)
    args = parser.parse_args()
    errors = validate(args.manifest, args.digest)
    if errors:
        print("Ground-motion manifest v0.8.1: INVALID")
        for error in errors:
            print(f"- {error}")
        return 2
    print("Ground-motion manifest v0.8.1: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
