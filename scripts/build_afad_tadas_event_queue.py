#!/usr/bin/env python3
"""Build a deterministic, local AFAD/TADAS event-candidate queue."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

if __package__:
    from scripts.ground_motion_manifest import AFAD_TADAS_SOURCE, SALT, sha_key
else:
    from ground_motion_manifest import AFAD_TADAS_SOURCE, SALT, sha_key

DEFAULT_OUT_DIR = Path("results/local/afad_tadas")
QUEUE_COLUMNS = (
    "rank", "event_hash", "source", "event_id", "event_date_from_export",
    "epicenter_agency", "longitude", "latitude", "magnitude_type", "magnitude",
    "depth", "location",
)
FIELD_ALIASES = {
    "event_id": ("eventid", "event_id"),
    "event_date_from_export": ("eventdate", "event_date", "date"),
    "epicenter_agency": ("epicenteragency", "epicenter_agency", "agency"),
    "longitude": ("longitude", "lon"), "latitude": ("latitude", "lat"),
    "magnitude_type": ("magnitudetype", "magnitude_type"),
    "magnitude": ("magnitude", "mag"), "depth": ("depth",),
    "location": ("location",),
}


def _header_key(value: str) -> str:
    return "".join(char.lower() for char in value.strip() if char.isalnum() or char == "_")


def _get(row: dict[str, str], field: str) -> str:
    normalized = {_header_key(key): (value or "").strip() for key, value in row.items()}
    return next((normalized[key] for key in FIELD_ALIASES[field] if key in normalized), "")


def build_event_queue(source_csv: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Read an Event Search export, rejecting duplicate nonblank candidate rows."""
    raw_bytes = source_csv.read_bytes()
    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not any(
            _header_key(name) in FIELD_ALIASES["event_id"] for name in reader.fieldnames
        ):
            raise ValueError("Event Search CSV is missing EventID")
        input_rows = list(reader)

    candidates: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    blank_count = 0
    for input_row in input_rows:
        event_id = _get(input_row, "event_id")
        if not event_id:
            blank_count += 1
            continue
        values = tuple(_get(input_row, field) for field in FIELD_ALIASES)
        if values in seen:
            raise ValueError(f"duplicate input row for EventID {event_id!r}")
        seen.add(values)
        row: dict[str, object] = {
            "source": AFAD_TADAS_SOURCE,
            **{field: value for field, value in zip(FIELD_ALIASES, values)},
        }
        row["event_hash"] = sha_key("event", row)  # type: ignore[arg-type]
        candidates.append(row)

    candidates.sort(key=lambda row: str(row["event_hash"]))
    for rank, row in enumerate(candidates, 1):
        row["rank"] = rank
    audit: dict[str, object] = {
        "source_csv_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "total_rows": len(input_rows),
        "rows_with_known_event_id": len(candidates),
        "rows_with_blank_event_id": blank_count,
        "canonical_source": AFAD_TADAS_SOURCE,
        "frozen_salt": SALT,
        "generation_timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return candidates, audit


def write_outputs(rows: Iterable[dict[str, object]], audit: dict[str, object], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "event_candidate_queue.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "event_candidate_queue.audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="local TADAS Event Search CSV export")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    rows, audit = build_event_queue(args.csv)
    write_outputs(rows, audit, args.out_dir)
    print(f"Wrote {len(rows)} candidates; ignored {audit['rows_with_blank_event_id']} blank-ID rows")


if __name__ == "__main__":
    main()
