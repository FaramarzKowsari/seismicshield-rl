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


def _zip(member_name: str, payload: bytes) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name, payload)
    return stream.getvalue()


def _row(raw: bytes, processed: bytes, *, count: int = 4) -> dict[str, str]:
    return {
        "record_id": "IT.TEST..HNN.D.TEST.ACC.MP.ASC",
        "raw_filename": "IT.TEST..HNN.D.TEST.ACC.MP.ASC",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "processed_sha256": hashlib.sha256(processed).hexdigest(),
        "parsed_sample_count": str(count),
        "ndata": str(count),
        "sampling_interval_s": "0.1",
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


def test_materialize_row_accepts_nested_zip_member_and_exact_processed_hash(tmp_path: Path):
    raw = b"HEADER: fixture\n1 -2 3.50 0\n"
    processed = normalized_csv_bytes(parse_samples_decimal(raw.decode()), Decimal("0.1"))
    row = _row(raw, processed)
    payload = _zip(f"nested/path/{row['raw_filename']}", raw)

    output, existed = materialize_row(row, payload, tmp_path)
    assert not existed
    assert output.read_bytes() == processed
    assert output.name == f"{row['processed_sha256']}.csv"

    replay, existed = materialize_row(row, payload, tmp_path)
    assert existed
    assert replay == output


def test_materialize_row_rejects_raw_hash_change(tmp_path: Path):
    raw = b"HEADER: fixture\n1 -2 3.50 0\n"
    processed = normalized_csv_bytes(parse_samples_decimal(raw.decode()), Decimal("0.1"))
    row = _row(raw, processed)
    payload = _zip(row["raw_filename"], raw + b"5\n")
    with pytest.raises(ValueError, match="raw SHA-256 mismatch"):
        materialize_row(row, payload, tmp_path)


def test_materialize_row_rejects_sample_count_change(tmp_path: Path):
    raw = b"HEADER: fixture\n1 -2 3.50 0\n"
    processed = normalized_csv_bytes(parse_samples_decimal(raw.decode()), Decimal("0.1"))
    row = _row(raw, processed, count=5)
    payload = _zip(row["raw_filename"], raw)
    with pytest.raises(ValueError, match="sample-count mismatch"):
        materialize_row(row, payload, tmp_path)


def test_extract_member_rejects_ambiguous_basename():
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("one/record.ASC", b"1\n")
        archive.writestr("two/record.ASC", b"1\n")
    with pytest.raises(ValueError, match="exactly one ESM ZIP member"):
        extract_member(stream.getvalue(), "record.ASC")
