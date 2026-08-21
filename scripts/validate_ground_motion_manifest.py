"""Validate every frozen ground-motion manifest contract and fail closed."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import (  # noqa: E402
    ESM_SOURCE,
    PARTITIONS,
    eligibility_errors,
    read_csv,
    sha_key,
)


def _fixture_source_allowed(source: str, allow_test_fixtures: bool) -> bool:
    return allow_test_fixtures and source.startswith("synthetic-fixture")


def validate(
    path: Path,
    digest_path: Path | None = None,
    *,
    allow_test_fixtures: bool = False,
    expected_source: str = ESM_SOURCE,
) -> list[str]:
    errors: list[str] = []
    try:
        rows = read_csv(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    if len(rows) != 160:
        errors.append(f"expected 160 rows, found {len(rows)}")

    by_event: dict[str, list[dict[str, str]]] = defaultdict(list)
    record_ids: set[str] = set()
    for index, row in enumerate(rows, 2):
        source = row.get("source", "").strip()
        if expected_source and source != expected_source and not _fixture_source_allowed(source, allow_test_fixtures):
            errors.append(f"row {index}: final manifest source must be {expected_source}, found {source!r}")
        if row["record_id"] in record_ids:
            errors.append(f"duplicate record_id {row['record_id']!r}")
        record_ids.add(row["record_id"])
        row_errors = eligibility_errors(row, allow_test_fixtures=allow_test_fixtures)
        if row.get("eligibility_status") != "eligible" or row.get("eligibility_reason"):
            row_errors.append("manifest row is not unconditionally eligible")
        errors.extend(f"row {index}: {message}" for message in row_errors)
        by_event[row["event_id"]].append(row)

    production_sources = {
        row.get("source", "").strip()
        for row in rows
        if not _fixture_source_allowed(row.get("source", "").strip(), allow_test_fixtures)
    }
    if expected_source and production_sources and production_sources != {expected_source}:
        errors.append(
            f"final manifest must be single-source {expected_source}; observed sources: {sorted(production_sources)}"
        )

    if len(by_event) != 40:
        errors.append(f"expected 40 unique event IDs, found {len(by_event)}")
    for event_id, event_rows in by_event.items():
        if len(event_rows) != 4:
            errors.append(f"event {event_id!r} has {len(event_rows)} records, expected 4")
        partitions = {row["partition"] for row in event_rows}
        if len(partitions) != 1:
            errors.append(f"event leakage for {event_id!r}: {sorted(partitions)}")
        if len({row["source"] for row in event_rows}) != 1:
            errors.append(f"event ID {event_id!r} has inconsistent sources")

    record_counts = Counter(row["partition"] for row in rows)
    event_counts = Counter(event_rows[0]["partition"] for event_rows in by_event.values() if event_rows)
    for name, expected_events in PARTITIONS:
        if event_counts[name] != expected_events:
            errors.append(f"{name}: expected {expected_events} events, found {event_counts[name]}")
        if record_counts[name] != expected_events * 4:
            errors.append(f"{name}: expected {expected_events * 4} records, found {record_counts[name]}")
    unexpected = (set(record_counts) | set(event_counts)) - {name for name, _ in PARTITIONS}
    if unexpected:
        errors.append(f"unexpected partitions: {sorted(unexpected)}")

    expected_events = sorted(by_event.values(), key=lambda group: sha_key("event", group[0]))
    expected_rows: list[dict[str, str]] = []
    partition_names = [name for name, count in PARTITIONS for _ in range(count)]
    for partition, group in zip(partition_names, expected_events):
        ordered = sorted(group, key=lambda row: sha_key("record", row))
        if any(row["partition"] != partition for row in ordered):
            errors.append("event partition/order differs from frozen SHA-256 allocation")
        expected_rows.extend(ordered)
    if len(rows) == 160 and [row["record_id"] for row in rows] != [row["record_id"] for row in expected_rows]:
        errors.append("row ordering differs from frozen event/record SHA-256 ordering")

    sidecar = digest_path or path.with_suffix(path.suffix + ".sha256")
    try:
        expected_digest = sidecar.read_text(encoding="utf-8").split()[0].lower()
    except (OSError, IndexError):
        errors.append(f"missing or unreadable SHA-256 sidecar: {sidecar}")
    else:
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_digest != actual_digest:
            errors.append("manifest SHA-256 does not match sidecar")

    # This explicit contract prevents the feasibility-exposed pilot stratum from
    # ever being reclassified as confirmatory within the frozen manifest.
    pilot_ids = {event for event, group in by_event.items() if group[0]["partition"] == "pilot"}
    confirmatory_ids = {event for event, group in by_event.items() if group[0]["partition"] == "confirmatory"}
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
        print("Ground-motion manifest: INVALID")
        for error in errors:
            print(f"- {error}")
        return 2
    print("Ground-motion manifest: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
