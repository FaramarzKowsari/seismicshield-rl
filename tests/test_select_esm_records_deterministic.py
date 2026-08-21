from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.ground_motion_manifest import ESM_SOURCE, sha_key
from scripts.select_esm_records_deterministic import (
    EXPECTED_EVENTS,
    EXPECTED_RECORDS,
    build_selection,
    _event_order,
    _inventory_by_event,
)


def _record(event_id: str, index: int, *, hash_override: str | None = None) -> dict[str, str]:
    record_id = f"{event_id}.REC{index:03d}.ASC"
    expected_hash = sha_key(
        "record",
        {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id},
    )
    return {
        "source": ESM_SOURCE,
        "record_id": record_id,
        "record_hash_preview": hash_override or expected_hash,
        "file_name": record_id,
        "stream": "HNE" if index % 2 else "HNN",
        "network": "XX",
        "station_code": f"S{index:03d}",
        "location": "00",
        "source_member_sha256": "a" * 64,
        "source_zip_sha256": "b" * 64,
        "source_request_url": f"https://esm-db.eu/esmws/eventdata/1/query?eventid={event_id}",
    }


def _selected_events() -> list[tuple[int, str]]:
    return [(rank, f"EVENT-{rank:03d}") for rank in range(1, EXPECTED_EVENTS + 1)]


def _inventory(records_per_event: int = 6) -> dict[str, dict]:
    return {
        event_id: {
            "event_id": event_id,
            "status": "COMPLETE_RECORD_INVENTORY",
            "waveform_errors": 0,
            "passing_records_hash_order_preview": [
                _record(event_id, index) for index in range(1, records_per_event + 1)
            ],
        }
        for _, event_id in _selected_events()
    }


def test_build_selection_produces_exactly_four_per_event_and_160_total():
    events = _selected_events()
    inventory = _inventory(records_per_event=7)
    rows = build_selection(events, inventory)
    assert len(rows) == EXPECTED_RECORDS
    for rank, event_id in events:
        chosen = [row for row in rows if row["event_id"] == event_id]
        assert len(chosen) == 4
        expected = sorted(
            inventory[event_id]["passing_records_hash_order_preview"],
            key=lambda row: (row["record_hash_preview"], row["record_id"]),
        )[:4]
        assert [row["record_id"] for row in chosen] == [row["record_id"] for row in expected]
        assert [row["record_rank"] for row in chosen] == ["1", "2", "3", "4"]
        assert all(row["event_rank"] == str(rank) for row in chosen)


def test_build_selection_emits_canonical_basename_as_raw_filename():
    inventory = _inventory()
    for event in inventory.values():
        for record in event["passing_records_hash_order_preview"]:
            record["file_name"] = f"nested/path/{record['record_id']}"
    rows = build_selection(_selected_events(), inventory)
    assert all(row["raw_filename"] == row["record_id"] for row in rows)
    assert all("/" not in row["raw_filename"] and "\\" not in row["raw_filename"] for row in rows)


def test_direct_script_help_bootstraps_repository_root():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/select_esm_records_deterministic.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Select the frozen four ESM records" in result.stdout


def test_build_selection_fails_closed_on_incomplete_event():
    inventory = _inventory()
    inventory["EVENT-001"]["status"] = "ERROR_INCOMPLETE_RECORD_INVENTORY"
    with pytest.raises(ValueError, match="does not have a complete record inventory"):
        build_selection(_selected_events(), inventory)


def test_build_selection_fails_closed_on_nonzero_waveform_errors():
    inventory = _inventory()
    inventory["EVENT-001"]["waveform_errors"] = 1
    with pytest.raises(ValueError, match="nonzero waveform_errors"):
        build_selection(_selected_events(), inventory)


def test_build_selection_fails_closed_on_fewer_than_four_records():
    inventory = _inventory()
    inventory["EVENT-001"]["passing_records_hash_order_preview"] = [
        _record("EVENT-001", index) for index in range(1, 4)
    ]
    with pytest.raises(ValueError, match="fewer than four"):
        build_selection(_selected_events(), inventory)


def test_build_selection_recomputes_and_rejects_noncanonical_hash():
    inventory = _inventory()
    inventory["EVENT-001"]["passing_records_hash_order_preview"][0]["record_hash_preview"] = "0" * 64
    with pytest.raises(ValueError, match="noncanonical hash"):
        build_selection(_selected_events(), inventory)


def test_build_selection_rejects_duplicate_record_identity():
    inventory = _inventory()
    first = inventory["EVENT-001"]["passing_records_hash_order_preview"][0]
    inventory["EVENT-001"]["passing_records_hash_order_preview"][1] = dict(first)
    with pytest.raises(ValueError, match="duplicate record_id"):
        build_selection(_selected_events(), inventory)


def test_build_selection_rejects_non_esm_source():
    inventory = _inventory()
    inventory["EVENT-001"]["passing_records_hash_order_preview"][0]["source"] = "AFAD_TADAS"
    with pytest.raises(ValueError, match="non-ESM"):
        build_selection(_selected_events(), inventory)


def test_event_order_requires_exact_canonical_40_rank_sequence(tmp_path: Path):
    path = tmp_path / "selected.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "event_id"])
        writer.writeheader()
        for rank in range(1, EXPECTED_EVENTS + 1):
            writer.writerow({"rank": rank, "event_id": f"EVENT-{rank:03d}"})
    assert _event_order(path) == _selected_events()

    rows = list(csv.DictReader(path.open("r", encoding="utf-8", newline="")))
    rows[2]["rank"] = "99"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "event_id"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="rank sequence is not canonical"):
        _event_order(path)


def test_inventory_loader_rejects_duplicate_event_id(tmp_path: Path):
    path = tmp_path / "inventory.json"
    row = {
        "event_id": "EVENT-001",
        "status": "COMPLETE_RECORD_INVENTORY",
        "waveform_errors": 0,
        "passing_records_hash_order_preview": [],
    }
    path.write_text(json.dumps([row, row]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate event_id"):
        _inventory_by_event(path)
