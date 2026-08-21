from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.finalize_esm_cc_selection_v0_8_1 import (
    EXPECTED_EVENTS,
    EXPECTED_QUEUE_EVENTS,
    EXPECTED_RECORDS,
    build_selection,
    explicit_cc_license,
    load_event_queue,
)
from scripts.ground_motion_manifest import ESM_SOURCE, sha_key


def _queue() -> list[dict[str, str]]:
    rows = []
    for rank in range(1, EXPECTED_QUEUE_EVENTS + 1):
        event_id = f"EVENT-{rank:03d}"
        rows.append({
            "rank": str(rank),
            "event_hash": sha_key("event", {"source": ESM_SOURCE, "event_id": event_id}),
            "source": ESM_SOURCE,
            "event_id": event_id,
        })
    return rows


def _record(event_id: str, index: int, license_text: str) -> dict[str, str]:
    record_id = f"{event_id}.REC{index:02d}.ASC"
    return {
        "source": ESM_SOURCE,
        "record_id": record_id,
        "record_hash_preview": sha_key(
            "record", {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id}
        ),
        "stream": "HNE" if index % 2 else "HNN",
        "network": "XX",
        "station_code": f"S{index:02d}",
        "location": "00",
        "data_license": license_text,
        "source_member_sha256": "a" * 64,
        "source_zip_sha256": "b" * 64,
        "source_request_url": f"https://esm-db.eu/esmws/eventdata/1/query?eventid={event_id}",
    }


def _inventory(clean_events: set[int]) -> dict[str, dict]:
    result = {}
    for rank in range(1, EXPECTED_QUEUE_EVENTS + 1):
        event_id = f"EVENT-{rank:03d}"
        license_text = (
            "CC-BY4_0 (http://creativecommons.org/licenses/by/4.0/)"
            if rank in clean_events
            else "U (unknown license)"
        )
        result[event_id] = {
            "event_id": event_id,
            "status": "COMPLETE_RECORD_INVENTORY",
            "waveform_errors": 0,
            "passing_records_hash_order_preview": [
                _record(event_id, index, license_text) for index in range(1, 6)
            ],
        }
    return result


def test_explicit_cc_allowlist_does_not_infer_d_or_u():
    assert explicit_cc_license("CC-BY3_0-IT (http://creativecommons.org/licenses/by/3.0/deed.en)")
    assert explicit_cc_license("CC-BY4_0 (http://creativecommons.org/licenses/by/4.0/)")
    assert not explicit_cc_license("D (network default license)")
    assert not explicit_cc_license("U (unknown license)")


def test_build_selection_freezes_34_events_and_136_records():
    clean = set(range(1, EXPECTED_EVENTS + 1))
    events, records = build_selection(_queue(), _inventory(clean))
    assert len(events) == EXPECTED_EVENTS
    assert len(records) == EXPECTED_RECORDS
    assert all(record["data_license"].startswith("CC-BY4_0") for record in records)
    assert {record["event_id"] for record in records} == {event["event_id"] for event in events}
    assert all(sum(r["event_id"] == event["event_id"] for r in records) == 4 for event in events)


def test_license_ineligible_event_is_skipped_without_reordering_salt():
    clean = set(range(2, EXPECTED_EVENTS + 2))
    events, records = build_selection(_queue(), _inventory(clean))
    assert events[0]["event_id"] == "EVENT-002"
    assert events[0]["source_queue_rank"] == "2"
    assert events[-1]["event_id"] == f"EVENT-{EXPECTED_EVENTS + 1:03d}"
    assert len(records) == EXPECTED_RECORDS


def test_build_selection_fails_closed_if_fewer_than_34_events_have_four_explicit_cc_records():
    clean = set(range(1, EXPECTED_EVENTS))
    with pytest.raises(ValueError, match="expected 34"):
        build_selection(_queue(), _inventory(clean))


def test_load_event_queue_requires_exact_63_canonical_hash_rows(tmp_path: Path):
    path = tmp_path / "queue.csv"
    rows = _queue()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "event_hash", "source", "event_id"])
        writer.writeheader()
        writer.writerows(rows)
    assert len(load_event_queue(path)) == EXPECTED_QUEUE_EVENTS

    rows[0]["event_hash"] = "0" * 64
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "event_hash", "source", "event_id"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="noncanonical event hash"):
        load_event_queue(path)


def test_direct_script_help_bootstraps_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/finalize_esm_cc_selection_v0_8_1.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "explicit-CC ESM selection" in result.stdout
