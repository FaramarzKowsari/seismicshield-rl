from __future__ import annotations

from decimal import Decimal
import hashlib
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from scripts.hydrate_frozen_esm_manifest_v0_8_2 import (
    extract_member,
    materialize_row,
    normalized_csv_bytes,
    parse_samples_decimal,
)

RECORD_ID = "IT.TEST..HNN.D.TEST-EVENT.ACC.MP.ASC"


def _zip(member_name: str, payload: bytes) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name, payload)
    return stream.getvalue()


def _raw(
    *,
    comment: str = "frozen",
    station: str = "TEST",
    samples: str = "1 -2 3.50 0",
    ndata: int = 4,
    license_text: str = "CC-BY4_0 (https://creativecommons.org/licenses/by/4.0/)",
) -> bytes:
    return (
        "EVENT_ID: TEST-EVENT\n"
        "STREAM: HNN\n"
        "NETWORK: IT\n"
        f"STATION_CODE: {station}\n"
        "LOCATION:\n"
        "UNITS: cm/s^2\n"
        f"NDATA: {ndata}\n"
        "SAMPLING_INTERVAL_S: 0.1\n"
        "DURATION_S: 0.3\n"
        "PGA_CM/S^2: 3.50\n"
        f"DATA_LICENSE: {license_text}\n"
        f"COMMENT: {comment}\n"
        f"{samples}\n"
    ).encode()


def _processed(raw: bytes) -> bytes:
    return normalized_csv_bytes(parse_samples_decimal(raw.decode()), Decimal("0.1"))


def _row(raw: bytes, processed: bytes, *, count: int = 4) -> dict[str, str]:
    return {
        "event_id": "TEST-EVENT",
        "raw_header_event_id": "TEST-EVENT",
        "record_id": RECORD_ID,
        "raw_filename": RECORD_ID,
        "stream": "HNN",
        "network_code": "IT",
        "station_id": "TEST",
        "location_code": "",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "processed_sha256": hashlib.sha256(processed).hexdigest(),
        "parsed_sample_count": str(count),
        "ndata": str(count),
        "sampling_interval_s": "0.1",
        "usable_duration_s": "0.3",
        "pga_cm_s2": "3.50",
        "source_header_pga_cm_s2": "3.50",
        "data_license": "CC-BY4_0 (https://creativecommons.org/licenses/by/4.0/)",
    }


def test_parse_and_normalize_match_frozen_decimal_semantics():
    text = "HEADER: fixture\nUNITS: cm/s^2\n1 -2 3.50 0\n"
    samples = parse_samples_decimal(text)
    assert samples == [Decimal("1"), Decimal("-2"), Decimal("3.50"), Decimal("0")]
    assert normalized_csv_bytes(samples, Decimal("0.1")) == (
        b"time_s,accel_mps2\n"
        b"0,0.01\n"
        b"0.1,-0.02\n"
        b"0.2,0.035\n"
        b"0.3,0\n"
    )


def test_materialize_row_accepts_nested_zip_member_and_exact_raw_hash(tmp_path: Path):
    raw = _raw()
    processed = _processed(raw)
    row = _row(raw, processed)
    payload = _zip(f"nested/path/{row['raw_filename']}", raw)

    output, existed, drift = materialize_row(row, payload, tmp_path)
    assert not existed
    assert drift is None
    assert output.read_bytes() == processed
    assert output.name == f"{row['processed_sha256']}.csv"

    replay, existed, drift = materialize_row(row, payload, tmp_path)
    assert existed
    assert drift is None
    assert replay == output


def test_materialize_row_accepts_header_only_raw_drift_when_processed_hash_is_exact(
    tmp_path: Path,
):
    frozen_raw = _raw(comment="frozen source header")
    live_raw = _raw(comment="live source header changed")
    processed = _processed(frozen_raw)
    assert _processed(live_raw) == processed
    row = _row(frozen_raw, processed)

    output, existed, drift = materialize_row(row, _zip(RECORD_ID, live_raw), tmp_path)
    assert not existed
    assert output.read_bytes() == processed
    assert drift is not None
    assert drift["record_id"] == RECORD_ID
    assert drift["expected_raw_sha256"] == hashlib.sha256(frozen_raw).hexdigest()
    assert drift["observed_live_raw_sha256"] == hashlib.sha256(live_raw).hexdigest()
    assert drift["processed_sha256_reproduced_exactly"] == row["processed_sha256"]


def test_materialize_row_rejects_changed_samples_even_when_identity_headers_match(tmp_path: Path):
    frozen_raw = _raw()
    live_raw = _raw(comment="live", samples="1 -2 3.50 1")
    row = _row(frozen_raw, _processed(frozen_raw))
    with pytest.raises(ValueError, match="processed SHA-256 mismatch"):
        materialize_row(row, _zip(RECORD_ID, live_raw), tmp_path)


def test_materialize_row_rejects_live_identity_change(tmp_path: Path):
    frozen_raw = _raw()
    live_raw = _raw(station="OTHER")
    row = _row(frozen_raw, _processed(frozen_raw))
    with pytest.raises(ValueError, match="STATION_CODE mismatch"):
        materialize_row(row, _zip(RECORD_ID, live_raw), tmp_path)


def test_materialize_row_rejects_license_family_change(tmp_path: Path):
    frozen_raw = _raw()
    live_raw = _raw(license_text="CC-BY3_0-IT (http://creativecommons.org/licenses/by/3.0/)")
    row = _row(frozen_raw, _processed(frozen_raw))
    with pytest.raises(ValueError, match="license mismatch"):
        materialize_row(row, _zip(RECORD_ID, live_raw), tmp_path)


def test_materialize_row_rejects_sample_count_change(tmp_path: Path):
    raw = _raw()
    row = _row(raw, _processed(raw), count=5)
    with pytest.raises(ValueError, match="sample-count mismatch"):
        materialize_row(row, _zip(RECORD_ID, raw), tmp_path)


def test_extract_member_rejects_ambiguous_basename():
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("one/record.ASC", b"1\n")
        archive.writestr("two/record.ASC", b"1\n")
    with pytest.raises(ValueError, match="exactly one ESM ZIP member"):
        extract_member(stream.getvalue(), "record.ASC")
