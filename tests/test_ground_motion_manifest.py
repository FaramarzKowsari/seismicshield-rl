"""Software-only synthetic fixtures; no fixture is authoritative earthquake metadata."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.build_ground_motion_manifest import build
from scripts.ground_motion_manifest import (
    AFAD_TADAS_SOURCE,
    COLUMNS,
    PARTITIONS,
    STANDARD_GRAVITY_M_S2,
    afad_event_identity,
    afad_record_id,
    derive_usable_duration_s,
    eligibility_errors,
    is_valid_utc_timestamp,
    raw_redistribution_allowed,
    sha_key,
    validate_component_pga,
    write_manifest,
)
from scripts.validate_ground_motion_manifest import validate


def synthetic_rows(events: int = 40, records: int = 4) -> list[dict[str, str]]:
    rows = []
    for event in range(events):
        for record in range(records):
            token = f"synthetic-fixture-{event:02d}-{record}"
            rows.append({
                "source": "synthetic-fixture-software-validation-only",
                "event_id": f"synthetic-fixture-event-{event:02d}",
                "raw_header_event_id": "",
                "record_id": token,
                "waveform_detail_id": "",
                "stream": "",
                "raw_filename": f"{token}.txt",
                "station_id": f"synthetic-fixture-station-{record}",
                "component": "horizontal acceleration",
                "sampling_interval_s": "0.02",
                "usable_duration_s": "10",
                "original_units": "g",
                "normalized_units": "m/s^2",
                "ndata": "501",
                "raw_duration_derivation": "explicit",
                "pga_cm_s2": "147.09975",
                "pga_g": "0.15",
                "event_date": "2000-01-01",
                "event_time_utc": "2000-01-01T00:00:00Z",
                "latitude": "0",
                "longitude": "0",
                "partition": "",
                "source_url_or_access_reference": "synthetic-fixture-access-reference",
                "preprocessing_status": "synthetic-fixture-test-only",
                "raw_sha256": f"{event * records + record + 1:064x}",
                "processed_sha256": f"{event * records + record + 1001:064x}",
                "data_license": "synthetic-fixture-license",
                "raw_redistribution_allowed": "false",
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


def test_afad_tadas_identity_and_stream_contracts():
    assert AFAD_TADAS_SOURCE == "AFAD_TADAS"
    assert afad_event_identity("543428", 0) == ("543428", "0")
    assert afad_record_id("327925", "HNE") == "327925:HNE"
    assert afad_record_id("327925", "hnn") == "327925:HNN"
    with pytest.raises(ValueError, match="not an eligible horizontal"):
        afad_record_id("327925", "HNZ")
    a = {"source": AFAD_TADAS_SOURCE, "event_id": "543428", "record_id": "327925:HNE"}
    b = dict(a)
    assert sha_key("record", a) == sha_key("record", b)


def test_afad_duration_derivation_fails_closed():
    assert derive_usable_duration_s("105", 10501, 0.01, 10501) == (
        105.0, "explicit:DURATION_S",
    )
    assert derive_usable_duration_s("", 10501, 0.01, 10501) == (
        105.0, "(NDATA - 1) * SAMPLING_INTERVAL_S",
    )
    with pytest.raises(ValueError, match="sample-count"):
        derive_usable_duration_s(None, 10501, 0.01, 10500)
    for bad_dt in (0, -0.01, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="sampling interval"):
            derive_usable_duration_s(None, 2, bad_dt, 2)


def test_afad_pga_and_license_contracts():
    assert STANDARD_GRAVITY_M_S2 * 100 * 0.15 == 147.09975
    assert validate_component_pga([-147.09975, 12], 147.10975) == pytest.approx(147.10975 / 980.665)
    with pytest.raises(ValueError, match="disagrees"):
        validate_component_pga([-147.09975, 12], 147.109751)
    license_text = "U (unknown license)"
    assert license_text == "U (unknown license)"
    assert raw_redistribution_allowed(license_text) is False


@pytest.mark.parametrize(
    "license_text",
    ["", "arbitrary license", "all rights reserved", "restricted", None],
)
def test_afad_raw_redistribution_has_no_permissive_default(license_text):
    assert raw_redistribution_allowed(license_text) is False


def valid_afad_row() -> dict[str, str]:
    return {
        "source": "AFAD_TADAS",
        "event_id": "543428",
        "raw_header_event_id": "0",
        "record_id": "327925:HNE",
        "waveform_detail_id": "327925",
        "stream": "HNE",
        "raw_filename": "327925_HNE.txt",
        "station_id": "1201",
        "component": "horizontal acceleration",
        "sampling_interval_s": "0.01",
        "usable_duration_s": "105.0",
        "original_units": "cm/s^2",
        "normalized_units": "m/s^2",
        "ndata": "10501",
        "raw_duration_derivation": "(NDATA - 1) * SAMPLING_INTERVAL_S",
        "pga_cm_s2": "147.09975",
        "pga_g": "0.15",
        "event_date": "2023-02-06",
        "event_time_utc": "2023-02-06T01:17:34Z",
        "latitude": "37.17",
        "longitude": "37.03",
        "source_url_or_access_reference": "https://tadas.afad.gov.tr/event-detail/543428",
        "preprocessing_status": "raw-validated",
        "raw_sha256": "a" * 64,
        "processed_sha256": "b" * 64,
        "data_license": "U (unknown license)",
        "raw_redistribution_allowed": "false",
    }


def test_unknown_afad_license_is_preserved_without_placeholder_rejection():
    row = valid_afad_row()
    assert row["data_license"] == "U (unknown license)"
    assert eligibility_errors(row) == []


@pytest.mark.parametrize(
    ("timestamp", "valid"),
    [
        ("2023-02-06T01:17:34Z", True),
        ("2023-02-06T01:17:34+00:00", True),
        ("2023-02-06T01:17:34.123Z", True),
        ("bananaZ", False),
        ("2023-99-99T99:99:99Z", False),
        ("2023-02-06T04:17:34+03:00", False),
        ("2023-02-06 01:17:34Z", False),
        ("", False),
    ],
)
def test_strict_utc_timestamp_validation(timestamp, valid):
    assert is_valid_utc_timestamp(timestamp) is valid
    row = dict(valid_afad_row(), event_time_utc=timestamp)
    utc_errors = [error for error in eligibility_errors(row) if "event_time_utc" in error]
    assert bool(utc_errors) is not valid


def test_afad_redistribution_flag_must_fail_closed():
    errors = eligibility_errors(dict(valid_afad_row(), raw_redistribution_allowed="true"))
    assert "AFAD/TADAS raw redistribution is not explicitly licensed" in errors


def test_blank_afad_license_fails_eligibility():
    assert "blank data_license" in eligibility_errors(dict(valid_afad_row(), data_license=""))


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
