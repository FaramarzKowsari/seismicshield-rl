import io
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import zipfile

import scripts.audit_esm_candidate_events as audit


def _zip_bytes(event="IT-TEST-1", network="XX", station="A", location="00", pga=200.0):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for stream in ("HNE", "HNN", "HNZ"):
            header = "\n".join(
                [
                    f"EVENT_ID: {event}",
                    "EVENT_DATE_YYYYMMDD: 20200101",
                    "EVENT_TIME_HHMMSS: 010203",
                    "EVENT_LATITUDE_DEGREE: 40.0",
                    "EVENT_LONGITUDE_DEGREE: 29.0",
                    "EVENT_DEPTH_KM: 10.0",
                    "MAGNITUDE_W: 6.0",
                    f"NETWORK: {network}",
                    f"STATION_CODE: {station}",
                    f"LOCATION: {location}",
                    "SAMPLING_INTERVAL_S: 0.01",
                    "NDATA: 2001",
                    "DURATION_S: 20.0",
                    f"STREAM: {stream}",
                    "UNITS: cm/s^2",
                    f"PGA_CM/S^2: {pga if stream != 'HNZ' else 50.0}",
                    "DATA_LICENSE: D (network default license)",
                    "DATA_CITATION: Example citation",
                    "0.0",
                ]
            )
            zf.writestr(f"{network}.{station}.{location}.{stream}.ASC", header)
    return payload.getvalue()


def _waveform(station, quality="GOOD", pga=250.0):
    return {
        "network": "XX",
        "station": station,
        "location": "00",
        "instrument": "HN*",
        "processing_type": "MP",
        "quality_class": quality,
        "corr_hz_PGA_cm_s2": pga,
    }


def _event(waveforms):
    return {
        "event_id": "IT-TEST-1",
        "event_times": ["2020-01-01T01:02:03"],
        "rows_at_or_above_0p15g": len(waveforms),
        "max_corr_hz_PGA_cm_s2": 250.0,
        "candidate_waveforms": waveforms,
    }


def test_eventdata_url_uses_exact_candidate_quality_class():
    url = audit.build_eventdata_url("IT-TEST-1", _waveform("A", quality="BAD"))
    query = parse_qs(urlparse(url).query)
    assert query["eventid"] == ["IT-TEST-1"]
    assert query["channel"] == ["HN*"]
    assert query["quality-class"] == ["BAD"]
    assert query["processing-type"] == ["MP"]
    assert query["data-type"] == ["ACC"]


def test_passing_records_requires_same_accelerometric_family():
    inspection = {
        "components": [
            {"component_pass": True, "stream": "HNE"},
            {"component_pass": True, "stream": "HNN"},
            {"component_pass": True, "stream": "HGE"},
        ]
    }
    rows = audit.passing_records(inspection, {"instrument": "HN*"})
    assert [row["stream"] for row in rows] == ["HNE", "HNN"]


def test_event_becomes_eligible_after_four_distinct_passing_horizontals(monkeypatch, tmp_path: Path):
    bodies = {
        "A": _zip_bytes(station="A"),
        "B": _zip_bytes(station="B"),
        "C": _zip_bytes(station="C"),
    }

    def fake_fetch(url, timeout_s):
        station = parse_qs(urlparse(url).query)["station"][0]
        return 200, "application/zip", bodies[station]

    monkeypatch.setattr(audit, "fetch_bytes", fake_fetch)
    result = audit.audit_event(_event([_waveform("A"), _waveform("B"), _waveform("C")]), tmp_path, 5.0, 0.0)
    assert result["status"] == "ELIGIBLE_EVENT_COMPONENT_AUDIT"
    assert result["passing_horizontal_count"] == 4
    assert result["candidate_waveforms_audited"] == 2
    assert result["early_stop_after_four_passing_horizontals"] is True
    assert len(result["passing_horizontal_records"]) == 4
    assert result["event_metadata"]["event_latitude_degree"] == 40.0


def test_error_with_fewer_than_four_passes_is_incomplete_not_rejected(monkeypatch, tmp_path: Path):
    body = _zip_bytes(station="A")

    def fake_fetch(url, timeout_s):
        station = parse_qs(urlparse(url).query)["station"][0]
        if station == "B":
            raise RuntimeError("temporary source failure")
        return 200, "application/zip", body

    monkeypatch.setattr(audit, "fetch_bytes", fake_fetch)
    result = audit.audit_event(_event([_waveform("A"), _waveform("B")]), tmp_path, 5.0, 0.0)
    assert result["status"] == "ERROR_INCOMPLETE_COMPONENT_AUDIT"
    assert result["passing_horizontal_count"] == 2
    assert result["waveform_errors"] == 1


def test_summary_counts_terminal_and_incomplete_states():
    ledger = {
        "A": {"event_id": "A", "status": "ELIGIBLE_EVENT_COMPONENT_AUDIT"},
        "B": {"event_id": "B", "status": "REJECT_COMPONENT_AUDIT"},
        "C": {"event_id": "C", "status": "ERROR_INCOMPLETE_COMPONENT_AUDIT"},
    }
    summary = audit.summary_payload(ledger, 98)
    assert summary["prescreen_candidate_events"] == 98
    assert summary["eligible_events"] == 1
    assert summary["rejected_events"] == 1
    assert summary["incomplete_error_events"] == 1
    assert summary["final_manifest"] is False
