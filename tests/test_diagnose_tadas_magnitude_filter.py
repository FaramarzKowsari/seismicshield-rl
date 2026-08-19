import subprocess
import sys

from scripts import diagnose_tadas_magnitude_filter as mod


def test_parse_magnitude_and_sub3_selection_preserve_queue_order():
    rows = [
        {"rank": "1", "event_id": "A", "magnitude": "3.1"},
        {"rank": "2", "event_id": "B", "magnitude": "2.9"},
        {"rank": "3", "event_id": "C", "magnitude": "2.5"},
    ]
    selected = mod.sub3_rows(rows)
    assert [row["event_id"] for row in selected] == ["B", "C"]
    assert mod.parse_magnitude(" 2.90 ") == 2.9


def test_requested_rank_must_be_known_and_below_three():
    rows = [
        {"rank": "1", "event_id": "A", "magnitude": ""},
        {"rank": "2", "event_id": "B", "magnitude": "3.0"},
        {"rank": "3", "event_id": "C", "magnitude": "2.7"},
    ]
    assert mod.sub3_rows(rows, 3)[0]["event_id"] == "C"
    for rank in (1, 2):
        try:
            mod.sub3_rows(rows, rank)
        except ValueError as exc:
            assert "below M3" in str(exc)
        else:
            raise AssertionError("non-testable requested rank must fail")


def test_non_numeric_queue_magnitude_fails_closed():
    try:
        mod.parse_magnitude("M2.5")
    except ValueError as exc:
        assert "non-numeric" in str(exc)
    else:
        raise AssertionError("non-numeric magnitude must fail")


def test_canonical_json_ignores_object_key_order_but_not_list_order():
    a = [{"b": 2, "a": 1}, {"x": 3}]
    b = [{"a": 1, "b": 2}, {"x": 3}]
    c = list(reversed(b))
    assert mod.canonical_json_bytes(a) == mod.canonical_json_bytes(b)
    assert mod.canonical_json_bytes(a) != mod.canonical_json_bytes(c)


def test_response_summary_reuses_frozen_prescreen_logic():
    threshold = mod.backend.base.MIN_PGA_CM_S2
    value = [
        {"eaEventId": 7, "stationCode": "A", "pga": threshold},
        {"eaEventId": 7, "stationCode": "B", "pga": threshold + 1},
    ]
    result = mod.response_summary(value, "7")
    assert result["row_count"] == 2
    assert result["unique_station_count"] == 2
    assert result["stations_at_or_above_threshold"] == 2
    assert result["status"] == "CANDIDATE_COMPONENT_AUDIT"
    assert len(result["canonical_json_sha256"]) == 64


def test_direct_entrypoint_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/diagnose_tadas_magnitude_filter.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--max-sub3-probes" in completed.stdout
    assert "--bootstrap-rank" in completed.stdout
