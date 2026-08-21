from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_ground_motion_manifest import build
from scripts.ground_motion_manifest import ESM_SOURCE, STANDARD_GRAVITY_M_S2, eligibility_errors, write_manifest
from scripts.validate_ground_motion_manifest import validate


def valid_esm_row(event_index: int = 0, record_index: int = 0) -> dict[str, str]:
    event_id = f"IT-2000-{event_index + 1:04d}"
    station = f"S{record_index // 2 + 1:03d}"
    stream = "HNE" if record_index % 2 == 0 else "HNN"
    basename = f"XX.{station}.00.{stream}.D.{event_id}.ACC.MP.ASC"
    parsed_pga = 150.0
    return {
        "source": ESM_SOURCE,
        "event_id": event_id,
        "raw_header_event_id": event_id,
        "record_id": basename,
        "waveform_detail_id": "",
        "stream": stream,
        "raw_filename": basename,
        "network_code": "XX",
        "station_id": station,
        "location_code": "00",
        "component": "horizontal acceleration",
        "sampling_interval_s": "0.01",
        "usable_duration_s": "20.0",
        "original_units": "cm/s^2",
        "normalized_units": "m/s^2",
        "ndata": "2001",
        "parsed_sample_count": "2001",
        "raw_duration_derivation": "explicit:DURATION_S",
        "pga_cm_s2": str(parsed_pga),
        "source_header_pga_cm_s2": str(parsed_pga),
        "pga_g": str(parsed_pga / (STANDARD_GRAVITY_M_S2 * 100.0)),
        "event_date": "2000-01-01",
        "event_time_utc": "2000-01-01T00:00:00Z",
        "latitude": "40.0",
        "longitude": "29.0",
        "partition": "",
        "source_url_or_access_reference": (
            f"https://esm-db.eu/esmws/eventdata/1/query?eventid={event_id}&network=XX&station={station}"
        ),
        "preprocessing_status": "source-distributed ESM MP ASCII validated",
        "source_processing_type": "MP",
        "source_quality_class": "GOOD",
        "raw_sha256": f"{event_index * 4 + record_index + 1:064x}",
        "processed_sha256": f"{event_index * 4 + record_index + 1001:064x}",
        "data_license": "D (network default license)",
        "data_citation": "Engineering Strong Motion Database citation",
        "raw_redistribution_allowed": "false",
        "eligibility_status": "",
        "eligibility_reason": "",
    }


def esm_rows() -> list[dict[str, str]]:
    return [valid_esm_row(event, record) for event in range(40) for record in range(4)]


def test_valid_esm_row_satisfies_active_row_contract():
    assert eligibility_errors(valid_esm_row()) == []


@pytest.mark.parametrize("derivation", ["fallback", "explicit", "arbitrary unknown derivation"])
def test_esm_contract_rejects_noncanonical_duration_derivations(derivation: str):
    row = valid_esm_row()
    row["raw_duration_derivation"] = derivation
    assert any("unsupported ESM raw_duration_derivation" in error for error in eligibility_errors(row))


def test_esm_contract_accepts_frozen_fallback_duration_derivation():
    row = valid_esm_row()
    row["raw_duration_derivation"] = "(NDATA - 1) * SAMPLING_INTERVAL_S"
    assert eligibility_errors(row) == []


def test_esm_contract_rejects_mismatched_fallback_duration():
    row = valid_esm_row()
    row["raw_duration_derivation"] = "(NDATA - 1) * SAMPLING_INTERVAL_S"
    row["usable_duration_s"] = "20.0001"
    assert any("fallback usable_duration_s is inconsistent" in error for error in eligibility_errors(row))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ndata", "1"),
        ("ndata", "invalid"),
        ("parsed_sample_count", "2000"),
        ("parsed_sample_count", "invalid"),
        ("sampling_interval_s", "nan"),
    ],
)
def test_esm_contract_rejects_malformed_fallback_evidence(field: str, value: str):
    row = valid_esm_row()
    row["raw_duration_derivation"] = "(NDATA - 1) * SAMPLING_INTERVAL_S"
    row[field] = value
    assert eligibility_errors(row)


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.invalid/esm-db.eu/esmws/eventdata/1/query",
        "http://esm-db.eu/esmws/eventdata/1/query",
        "https://evil.esm-db.eu/esmws/eventdata/1/query",
        "https://esm-db.eu/unrelated",
        "https://esm-db.eu/esmws/eventdata/1/./query",
        "https://esm-db.eu/esmws/eventdata/1/../../unrelated",
        "https://esm-db.eu/esmws/eventdata/1/../query",
        "https://esm-db.eu/esmws/eventdata/1/%2e/query",
        "https://esm-db.eu/esmws/eventdata/1/%2E/query",
        "https://esm-db.eu/esmws/eventdata/1/%2e%2e/unrelated",
        "https://esm-db.eu/esmws/eventdata/1/%2E%2E/unrelated",
        "https://esm-db.eu/esmws/eventdata/1/.%2e/unrelated",
        "https://esm-db.eu/esmws/eventdata/1/%2e./unrelated",
    ],
)
def test_esm_contract_rejects_invalid_eventdata_provenance_urls(url: str):
    row = valid_esm_row()
    row["source_url_or_access_reference"] = url
    assert any("not an Event-Data service reference" in error for error in eligibility_errors(row))


def test_esm_contract_accepts_exact_https_eventdata_service_url():
    row = valid_esm_row()
    row["source_url_or_access_reference"] = "https://esm-db.eu/esmws/eventdata/1/query?eventid=TEST"
    assert eligibility_errors(row) == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("raw_header_event_id", "OTHER", "does not match ASCII EVENT_ID"),
        ("record_id", "wrong.ASC", "exact source-distributed ASCII basename"),
        ("stream", "HNZ", "eligible HN/HG/HL horizontal"),
        ("parsed_sample_count", "2000", "does not equal NDATA"),
        ("source_header_pga_cm_s2", "150.02", "disagrees with source header"),
        ("data_citation", "", "blank data_citation"),
        ("source_processing_type", "", "blank source_processing_type"),
        ("raw_redistribution_allowed", "true", "raw redistribution must remain false"),
    ],
)
def test_esm_contract_fails_closed_on_required_evidence(field: str, value: str, message: str):
    row = valid_esm_row()
    row[field] = value
    assert any(message in error for error in eligibility_errors(row))


def test_esm_pga_g_must_match_parsed_component_pga():
    row = valid_esm_row()
    row["pga_g"] = "0.99"
    assert any("pga_g is inconsistent" in error for error in eligibility_errors(row))


def test_final_validator_accepts_complete_esm_only_fixture(tmp_path: Path):
    manifest = build(esm_rows())
    path = tmp_path / "esm-manifest.csv"
    write_manifest(manifest, path)
    assert validate(path) == []


def test_final_validator_rejects_non_esm_source_even_when_shape_is_valid(tmp_path: Path):
    manifest = build(esm_rows())
    manifest[0]["source"] = "AFAD_TADAS"
    path = tmp_path / "mixed-source-manifest.csv"
    write_manifest(manifest, path)
    errors = validate(path)
    assert any("final manifest source must be ESM" in error for error in errors)
    assert any("final manifest must be single-source ESM" in error for error in errors)
