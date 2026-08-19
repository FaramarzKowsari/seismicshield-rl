import csv
import hashlib

import pytest

from scripts.build_afad_tadas_event_queue import build_event_queue, write_outputs
from scripts.ground_motion_manifest import AFAD_TADAS_SOURCE, sha_key


def write_csv(path, rows, bom=True, newline="\r\n"):
    text = "EventID,EventDate,EpicenterAgency,Longitude,Latitude,MagnitudeType,Magnitude,Depth,Location\n"
    for row in rows:
        text += ",".join(row) + "\n"
    path.write_bytes((("\ufeff" if bom else "") + text.replace("\n", newline)).encode())


def test_bom_exact_ids_blank_rows_and_frozen_order(tmp_path):
    source = tmp_path / "events.csv"
    write_csv(source, [
        (" 000123 ", "2020-01-01", "AFAD", "30", "40", "Mw", "6", "7", "A"),
        ("", "2020-01-02", "AFAD", "31", "41", "Mw", "5", "8", "B"),
        ("98765432101234567890", "2020-01-03", "AFAD", "32", "42", "Ml", "4", "9", "C"),
    ])
    rows, audit = build_event_queue(source)
    assert audit["canonical_source"] == AFAD_TADAS_SOURCE == "AFAD_TADAS"
    assert audit["total_rows"] == 3
    assert audit["rows_with_known_event_id"] == 2
    assert audit["rows_with_blank_event_id"] == 1
    assert audit["source_csv_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    ids = {row["event_id"] for row in rows}
    assert ids == {"000123", "98765432101234567890"}
    assert all(isinstance(row["event_id"], str) and not row["event_id"].endswith(".0") for row in rows)
    assert [row["event_hash"] for row in rows] == sorted(row["event_hash"] for row in rows)
    assert [row["rank"] for row in rows] == [1, 2]
    assert all(row["event_hash"] == sha_key("event", row) for row in rows)
    out = tmp_path / "out"
    write_outputs(rows, audit, out)
    with (out / "event_candidate_queue.csv").open() as handle:
        assert len(list(csv.DictReader(handle))) == 2


def test_duplicate_input_row_is_rejected(tmp_path):
    source = tmp_path / "events.csv"
    row = ("123", "2020-01-01", "AFAD", "30", "40", "Mw", "6", "7", "A")
    write_csv(source, [row, row], bom=False, newline="\n")
    with pytest.raises(ValueError, match="duplicate EventID '123'"):
        build_event_queue(source)


def test_duplicate_event_id_with_conflicting_metadata_is_rejected(tmp_path):
    source = tmp_path / "events.csv"
    write_csv(source, [
        ("123", "2020-01-01", "AFAD", "30", "40", "Mw", "6", "7", "A"),
        ("123", "2021-02-02", "OTHER", "31", "41", "Ml", "5", "8", "B"),
    ])
    with pytest.raises(ValueError, match="duplicate EventID '123'"):
        build_event_queue(source)


def test_different_event_ids_with_identical_metadata_are_allowed(tmp_path):
    source = tmp_path / "events.csv"
    tail = ("2020-01-01", "AFAD", "30", "40", "Mw", "6", "7", "A")
    write_csv(source, [("123", *tail), ("124", *tail)])
    rows, _ = build_event_queue(source)
    assert {row["event_id"] for row in rows} == {"123", "124"}


def test_exact_real_tadas_event_search_headers(tmp_path):
    source = tmp_path / "real_headers.csv"
    source.write_text(
        "EventID,EventDate,EpicenterAgency,EpicenterLon,EpicenterLat,Type,"
        "Magnitude,Depth,Location\n"
        "123,2020-01-01,AFAD,30.25,40.75,Mw,6.1,8,Test location\n",
        encoding="utf-8",
    )
    rows, _ = build_event_queue(source)
    assert rows[0]["longitude"] == "30.25"
    assert rows[0]["latitude"] == "40.75"
    assert rows[0]["magnitude_type"] == "Mw"
    assert all(rows[0][field] for field in ("longitude", "latitude", "magnitude_type"))


def test_hash_contract_changes_with_source_and_id():
    base = {"source": "AFAD_TADAS", "event_id": "123"}
    assert sha_key("event", base) != sha_key("event", {**base, "source": "OTHER"})
    assert sha_key("event", base) != sha_key("event", {**base, "event_id": "124"})
