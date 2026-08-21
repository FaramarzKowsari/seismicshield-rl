#!/usr/bin/env python3
"""Build a deterministic ESM-only eligible-event queue from the component-audit ledger.

This is preregistration/data-selection infrastructure only. It does not amend the frozen design,
choose final records, create a final manifest, submit OSF registration, or run confirmatory work.
The queue is a deterministic preview that applies the already-frozen SHA-256 event-key formula to
ESM events that already passed authoritative Event-Data component audit.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.ground_motion_manifest import SALT, sha_key

ESM_SOURCE = "ESM"
ELIGIBLE_STATUS = "ELIGIBLE_EVENT_COMPONENT_AUDIT"
INCOMPLETE_STATUS = "ERROR_INCOMPLETE_COMPONENT_AUDIT"
DEFAULT_LEDGER = Path("results/local/esm/eventdata_component_event_audit.json")
DEFAULT_OUT_DIR = Path("results/local/esm")
DEFAULT_SELECT_COUNT = 40
QUEUE_COLUMNS = (
    "rank",
    "event_hash",
    "source",
    "event_id",
    "selected_preview",
    "passing_horizontal_count",
    "event_date_yyyymmdd",
    "event_time_hhmmss",
    "event_latitude_degree",
    "event_longitude_degree",
    "event_depth_km",
    "magnitude_w",
    "magnitude_l",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_ledger(path: Path) -> list[dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise ValueError("ESM component-audit ledger must be a JSON list of objects")
    return parsed


def build_queue(rows: list[dict[str, Any]], select_count: int = DEFAULT_SELECT_COUNT) -> list[dict[str, Any]]:
    if select_count <= 0:
        raise ValueError("select_count must be > 0")
    incomplete = [row for row in rows if row.get("status") == INCOMPLETE_STATUS]
    if incomplete:
        raise ValueError(f"ESM ledger still contains {len(incomplete)} incomplete/error events")

    seen: set[str] = set()
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != ELIGIBLE_STATUS:
            continue
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("eligible ESM event has blank event_id")
        if event_id in seen:
            raise ValueError(f"duplicate eligible ESM event_id {event_id!r}")
        seen.add(event_id)
        passing = int(row.get("passing_horizontal_count") or 0)
        if passing < 4:
            raise ValueError(f"eligible ESM event {event_id} has fewer than four passing horizontals")
        metadata = row.get("event_metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"eligible ESM event {event_id} has invalid event_metadata")
        event_hash = sha_key("event", {"source": ESM_SOURCE, "event_id": event_id})
        eligible.append(
            {
                "event_hash": event_hash,
                "source": ESM_SOURCE,
                "event_id": event_id,
                "passing_horizontal_count": passing,
                "event_date_yyyymmdd": metadata.get("event_date_yyyymmdd") or "",
                "event_time_hhmmss": metadata.get("event_time_hhmmss") or "",
                "event_latitude_degree": metadata.get("event_latitude_degree"),
                "event_longitude_degree": metadata.get("event_longitude_degree"),
                "event_depth_km": metadata.get("event_depth_km"),
                "magnitude_w": metadata.get("magnitude_w"),
                "magnitude_l": metadata.get("magnitude_l"),
            }
        )

    if len(eligible) < select_count:
        raise ValueError(
            f"only {len(eligible)} ESM events passed component audit; {select_count} are required"
        )
    eligible.sort(key=lambda row: (str(row["event_hash"]), str(row["event_id"])))
    for rank, row in enumerate(eligible, start=1):
        row["rank"] = rank
        row["selected_preview"] = rank <= select_count
    return eligible


def write_outputs(queue: list[dict[str, Any]], ledger_path: Path, out_dir: Path, select_count: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    queue_path = out_dir / "esm_eligible_event_queue.csv"
    selected_path = out_dir / "esm_selected_event_preview.csv"
    with queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(queue)
    with selected_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row in queue if row["selected_preview"])

    queue_bytes = queue_path.read_bytes()
    selected_bytes = selected_path.read_bytes()
    ledger_sha256 = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    audit = {
        "audit_type": "ESM_ELIGIBLE_EVENT_HASH_QUEUE_PREVIEW_ONLY",
        "final_manifest": False,
        "generated_at_utc": _now_utc(),
        "canonical_source_preview": ESM_SOURCE,
        "frozen_salt": SALT,
        "event_key_formula": "SHA-256(salt + ':event:' + source + ':' + event_id)",
        "eligible_events": len(queue),
        "selected_preview_events": select_count,
        "source_ledger": str(ledger_path),
        "source_ledger_sha256": ledger_sha256,
        "queue_csv_sha256": hashlib.sha256(queue_bytes).hexdigest(),
        "selected_preview_csv_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        "notes": [
            "This preview uses only ESM events already marked ELIGIBLE_EVENT_COMPONENT_AUDIT.",
            "No final per-event record selection is performed here.",
            "No AFAD/ESM mixing or cross-source deduplication is performed in this preview.",
            "The frozen design and OSF draft must be amended before this preview becomes the registered final source design.",
        ],
    }
    (out_dir / "esm_eligible_event_queue.audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--select-count", type=int, default=DEFAULT_SELECT_COUNT)
    args = parser.parse_args()
    if not args.ledger.exists():
        parser.error(f"ESM component-audit ledger not found: {args.ledger}")
    if args.select_count <= 0:
        parser.error("--select-count must be > 0")

    rows = load_ledger(args.ledger)
    queue = build_queue(rows, args.select_count)
    write_outputs(queue, args.ledger, args.out_dir, args.select_count)
    selected = [row for row in queue if row["selected_preview"]]
    print(f"ESM component-eligible events: {len(queue)}")
    print(f"Deterministic selected-event preview: {len(selected)}")
    print(f"First selected event: rank 1 EventID {selected[0]['event_id']} hash={selected[0]['event_hash']}")
    print(f"Last selected event: rank {len(selected)} EventID {selected[-1]['event_id']} hash={selected[-1]['event_hash']}")
    print(f"Wrote full queue: {args.out_dir / 'esm_eligible_event_queue.csv'}")
    print(f"Wrote selected preview: {args.out_dir / 'esm_selected_event_preview.csv'}")
    print("No final records, manifest, OSF registration, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
