import zipfile

from scripts.audit_afad_tadas_raw_zip import audit_zip


def _realish_component(stream: str, peak: float = 160.0) -> bytes:
    ndata = 1001
    samples = [0.0] * ndata
    samples[-1] = peak
    text = "\n".join([
        "EVENT_ID: 0",
        f"STREAM: {stream}",
        "STATION_CODE: 1658",
        "STATION_NAME:",
        "STATION_LATITUDE_DEGREE: 40.424085",
        "STATION_LONGITUDE_DEGREE: 29.16722",
        "STATION_ELEVATION_M: 20.0",
        "EVENT_DATE_YYYYMMDD: 20240223",
        "EVENT_TIME_HHMMSS: 121432",
        "EVENT_LATITUDE: 40.0",
        "EVENT_LONGITUDE: 29.0",
        "SAMPLING_INTERVAL_S: 0.01",
        f"NDATA: {ndata}",
        "UNITS: cm/s^2",
        f"PGA_CM/S^2: {peak}",
        "DATA_LICENSE: U (unknown license)",
    ])
    return (text + "\n" + " ".join(map(str, samples)) + "\n").encode()


def test_real_afad_station_code_and_degree_headers_are_preserved(tmp_path):
    path = tmp_path / "raw.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("example.asc", _realish_component("HNE"))

    row = audit_zip(
        path,
        "620807",
        "2136302",
        "https://tadas.afad.gov.tr/waveform-detail/2136302",
    )["components"][0]

    assert row["station_id"] == "1658"
    assert row["station_latitude"] == "40.424085"
    assert row["station_longitude"] == "29.16722"
    assert row["eligibility_checks"]["required_provenance"] is True
    assert "required_provenance" not in row["eligibility_reasons"]
    assert row["eligibility_status"] == "PASS"
