import hashlib
import json
import zipfile

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


def test_zip_audit_orientation_identity_hashes_license_and_staging(tmp_path):
    path = tmp_path / "raw.zip"
    entries = {name: component(stream) for name, stream in
               (("a.HNE", "HNE"), ("b.HNN", "HNN"), ("c.HNZ", "HNZ"))}
    make_zip(path, entries)
    audit = audit_zip(path, "000123", "WD456", "local TADAS download")
    assert audit["final_manifest"] is False
    assert audit["zip_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    by_stream = {row["stream"]: row for row in audit["components"]}
    assert by_stream["HNE"]["eligibility_status"] == "PASS"
    assert by_stream["HNN"]["eligibility_status"] == "PASS"
    assert by_stream["HNZ"]["eligibility_status"] == "FAIL"
    assert by_stream["HNZ"]["eligibility_reasons"] == ["horizontal_orientation"]
    row = by_stream["HNE"]
    assert row["event_id"] == "000123" and row["raw_header_event_id"] == "0"
    assert row["record_id"] == "WD456:HNE"
    assert row["parsed_sample_count"] == row["ndata"] == 501
    assert row["usable_duration_s"] == 10.0
    assert row["raw_duration_derivation"] == "(NDATA - 1) * SAMPLING_INTERVAL_S"
    assert row["event_time_utc"] == "2020-01-02T03:04:05Z"
    assert row["data_license"] == "U (unknown license)"
    assert row["raw_redistribution_allowed"] is False
    assert row["raw_sha256"] == hashlib.sha256(entries["a.HNE"]).hexdigest()
    out = tmp_path / "staging" / "audit.json"
    write_audit(audit, out)
    assert json.loads(out.read_text())["final_manifest"] is False
    assert not (tmp_path / "data/manifests/ground_motion_manifest.csv").exists()


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
