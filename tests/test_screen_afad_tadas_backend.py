from datetime import timedelta
import subprocess
import sys

from scripts import screen_afad_tadas_backend as mod


def _queue_row(event_id="551067"):
    return {"event_id": event_id, "event_date_from_export": "20-02-2023  09:04"}


def test_live_date_shift_is_inferred_and_reused_without_hardcoding_timezone():
    template = {
        "fromMagnitude": 3,
        "startDate": "2023-02-19T01:00:00.000Z",
        "endDate": "2023-02-22T00:59:59.000Z",
        "eaEventId": "551067",
        "waveformId": 0,
    }
    shift = mod.infer_date_serialization_shift(
        "19-02-2023 00:00:00", "21-02-2023 23:59:59", template
    )
    assert shift == timedelta(hours=1)
    payload = mod.build_payload_from_live_template(
        template, _queue_row("00456"), pad_days=1, shift=shift
    )
    assert payload["eaEventId"] == "00456"
    assert payload["startDate"] == "2023-02-19T01:00:00.000Z"
    assert payload["endDate"] == "2023-02-22T00:59:59.000Z"


def test_inconsistent_live_date_shift_fails_closed():
    template = {
        "startDate": "2023-02-19T01:00:00.000Z",
        "endDate": "2023-02-22T01:59:59.000Z",
    }
    try:
        mod.infer_date_serialization_shift(
            "19-02-2023 00:00:00", "21-02-2023 23:59:59", template
        )
    except ValueError as exc:
        assert "inconsistent" in str(exc)
    else:
        raise AssertionError("inconsistent live date serialization must fail")


def test_backend_summary_matches_frozen_station_threshold_logic():
    threshold = mod.base.MIN_PGA_CM_S2
    rows = [
        {"eaEventId": 551067, "stationCode": "A", "pga": threshold - 0.01},
        {"eaEventId": 551067, "stationCode": "B", "pga": threshold},
        {"eaEventId": 551067, "stationCode": "C", "pga": 775.395599103},
    ]
    result = mod.summarize_backend_json(rows, "551067")
    assert result["backend_row_count"] == 3
    assert result["unique_station_count"] == 3
    assert result["stations_at_or_above_threshold"] == 2
    assert result["max_summary_pga_cm_s2"] == 775.395599103
    assert result["status"] == "CANDIDATE_COMPONENT_AUDIT"


def test_backend_summary_rejects_duplicate_station_and_event_mismatch():
    duplicate = [
        {"eaEventId": 1, "stationCode": "A", "pga": 1},
        {"eaEventId": 1, "stationCode": "A", "pga": 2},
    ]
    try:
        mod.summarize_backend_json(duplicate, "1")
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate station must fail")

    try:
        mod.summarize_backend_json([{"eaEventId": 2, "stationCode": "A", "pga": 1}], "1")
    except ValueError as exc:
        assert "EventID mismatch" in str(exc)
    else:
        raise AssertionError("event mismatch must fail")


def test_ui_parity_allows_csv_rounding_but_not_classification_drift():
    summary = {
        "status": "CANDIDATE_COMPONENT_AUDIT",
        "backend_row_count": 99,
        "unique_station_count": 99,
        "stations_at_or_above_threshold": 7,
        "max_summary_pga_cm_s2": 775.395599103,
    }
    ui = {
        "status": "CANDIDATE_COMPONENT_AUDIT",
        "summary_row_count": "99",
        "unique_station_count": "99",
        "stations_at_or_above_threshold": "7",
        "max_summary_pga_cm_s2": "775.396",
    }
    mod.assert_ui_parity(summary, ui, tol=0.001)
    ui["stations_at_or_above_threshold"] = "6"
    try:
        mod.assert_ui_parity(summary, ui, tol=0.001)
    except RuntimeError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("classification input drift must fail")


def test_direct_entrypoint_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/screen_afad_tadas_backend.py", "--help"],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--bootstrap-rank" in completed.stdout
    assert "--ui-parity-ledger" in completed.stdout
