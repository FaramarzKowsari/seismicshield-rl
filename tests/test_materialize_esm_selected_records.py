from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts.ground_motion_manifest import ESM_SOURCE, sha_key
from scripts.materialize_esm_selected_records import (
    _canonical_decimal,
    _load_selection_lock_hashes,
    _normalized_csv_bytes,
    _request_metadata,
    _verify_locked_inputs,
    materialize_one,
)


def _ascii_member(event_id: str = "IT-TEST-0001", station: str = "STA1") -> bytes:
    samples = ["200.000", "-100.000", "50.000"] + ["0.000"] * 998
    header = "\n".join(
        [
            f"EVENT_ID: {event_id}",
            "EVENT_DATE_YYYYMMDD: 20200102",
            "EVENT_TIME_HHMMSS: 030405",
            "EVENT_LATITUDE_DEGREE: 40.1",
            "EVENT_LONGITUDE_DEGREE: 29.2",
            "NETWORK: XX",
            f"STATION_CODE: {station}",
            "LOCATION: 00",
            "SAMPLING_INTERVAL_S: 0.01",
            "NDATA: 1001",
            "DURATION_S: 10.0",
            "UNITS: cm/s^2",
            "PGA_CM/S^2: 200.000",
            "STREAM: HNE",
            "DATA_LICENSE: D (network default license)",
            "DATA_CITATION: ESM source citation for validation",
            *samples,
            "",
        ]
    )
    return header.encode("utf-8")


def _fixture(tmp_path: Path):
    event_id = "IT-TEST-0001"
    member_name = "nested/source.ASC"
    record_id = "source.ASC"
    member = _ascii_member(event_id)
    zip_path = tmp_path / "source.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(member_name, member)
    zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    member_sha = hashlib.sha256(member).hexdigest()
    record_hash = sha_key("record", {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id})
    url = (
        "https://esm-db.eu/esmws/eventdata/1/query?eventid=IT-TEST-0001&catalog=ESM&network=XX"
        "&station=STA1&location=00&channel=HN%2A&format=ascii&processing-type=MP&data-type=ACC"
        "&quality-class=BEST%2CGOOD"
    )
    selection = {
        "event_rank": "1",
        "event_id": event_id,
        "record_rank": "1",
        "source": ESM_SOURCE,
        "record_id": record_id,
        "record_hash": record_hash,
        "stream": "HNE",
        "raw_filename": record_id,
        "network_code": "XX",
        "station_id": "STA1",
        "location_code": "00",
        "source_member_sha256": member_sha,
        "source_zip_sha256": zip_sha,
        "source_request_url": url,
    }
    record = {
        "source": ESM_SOURCE,
        "record_id": record_id,
        "record_hash_preview": record_hash,
        "file_name": member_name,
        "stream": "HNE",
        "network": "XX",
        "station_code": "STA1",
        "location": "00",
        "source_member_sha256": member_sha,
        "source_zip_sha256": zip_sha,
        "source_request_url": url,
        "source_zip_path": str(zip_path),
    }
    event = {
        "event_id": event_id,
        "status": "COMPLETE_RECORD_INVENTORY",
        "waveform_errors": 0,
        "passing_records_hash_order_preview": [record],
        "waveforms": [
            {
                "status": "AUDITED",
                "processing_type": "MP",
                "quality_class": "GOOD",
                "passing_records_in_request": [record_id],
            }
        ],
    }
    return selection, event


def _write_selection_lock(path: Path, selection_sha: str, inventory_sha: str) -> None:
    path.write_text(
        "\n".join(
            [
                "version: v0.8.0",
                "local_selection_artifact:",
                "  path: results/local/esm/esm_selected_records_160.csv",
                f"  sha256: {selection_sha}",
                "source_inventory:",
                "  path: results/local/esm/esm_selected_event_record_inventory.json",
                f"  sha256_at_selection: {inventory_sha}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_canonical_normalized_csv_is_deterministic():
    from decimal import Decimal

    payload = _normalized_csv_bytes(
        [Decimal("100"), Decimal("-50.000"), Decimal("0")],
        Decimal("0.01"),
    )
    assert payload == b"time_s,accel_mps2\n0,1\n0.01,-0.5\n0.02,0\n"
    assert _canonical_decimal(Decimal("1000.000")) == "1000"


def test_request_metadata_must_be_unambiguous():
    event = {
        "waveforms": [
            {
                "status": "AUDITED",
                "processing_type": "MP",
                "quality_class": "GOOD",
                "passing_records_in_request": ["x.ASC"],
            }
        ]
    }
    assert _request_metadata(event, "x.ASC") == ("MP", "GOOD")
    event["waveforms"].append(
        {
            "status": "AUDITED",
            "processing_type": "AP",
            "quality_class": "GOOD",
            "passing_records_in_request": ["x.ASC"],
        }
    )
    with pytest.raises(ValueError, match="ambiguous/missing source processing type"):
        _request_metadata(event, "x.ASC")


def test_materialize_one_uses_canonical_basename_and_private_si_bytes(tmp_path: Path):
    selection, event = _fixture(tmp_path)
    processed_dir = tmp_path / "processed"
    row = materialize_one(selection, event, processed_dir)
    assert row["raw_filename"] == "source.ASC"
    assert row["record_id"] == "source.ASC"
    assert row["raw_header_event_id"] == "IT-TEST-0001"
    assert row["normalized_units"] == "m/s^2"
    assert row["source_processing_type"] == "MP"
    assert row["source_quality_class"] == "GOOD"
    assert row["partition"] == ""
    assert row["eligibility_status"] == ""
    processed = Path(row["processed_path"])
    assert processed.exists()
    assert processed.read_bytes().startswith(b"time_s,accel_mps2\n")
    assert hashlib.sha256(processed.read_bytes()).hexdigest() == row["processed_sha256"]


def test_materialize_one_rejects_changed_source_member(tmp_path: Path):
    selection, event = _fixture(tmp_path)
    selection["source_member_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="inventory member SHA-256 disagrees"):
        materialize_one(selection, event, tmp_path / "processed")


def test_frozen_selection_and_inventory_hashes_are_enforced(tmp_path: Path):
    selection = tmp_path / "selection.csv"
    inventory = tmp_path / "inventory.json"
    lock = tmp_path / "selection-lock.yaml"
    selection.write_bytes(b"frozen-selection\n")
    inventory.write_bytes(b"frozen-inventory\n")
    selection_sha = hashlib.sha256(selection.read_bytes()).hexdigest()
    inventory_sha = hashlib.sha256(inventory.read_bytes()).hexdigest()
    _write_selection_lock(lock, selection_sha, inventory_sha)

    assert _load_selection_lock_hashes(lock) == (selection_sha, inventory_sha)
    assert _verify_locked_inputs(lock, selection, inventory) == (selection_sha, inventory_sha)

    selection.write_bytes(b"regenerated-selection\n")
    with pytest.raises(ValueError, match="selected-record CSV SHA-256 disagrees"):
        _verify_locked_inputs(lock, selection, inventory)


def test_frozen_inventory_hash_mismatch_is_rejected(tmp_path: Path):
    selection = tmp_path / "selection.csv"
    inventory = tmp_path / "inventory.json"
    lock = tmp_path / "selection-lock.yaml"
    selection.write_bytes(b"frozen-selection\n")
    inventory.write_bytes(b"frozen-inventory\n")
    selection_sha = hashlib.sha256(selection.read_bytes()).hexdigest()
    inventory_sha = hashlib.sha256(inventory.read_bytes()).hexdigest()
    _write_selection_lock(lock, selection_sha, inventory_sha)

    inventory.write_bytes(b"edited-inventory\n")
    with pytest.raises(ValueError, match="source inventory SHA-256 disagrees"):
        _verify_locked_inputs(lock, selection, inventory)


def test_malformed_selection_lock_fails_closed(tmp_path: Path):
    lock = tmp_path / "selection-lock.yaml"
    lock.write_text(
        "local_selection_artifact:\n  sha256: not-a-sha\nsource_inventory:\n  sha256_at_selection: also-bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="selection lock has missing/invalid"):
        _load_selection_lock_hashes(lock)


def test_direct_script_help_bootstraps_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/materialize_esm_selected_records.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Materialize the frozen 160-record ESM selection" in result.stdout
