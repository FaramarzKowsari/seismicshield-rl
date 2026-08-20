from __future__ import annotations

import hashlib

import pytest

from scripts import build_esm_eligible_event_queue as mod


def _eligible(event_id: str, passing: int = 4):
    return {
        "event_id": event_id,
        "status": mod.ELIGIBLE_STATUS,
        "passing_horizontal_count": passing,
        "event_metadata": {
            "event_date_yyyymmdd": "20200101",
            "event_time_hhmmss": "010203",
            "event_latitude_degree": 40.0,
            "event_longitude_degree": 29.0,
            "event_depth_km": 10.0,
            "magnitude_w": 6.0,
            "magnitude_l": None,
        },
    }


def test_queue_uses_frozen_event_hash_formula_and_selects_exactly_40():
    rows = [_eligible(f"E{i:03d}") for i in range(45)]
    queue = mod.build_queue(rows, 40)
    assert len(queue) == 45
    assert sum(row["selected_preview"] for row in queue) == 40
    assert [row["rank"] for row in queue] == list(range(1, 46))
    expected = {
        row["event_id"]: hashlib.sha256(
            f"{mod.SALT}:event:{mod.ESM_SOURCE}:{row['event_id']}".encode()
        ).hexdigest()
        for row in rows
    }
    assert all(row["event_hash"] == expected[row["event_id"]] for row in queue)
    assert [row["event_hash"] for row in queue] == sorted(row["event_hash"] for row in queue)


def test_incomplete_event_fails_closed():
    rows = [_eligible(f"E{i:03d}") for i in range(40)]
    rows.append({"event_id": "ERR", "status": mod.INCOMPLETE_STATUS})
    with pytest.raises(ValueError, match="incomplete/error"):
        mod.build_queue(rows, 40)


def test_fewer_than_40_eligible_events_fails_closed():
    with pytest.raises(ValueError, match="are required"):
        mod.build_queue([_eligible(f"E{i:03d}") for i in range(39)], 40)


def test_eligible_status_requires_four_passing_horizontals():
    rows = [_eligible(f"E{i:03d}") for i in range(39)] + [_eligible("BAD", passing=3)]
    with pytest.raises(ValueError, match="fewer than four"):
        mod.build_queue(rows, 40)


def test_duplicate_event_id_fails_closed():
    rows = [_eligible(f"E{i:03d}") for i in range(40)] + [_eligible("E000")]
    with pytest.raises(ValueError, match="duplicate eligible ESM event_id"):
        mod.build_queue(rows, 40)
