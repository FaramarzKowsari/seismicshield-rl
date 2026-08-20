from __future__ import annotations

import io
import zipfile

import pytest

from scripts import probe_esm_flatfile_eventdata as mod


SAMPLE = {
    "event_id": "IT-2005-0043",
    "net_name": "1V",
    "station_code": "ACC7",
    "location_code": "00",
    "instr_code": "HN",
    "processing_type": "mp",
    "class": "GOOD",
    "corr_hz_PGA": 0.147,
    "uncorr_PGA": 0.15,
}


def test_choose_probe_record_from_list():
    assert mod.choose_probe_record([SAMPLE]) == SAMPLE


def test_choose_probe_record_rejects_missing_identity():
    with pytest.raises(ValueError, match="missing required keys"):
        mod.choose_probe_record([{"event_id": "E"}])


def test_processing_and_location_normalization():
    assert mod.normalize_processing("mp") == "MP"
    assert mod.normalize_processing("AP") == "AP"
    with pytest.raises(ValueError):
        mod.normalize_processing("x")
    assert mod.normalize_location("00") == "00"
    assert mod.normalize_location("") == "--"


def test_urls_are_exact_and_public_shape():
    flat = mod.build_flatfile_url(SAMPLE)
    assert "eventid=IT-2005-0043" in flat
    assert "network=1V" in flat
    assert "station=ACC7" in flat
    assert "channel=HN" in flat
    assert "processing-type=MP" in flat
    assert "quality-class=BEST%2CGOOD" in flat
    event = mod.build_eventdata_url(SAMPLE)
    assert "catalog=ESM" in event
    assert "location=00" in event
    assert "format=ascii" in event
    assert "data-type=ACC" in event


def test_parse_semicolon_flatfile():
    body = b"ESM_event_id;network_code;station_code;U_pga\nIT-2005-0043;1V;ACC7;150.0\n"
    fields, row = mod.parse_flatfile(body)
    assert fields == ["ESM_event_id", "network_code", "station_code", "U_pga"]
    assert row["U_pga"] == "150.0"


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "sample.asc",
            "EVENT_ID: IT-2005-0043\nSTATION_CODE: ACC7\nSAMPLING_INTERVAL_S: 0.01\nNDATA: 1001\nUNITS: cm/s^2\n0.0\n",
        )
    return buf.getvalue()


def test_inspect_ascii_zip_extracts_header_shape():
    info = mod.inspect_ascii_zip(_zip_bytes())
    assert info["file_count"] == 1
    assert info["file_names"] == ["sample.asc"]
    assert "EVENT_ID" in info["header_keys"]
    assert "SAMPLING_INTERVAL_S" in info["header_keys"]


def test_inspect_ascii_zip_rejects_empty_archive():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    with pytest.raises(ValueError, match="empty"):
        mod.inspect_ascii_zip(buf.getvalue())
