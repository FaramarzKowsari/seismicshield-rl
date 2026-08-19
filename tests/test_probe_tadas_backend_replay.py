import subprocess
import sys

from scripts.probe_tadas_backend_replay import build_backend_payload, response_shape


def _row():
    return {
        "event_id": "551067",
        "event_date_from_export": "20-02-2023  09:04",
    }


def test_backend_payload_matches_discovered_contract_and_exact_event_id():
    payload = build_backend_payload(_row(), pad_days=1)
    assert payload == {
        "fromMagnitude": 3,
        "startDate": "2023-02-19T00:00:00.000Z",
        "endDate": "2023-02-21T23:59:59.000Z",
        "fromLatitude": None,
        "toLatitude": None,
        "fromLongitude": None,
        "toLongitude": None,
        "country": None,
        "province": None,
        "district": None,
        "neighborhood": None,
        "eaEventId": "551067",
        "waveformId": 0,
    }


def test_backend_payload_rejects_bad_pad_and_blank_event_id():
    row = _row()
    try:
        build_backend_payload(row, pad_days=-1)
    except ValueError as exc:
        assert "pad_days" in str(exc)
    else:
        raise AssertionError("negative pad_days should fail")

    row["event_id"] = "  "
    try:
        build_backend_payload(row, pad_days=1)
    except ValueError as exc:
        assert "event_id" in str(exc)
    else:
        raise AssertionError("blank event_id should fail")


def test_response_shape_reports_list_and_dict_without_rewriting_body():
    assert response_shape([]) == {
        "top_level_type": "list",
        "length": 0,
        "first_item_type": None,
        "first_item_keys": [],
    }
    assert response_shape([{"b": 2, "a": 1}]) == {
        "top_level_type": "list",
        "length": 1,
        "first_item_type": "dict",
        "first_item_keys": ["a", "b"],
    }
    assert response_shape({"z": 1, "a": 2}) == {
        "top_level_type": "dict",
        "keys": ["a", "z"],
    }


def test_direct_entrypoint_help_runs_from_repo_root():
    completed = subprocess.run(
        [sys.executable, "scripts/probe_tadas_backend_replay.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--rank" in completed.stdout
    assert "--out" in completed.stdout
