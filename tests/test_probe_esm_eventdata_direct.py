from __future__ import annotations

import io
import zipfile

import pytest

from scripts import probe_esm_eventdata_direct as mod


SAMPLE = {
    "event_id": "IT-2005-0043",
    "net_name": "1V",
    "station_code": "ACC7",
    "location_code": "00",
    "instr_code": "HN*",
    "processing_type": "mp",
    "class": "GOOD",
    "corr_hz_PGA": 0.147,
}


def test_direct_eventdata_url_preserves_wildcard_identity():
    url = mod.build_eventdata_url(SAMPLE)
    assert "eventid=IT-2005-0043" in url
    assert "catalog=ESM" in url
    assert "network=1V" in url
    assert "station=ACC7" in url
    assert "location=00" in url
    assert "channel=HN%2A" in url
    assert "format=ascii" in url
    assert "processing-type=MP" in url
    assert "data-type=ACC" in url
    assert "quality-class=BEST%2CGOOD" in url


def test_blank_location_avoids_double_dash_backend_collision():
    blank = {**SAMPLE, "location_code": ""}
    url = mod.build_eventdata_url(blank)
    assert "location=" in url
    assert "location=--" not in url
    assert mod.normalize_location(None) == ""
    assert mod.normalize_location("") == ""
    assert mod.normalize_location("--") == ""


def test_instrument_normalization_accepts_accelerometers_only():
    assert mod.normalize_instrument_pattern("HN*") == "HN*"
    assert mod.normalize_instrument_pattern("hn") == "HN*"
    assert mod.normalize_instrument_pattern("HG?") == "HG?"
    with pytest.raises(ValueError, match="non-accelerometric"):
        mod.normalize_instrument_pattern("HH*")


def _component(stream: str, pga: float, *, station: str = "ACC7", location: str = "00") -> str:
    return "\n".join(
        [
            "EVENT_ID: IT-2005-0043",
            "NETWORK: 1V",
            f"STATION_CODE: {station}",
            f"LOCATION: {location}",
            "SAMPLING_INTERVAL_S: 0.005",
            "NDATA: 24001",
            "DURATION_S: 120.0",
            f"STREAM: {stream}",
            "UNITS: cm/s^2",
            f"PGA_CM/S^2: {pga}",
            "DATA_LICENSE: D (network default license)",
            "DATA_CITATION: example citation",
            "0.0",
        ]
    )


def _zip_bytes(*, bad_station: bool = False, location: str = "00") -> bytes:
    buf = io.BytesIO()
    station = "OTHER" if bad_station else "ACC7"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("x.HNE.ASC", _component("HNE", 200.0, station=station, location=location))
        zf.writestr("x.HNN.ASC", _component("HNN", 180.0, station=station, location=location))
        zf.writestr("x.HNZ.ASC", _component("HNZ", 250.0, station=station, location=location))
    return buf.getvalue()


def test_ascii_zip_component_checks_and_vertical_exclusion():
    info = mod.inspect_ascii_zip(_zip_bytes(), {**SAMPLE, "corr_hz_PGA": 200.0})
    assert info["file_count"] == 3
    assert info["horizontal_count"] == 2
    assert info["passing_horizontal_count"] == 2
    by_stream = {row["stream"]: row for row in info["components"]}
    assert by_stream["HNE"]["component_pass"] is True
    assert by_stream["HNN"]["component_pass"] is True
    assert by_stream["HNZ"]["component_pass"] is False
    assert by_stream["HNZ"]["checks"]["horizontal_orientation"] is False
    assert info["max_horizontal_header_pga_cm_s2"] == 200.0
    assert info["dataset_selection_to_header_within_0p01"] is True


def test_blank_location_identity_matches_blank_ascii_header():
    info = mod.inspect_ascii_zip(
        _zip_bytes(location=""),
        {**SAMPLE, "location_code": "", "corr_hz_PGA": 200.0},
    )
    assert info["passing_horizontal_count"] == 2
    assert all(
        row["checks"]["identity"]
        for row in info["components"]
    )


def test_identity_mismatch_fails_closed():
    info = mod.inspect_ascii_zip(_zip_bytes(bad_station=True), SAMPLE)
    assert info["passing_horizontal_count"] == 0
    assert all(not row["checks"]["identity"] for row in info["components"])


def test_component_pga_threshold_is_frozen_0p15g():
    assert mod.PGA_THRESHOLD_CM_S2 == pytest.approx(147.09975)
    low = _component("HNE", 147.0)
    high = _component("HNN", 147.2)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("low.asc", low)
        zf.writestr("high.asc", high)
    info = mod.inspect_ascii_zip(buf.getvalue(), SAMPLE)
    by_stream = {row["stream"]: row for row in info["components"]}
    assert by_stream["HNE"]["checks"]["component_pga"] is False
    assert by_stream["HNN"]["checks"]["component_pga"] is True
