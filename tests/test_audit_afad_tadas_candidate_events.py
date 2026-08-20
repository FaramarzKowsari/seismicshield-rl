import csv
import json
import subprocess
import sys

import pytest

from scripts import audit_afad_tadas_candidate_events as mod


def _candidate_row(event_id="551067", waveform_id=327925, station="8002", pga=200.0):
    return {
        "eaEventId": int(event_id),
        "waveformId": waveform_id,
        "stationCode": station,
        "pga": pga,
    }


def test_candidate_artifact_requires_corrected_query_contract_and_threshold(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({
        "event_id": "551067",
        "query_contract": mod.QUERY_CONTRACT,
        "rows_at_or_above_threshold": [_candidate_row()],
    }), encoding="utf-8")
    rows = mod.candidate_rows_from_artifact(path, "551067")
    assert rows == [{
        "waveform_id": "327925",
        "station_code": "8002",
        "station_summary_pga_cm_s2": 200.0,
        "detail_url": "https://tadas.afad.gov.tr/waveform-detail/327925",
    }]

    bad = json.loads(path.read_text(encoding="utf-8"))
    bad["query_contract"] = "event-specific;fromMagnitude=3"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="stale/unknown query contract"):
        mod.candidate_rows_from_artifact(path, "551067")


def test_candidate_artifact_rejects_duplicate_waveform_and_below_threshold(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({
        "event_id": "551067",
        "query_contract": mod.QUERY_CONTRACT,
        "rows_at_or_above_threshold": [
            _candidate_row(waveform_id=1, station="A"),
            _candidate_row(waveform_id=1, station="B"),
        ],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="repeats waveformId"):
        mod.candidate_rows_from_artifact(path, "551067")

    path.write_text(json.dumps({
        "event_id": "551067",
        "query_contract": mod.QUERY_CONTRACT,
        "rows_at_or_above_threshold": [
            _candidate_row(waveform_id=2, pga=mod.MIN_PGA_CM_S2 - 0.001),
        ],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="below frozen station-summary threshold"):
        mod.candidate_rows_from_artifact(path, "551067")


def test_snapshot_candidates_uses_corrected_ledger_and_candidate_file(tmp_path):
    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()
    candidate = candidate_dir / "rank-00003-event-551067.json"
    candidate.write_text(json.dumps({
        "rank": 3,
        "event_id": "551067",
        "query_contract": mod.QUERY_CONTRACT,
        "rows_at_or_above_threshold": [_candidate_row()],
    }), encoding="utf-8")
    ledger = tmp_path / "screen.csv"
    with ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "rank", "event_id", "query_contract", "status", "candidate_json_path"
        ])
        writer.writeheader()
        writer.writerow({
            "rank": 3,
            "event_id": "551067",
            "query_contract": mod.QUERY_CONTRACT,
            "status": "CANDIDATE_COMPONENT_AUDIT",
            "candidate_json_path": str(candidate),
        })
        writer.writerow({
            "rank": 4,
            "event_id": "123",
            "query_contract": mod.QUERY_CONTRACT,
            "status": "REJECT_SUMMARY_PGA",
            "candidate_json_path": "",
        })
    snapshot = mod.snapshot_candidates(ledger, candidate_dir)
    assert len(snapshot) == 1
    assert snapshot[0]["rank"] == 3
    assert snapshot[0]["event_id"] == "551067"
    assert len(snapshot[0]["station_rows"]) == 1


def test_choose_frozen_records_is_deterministic_and_limited_to_four():
    components = [
        {"record_id": f"{100+i}:HNE" if i % 2 == 0 else f"{100+i}:HNN"}
        for i in range(7)
    ]
    selected_a = mod.choose_frozen_records("551067", components)
    selected_b = mod.choose_frozen_records("551067", list(reversed(components)))
    assert len(selected_a) == 4
    assert [x["record_id"] for x in selected_a] == [x["record_id"] for x in selected_b]
    assert all(len(x["record_hash"]) == 64 for x in selected_a)
    assert [x["record_hash"] for x in selected_a] == sorted(x["record_hash"] for x in selected_a)


def test_download_control_priority_prefers_raw_data():
    assert mod._download_priority("Raw Data") == 0
    assert mod._download_priority("DYNA ASCII") == 1
    assert mod._download_priority("raw archive") == 2
    assert mod._download_priority("Download") == 3
    assert mod._download_priority("Event metadata") is None


def test_event_ledger_fails_closed_on_stale_contract(tmp_path):
    path = tmp_path / "events.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=mod.EVENT_LEDGER_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "rank": 1,
            "event_id": "1",
            "query_contract": "event-specific;fromMagnitude=3",
            "status": "REJECT_COMPONENT_AUDIT",
        })
    with pytest.raises(ValueError, match="stale/unknown query contract"):
        mod._load_event_ledger(path)


def test_direct_entrypoint_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/audit_afad_tadas_candidate_events.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--prepare-only" in completed.stdout
    assert "--max-events" in completed.stdout
