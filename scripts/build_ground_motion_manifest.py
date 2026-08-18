"""Build the frozen manifest from supplied REAL source metadata; never fetch or invent data."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import (  # noqa: E402
    COLUMNS,
    PARTITIONS,
    eligibility_errors,
    read_csv,
    sha_key,
    write_manifest,
)


def build(rows: list[dict[str, str]], *, allow_test_fixtures: bool = False) -> list[dict[str, str]]:
    eligible: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    seen_records: set[tuple[str, str, str]] = set()
    for row in rows:
        errors = eligibility_errors(row, allow_test_fixtures=allow_test_fixtures)
        if errors:
            continue
        identity = (row["source"], row["event_id"], row["record_id"])
        if identity in seen_records:
            raise ValueError(f"Duplicate record identity: {identity}")
        seen_records.add(identity)
        eligible[identity[:2]].append(row)

    qualified = [(key, values) for key, values in eligible.items() if len(values) >= 4]
    qualified.sort(key=lambda item: sha_key("event", item[1][0]))
    if len(qualified) < 40:
        raise ValueError(f"Need 40 events with >=4 eligible records; found {len(qualified)}")

    output: list[dict[str, str]] = []
    partition_names = [name for name, count in PARTITIONS for _ in range(count)]
    for partition, (_, candidates) in zip(partition_names, qualified[:40], strict=True):
        candidates.sort(key=lambda row: sha_key("record", row))
        if len(candidates) < 4:  # Defensive fail-closed check; no substitution occurs.
            raise ValueError(f"Selected event {candidates[0]['event_id']} has fewer than four records")
        for candidate in candidates[:4]:
            row = {column: candidate.get(column, "") for column in COLUMNS}
            row.update(partition=partition, eligibility_status="eligible", eligibility_reason="")
            output.append(row)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV containing real source metadata")
    parser.add_argument("output", type=Path, help="output manifest CSV")
    args = parser.parse_args()
    try:
        digest = write_manifest(build(read_csv(args.input)), args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote frozen manifest: {args.output}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
