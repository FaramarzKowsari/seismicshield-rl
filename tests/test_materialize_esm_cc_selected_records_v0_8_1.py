from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.materialize_esm_cc_selected_records_v0_8_1 import (
    EXPECTED_EVENTS,
    EXPECTED_RECORDS,
    load_selection,
)


def _write_selection(path: Path, license_text: str = "CC-BY4_0 (http://creativecommons.org/licenses/by/4.0/)") -> None:
    fieldnames = ["event_rank", "event_id", "record_rank", "record_id", "data_license"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event_rank in range(1, EXPECTED_EVENTS + 1):
            for record_rank in range(1, 5):
                writer.writerow({
                    "event_rank": event_rank,
                    "event_id": f"EVENT-{event_rank:03d}",
                    "record_rank": record_rank,
                    "record_id": f"R-{event_rank:03d}-{record_rank}",
                    "data_license": license_text,
                })


def test_v0_8_1_selection_loader_requires_34x4_explicit_cc(tmp_path: Path):
    path = tmp_path / "selection.csv"
    _write_selection(path)
    rows = load_selection(path)
    assert len(rows) == EXPECTED_RECORDS
    assert len({row["event_id"] for row in rows}) == EXPECTED_EVENTS


def test_v0_8_1_selection_loader_rejects_network_default_license(tmp_path: Path):
    path = tmp_path / "selection.csv"
    _write_selection(path, "D (network default license)")
    with pytest.raises(ValueError, match="explicit frozen CC license"):
        load_selection(path)


def test_direct_materializer_help_bootstraps_repository_root():
    result = subprocess.run(
        [sys.executable, "scripts/materialize_esm_cc_selected_records_v0_8_1.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "34x4 explicit-CC ESM selection" in result.stdout
