import hashlib
from pathlib import Path

import pytest

from scripts.audit_esm_selected_event_records_exhaustive import (
    esm_record_id,
    load_selected_event_ids,
    parse_numeric_samples,
    validate_member_samples,
)


def _member(samples: list[float], *, pga: float | None = None, ndata: int | None = None) -> bytes:
    n = len(samples) if ndata is None else ndata
    p = max(abs(value) for value in samples) if pga is None else pga
    text = "\n".join(
        [
            "EVENT_ID: TEST-EVENT",
            "NETWORK: XX",
            "STATION_CODE: ABC",
            "LOCATION: 00",
            "SAMPLING_INTERVAL_S: 0.01",
            f"NDATA: {n}",
            "DURATION_S: 0.02",
            "STREAM: HNE",
            "UNITS: cm/s^2",
            f"PGA_CM/S^2: {p}",
            "DATA_LICENSE: D",
            "DATA_CITATION: fixture citation",
            "USER5:",
            *(str(value) for value in samples),
            "",
        ]
    )
    return text.encode()


def test_parse_numeric_samples_starts_after_headers():
    body = _member([0.0, -2.5, 1.25])
    assert parse_numeric_samples(body.decode()) == [0.0, -2.5, 1.25]


def test_validate_member_samples_checks_count_and_pga():
    body = _member([0.0, -2.5, 1.25])
    result = validate_member_samples(body)
    assert result["parsed_sample_count"] == 3
    assert result["parsed_pga_cm_s2"] == 2.5
    assert result["header_pga_cm_s2"] == 2.5
    assert result["source_member_sha256"] == hashlib.sha256(body).hexdigest()


def test_validate_member_samples_rejects_ndata_mismatch():
    with pytest.raises(ValueError, match="sample count"):
        validate_member_samples(_member([0.0, 1.0, 2.0], ndata=4))


def test_validate_member_samples_rejects_pga_mismatch_over_frozen_tolerance():
    with pytest.raises(ValueError, match="parsed PGA disagrees"):
        validate_member_samples(_member([0.0, 2.0], pga=2.02))


def test_esm_record_id_is_exact_basename():
    assert esm_record_id("folder/1V.ACC7.00.HNE.D.IT-2005-0043.ACC.MP.ASC") == (
        "1V.ACC7.00.HNE.D.IT-2005-0043.ACC.MP.ASC"
    )
    assert esm_record_id(r"folder\1V.ACC7.00.HNN.D.IT-2005-0043.ACC.MP.ASC") == (
        "1V.ACC7.00.HNN.D.IT-2005-0043.ACC.MP.ASC"
    )


def test_load_selected_event_ids_requires_exact_unique_count(tmp_path: Path):
    path = tmp_path / "selected.csv"
    path.write_text("event_id\nE1\nE2\n", encoding="utf-8")
    assert load_selected_event_ids(path, expected_count=2) == ["E1", "E2"]
    with pytest.raises(ValueError, match="exactly 3"):
        load_selected_event_ids(path, expected_count=3)


def test_load_selected_event_ids_rejects_duplicates(tmp_path: Path):
    path = tmp_path / "selected.csv"
    path.write_text("event_id\nE1\nE1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_selected_event_ids(path, expected_count=2)
