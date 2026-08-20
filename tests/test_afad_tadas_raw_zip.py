import hashlib
import json
import zipfile

import pytest

from scripts.audit_afad_tadas_raw_zip import audit_zip, parse_dyna_ascii, write_audit


def component(stream="HNE", *, dt="0.020", ndata=501, actual_count=None,
              duration="", pga="150.00", peak=150.0):
    count = ndata if actual_count is None else actual_count
    samples = [0.0] * count
    samples[-1] = peak
    headers = [
        "EVENT_ID: 0", f"STREAM: {stream}", "STATION_ID: SYN01",
        "EVENT_DATE_YYYYMMDD: 20200102", "EVENT_TIME_HHMMSS: 030405",
        "EVENT_LATITUDE: 40.0", "EVENT_LONGITUDE: 30.0",
        "STATION_LATITUDE: 40.1", "STATION_LONGITUDE: 30.1",
        f"SAMPLING_INTERVAL_S: {dt}", f"NDATA: {ndata}", f"DURATION_S: {duration}",
        "UNITS: cm/s^2", f"PGA_CM/S^2: {pga}", "DATA_LICENSE: U (unknown license)",
        "COMMENT: value:with:colons",
    ]
    return ("\n".join(headers) + "\n" + " ".join(map(str, samples)) + "\n").encode()


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            archive.writestr(info, raw)


def test_parser_splits_header_on_first_colon():
    headers, samples = parse_dyna_ascii(component())
    assert headers["COMMENT"] == "value:with:colons"
    assert len(samples) == 501


def test_zip_audit_generic_filenames_orientation_identity_hashes_and_staging(tmp_path):
    path = tmp_path / "raw.zip"
    entries = {name: component(stream) for name, stream in
               (("station_HNE.txt", "HNE"), ("station_HNN.txt", "HNN"),
                ("station_HNZ.txt", "HNZ"))}
    entries["README.txt"] = b"This archive contains synthetic test components.\n"
    make_zip(path, entries)
    audit = audit_zip(path, "000123", "456", "local TADAS download")
    assert audit["final_manifest"] is False
    assert audit["zip_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    by_stream = {row["stream"]: row for row in audit["components"]}
    assert by_stream["HNE"]["eligibility_status"] == "PASS"
    assert by_stream["HNN"]["eligibility_status"] == "PASS"
    assert by_stream["HNZ"]["eligibility_status"] == "FAIL"
    assert by_stream["HNZ"]["eligibility_reasons"] == ["horizontal_orientation"]
    row = by_stream["HNE"]
    assert row["event_id"] == "000123" and row["raw_header_event_id"] == "0"
    assert row["record_id"] == "456:HNE"
    assert row["parsed_sample_count"] == row["ndata"] == 501
    assert row["usable_duration_s"] == 10.0
    assert row["raw_duration_derivation"] == "(NDATA - 1) * SAMPLING_INTERVAL_S"
    assert row["event_time_utc"] == "2020-01-02T03:04:05Z"
    assert row["data_license"] == "U (unknown license)"
    assert row["raw_redistribution_allowed"] is False
    assert row["raw_sha256"] == hashlib.sha256(entries["station_HNE.txt"]).hexdigest()
    out = tmp_path / "staging" / "audit.json"
    write_audit(audit, out)
    assert json.loads(out.read_text())["final_manifest"] is False
    assert not (tmp_path / "data/manifests/ground_motion_manifest.csv").exists()


def test_real_afad_degree_coordinate_and_station_code_aliases(tmp_path):
    raw = component().decode()
    raw = raw.replace("STATION_ID: SYN01", "STATION_CODE: 1658")
    raw = raw.replace("EVENT_LATITUDE: 40.0", "EVENT_LATITUDE_DEGREE: 40.41806")
    raw = raw.replace("EVENT_LONGITUDE: 30.0", "EVENT_LONGITUDE_DEGREE: 29.16083")
    raw = raw.replace("STATION_LATITUDE: 40.1", "STATION_LATITUDE_DEGREE: 40.424085")
    raw = raw.replace("STATION_LONGITUDE: 30.1", "STATION_LONGITUDE_DEGREE: 29.16722")
    path = tmp_path / "real-afad-header.zip"
    make_zip(path, {"20240223121432_1658_ap_RawAcc_E.asc": raw.encode()})

    row = audit_zip(
        path,
        "620807",
        "2136302",
        "https://tadas.afad.gov.tr/waveform-detail/2136302",
    )["components"][0]
    assert row["eligibility_status"] == "PASS"
    assert row["station_id"] == "1658"
    assert row["event_latitude"] == "40.41806"
    assert row["event_longitude"] == "29.16083"
    assert row["station_latitude"] == "40.424085"
    assert row["station_longitude"] == "29.16722"
    assert row["eligibility_checks"]["required_provenance"] is True


def test_failures_are_reported_without_repair(tmp_path):
    path = tmp_path / "bad.zip"
    make_zip(path, {
        "count.HNE": component(actual_count=500),
        "dt.HNN": component("HNN", dt="0.021"),
        "pga.HNE": component(pga="151.00"),
    })
    rows = {row["raw_filename"]: row for row in
            audit_zip(path, "123", "456", "local source")["components"]}
    assert "sample_count_consistency" in rows["count.HNE"]["eligibility_reasons"]
    assert "usable_duration" in rows["count.HNE"]["eligibility_reasons"]
    assert "valid_sampling_interval" in rows["dt.HNN"]["eligibility_reasons"]
    assert "pga_header_data_agreement" in rows["pga.HNE"]["eligibility_reasons"]


@pytest.mark.parametrize("detail", ["", "WD456", "45.6", "   ", "٤٥٦"])
def test_waveform_detail_id_must_be_decimal_digits(tmp_path, detail):
    path = tmp_path / "raw.zip"
    make_zip(path, {"station.txt": component()})
    with pytest.raises(ValueError, match="waveform_detail_id"):
        audit_zip(path, "123", detail, "local source")


def test_waveform_detail_id_leading_zeros_are_preserved(tmp_path):
    path = tmp_path / "raw.zip"
    make_zip(path, {"station.txt": component()})
    row = audit_zip(path, "123", "00456", "local source")["components"][0]
    assert row["waveform_detail_id"] == "00456"
    assert row["record_id"] == "00456:HNE"


def test_malformed_waveform_like_file_fails_closed(tmp_path):
    path = tmp_path / "raw.zip"
    make_zip(path, {"station.txt": b"\xef\xbb\xbfSTREAM: HNE\nnot numeric data\n"})
    with pytest.raises(ValueError, match="malformed waveform component"):
        audit_zip(path, "123", "456", "local source")
