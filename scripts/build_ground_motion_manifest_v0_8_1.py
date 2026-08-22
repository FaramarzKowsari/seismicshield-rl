#!/usr/bin/env python3
"""Build the public v0.8.1 ground-motion manifest from frozen 136-record staging metadata.

This post-registration step applies only the deterministic partition rule published in OSF 64dtx:
selected event ranks 1-13 -> training, 14-18 -> validation, 19-22 -> pilot, and 23-34 ->
confirmatory. All four records of an event inherit the event partition. No source event or record is
reselected here, and no confirmatory simulator outcome is inspected.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import COLUMNS, ESM_SOURCE, eligibility_errors, sha_key, write_manifest  # noqa: E402

EXPECTED_EVENTS = 34
EXPECTED_RECORDS = 136
RECORDS_PER_EVENT = 4
PARTITIONS_V0_8_1 = (("training", 13), ("validation", 5), ("pilot", 4), ("confirmatory", 12))
EXPLICIT_CC_PREFIXES = ("CC-BY3_0-IT", "CC-BY4_0")
DEFAULT_INPUT = Path("results/local/esm/esm_selected_records_136_manifest_staging.csv")
DEFAULT_OUTPUT = Path("data/manifests/ground_motion_manifest.csv")


def partition_for_event_rank(rank: int) -> str:
    if 1 <= rank <= 13:
        return "training"
    if 14 <= rank <= 18:
        return "validation"
    if 19 <= rank <= 22:
        return "pilot"
    if 23 <= rank <= 34:
        return "confirmatory"
    raise ValueError(f"event_rank out of frozen v0.8.1 range: {rank}")


def _explicit_cc(value: str) -> bool:
    text = str(value or "").strip().upper()
    return any(text.startswith(prefix) for prefix in EXPLICIT_CC_PREFIXES)


def read_staging(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = set(COLUMNS) | {"event_rank", "record_rank", "record_hash"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"staging CSV missing required columns: {', '.join(sorted(missing))}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def build(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"v0.8.1 staging must contain exactly {EXPECTED_RECORDS} rows; found {len(rows)}")

    by_rank: dict[int, list[dict[str, str]]] = defaultdict(list)
    identities: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("source") != ESM_SOURCE:
            raise ValueError("v0.8.1 staging contains a non-ESM source")
        try:
            event_rank = int(row.get("event_rank", ""))
            record_rank = int(row.get("record_rank", ""))
        except ValueError as exc:
            raise ValueError("staging contains invalid event_rank/record_rank") from exc
        if not 1 <= record_rank <= RECORDS_PER_EVENT:
            raise ValueError(f"invalid record_rank {record_rank} for event rank {event_rank}")
        identity = (row.get("event_id", ""), row.get("record_id", ""))
        if not all(identity):
            raise ValueError("staging contains blank event_id/record_id")
        if identity in identities:
            raise ValueError(f"duplicate selected event/record identity: {identity}")
        identities.add(identity)
        if not _explicit_cc(row.get("data_license", "")):
            raise ValueError(f"selected row lacks explicit frozen CC license: {identity}")
        errors = eligibility_errors(row)
        if errors:
            raise ValueError(f"staging row {identity} fails frozen eligibility: {'; '.join(errors)}")
        expected_record_hash = sha_key("record", row)
        if row.get("record_hash") != expected_record_hash:
            raise ValueError(f"noncanonical record hash for {identity}")
        by_rank[event_rank].append(row)

    if set(by_rank) != set(range(1, EXPECTED_EVENTS + 1)):
        raise ValueError("staging event_rank set is not exactly 1..34")

    output: list[dict[str, str]] = []
    event_ids: set[str] = set()
    previous_event_hash = ""
    for event_rank in range(1, EXPECTED_EVENTS + 1):
        group = by_rank[event_rank]
        if len(group) != RECORDS_PER_EVENT:
            raise ValueError(f"event rank {event_rank} has {len(group)} records; expected 4")
        ids = {row["event_id"] for row in group}
        if len(ids) != 1:
            raise ValueError(f"event rank {event_rank} contains multiple event IDs")
        event_id = next(iter(ids))
        if event_id in event_ids:
            raise ValueError(f"event ID appears under multiple event ranks: {event_id}")
        event_ids.add(event_id)
        event_hash = sha_key("event", group[0])
        if previous_event_hash and event_hash <= previous_event_hash:
            raise ValueError("selected event ranks are not in ascending frozen salted event-hash order")
        previous_event_hash = event_hash

        ordered = sorted(group, key=lambda row: (int(row["record_rank"]), row["record_id"]))
        if [int(row["record_rank"]) for row in ordered] != [1, 2, 3, 4]:
            raise ValueError(f"event rank {event_rank} does not contain record ranks 1..4")
        expected_by_hash = sorted(group, key=lambda row: (sha_key("record", row), row["record_id"]))
        if [row["record_id"] for row in ordered] != [row["record_id"] for row in expected_by_hash]:
            raise ValueError(f"event rank {event_rank} record ranks differ from frozen salted record-hash order")

        partition = partition_for_event_rank(event_rank)
        for source_row in ordered:
            row = {column: source_row.get(column, "") for column in COLUMNS}
            row.update(partition=partition, eligibility_status="eligible", eligibility_reason="")
            output.append(row)

    event_counts = Counter()
    record_counts = Counter(row["partition"] for row in output)
    seen_event_partition: dict[str, str] = {}
    for row in output:
        seen_event_partition.setdefault(row["event_id"], row["partition"])
    event_counts.update(seen_event_partition.values())
    for name, expected in PARTITIONS_V0_8_1:
        if event_counts[name] != expected or record_counts[name] != expected * RECORDS_PER_EVENT:
            raise ValueError(f"partition count mismatch for {name}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        manifest = build(read_staging(args.input))
        digest = write_manifest(manifest, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote v0.8.1 frozen manifest: {args.output}")
    print(f"Rows: {len(manifest)}")
    print("Partitions: training=52 validation=20 pilot=16 confirmatory=48")
    print(f"SHA-256: {digest}")
    print("No confirmatory simulator result was produced or inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
