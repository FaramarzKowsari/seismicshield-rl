"""Software-only synthetic fixtures; no fixture is authoritative earthquake metadata."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.build_ground_motion_manifest import build
from scripts.ground_motion_manifest import COLUMNS, PARTITIONS, eligibility_errors, sha_key, write_manifest
from scripts.validate_ground_motion_manifest import validate


def synthetic_rows(events: int = 40, records: int = 4) -> list[dict[str, str]]:
    rows = []
    for event in range(events):
        for record in range(records):
            token = f"synthetic-fixture-{event:02d}-{record}"
            rows.append({
                "source": "synthetic-fixture-software-validation-only",
                "event_id": f"synthetic-fixture-event-{event:02d}",
                "record_id": token,
                "station_id": f"synthetic-fixture-station-{record}",
                "component": "horizontal acceleration",
                "sampling_interval_s": "0.02",
                "usable_duration_s": "10",
                "original_units": "g",
                "normalized_units": "m/s^2",
                "pga_g": "0.15",
                "event_date": "2000-01-01",
                "latitude": "0",
                "longitude": "0",
                "partition": "",
                "source_url_or_access_reference": "synthetic-fixture-access-reference",
                "preprocessing_status": "synthetic-fixture-test-only",
                "raw_sha256": f"{event * records + record + 1:064x}",
                "processed_sha256": f"{event * records + record + 1001:064x}",
                "eligibility_status": "",
                "eligibility_reason": "",
            })
    return rows


def test_schema_header_is_exact():
    schema = Path("data/manifests/ground_motion_manifest_schema.csv")
    with schema.open(newline="", encoding="utf-8") as handle:
        assert tuple(next(csv.reader(handle))) == COLUMNS
        assert list(csv.reader(handle)) == []


def test_hashing_is_deterministic_and_scoped():
    row = synthetic_rows(1, 1)[0]
    assert sha_key("event", row) == sha_key("event", dict(row))
    assert sha_key("event", row) != sha_key("record", row)


def test_event_level_split_and_partition_counts():
    manifest = build(synthetic_rows(), allow_test_fixtures=True)
    assert len(manifest) == 160
    for event_id in {row["event_id"] for row in manifest}:
        assert len({row["partition"] for row in manifest if row["event_id"] == event_id}) == 1
    assert {name: sum(row["partition"] == name for row in manifest) for name, _ in PARTITIONS} == {
        "training": 72, "validation": 24, "pilot": 16, "confirmatory": 48,
    }


def test_insufficient_events_rejected():
    with pytest.raises(ValueError, match="Need 40 events"):
        build(synthetic_rows(39), allow_test_fixtures=True)


def test_insufficient_records_rejected():
    with pytest.raises(ValueError, match="Need 40 events"):
        build(synthetic_rows(40, 3), allow_test_fixtures=True)


def test_blank_and_fake_provenance_rejected():
    row = synthetic_rows(1, 1)[0]
    assert any("non-real/placeholder" in error for error in eligibility_errors(row))
    row = dict(row, source="")
    assert "blank source" in eligibility_errors(row)


def test_validator_accepts_test_fixture_and_rejects_leakage(tmp_path: Path):
    path = tmp_path / "synthetic-software-validation-only.csv"
    rows = build(synthetic_rows(), allow_test_fixtures=True)
    write_manifest(rows, path)
    assert validate(path, allow_test_fixtures=True) == []
    rows[0]["partition"] = "confirmatory"
    write_manifest(rows, path)
    errors = validate(path, allow_test_fixtures=True)
    assert any("event leakage" in error for error in errors)

