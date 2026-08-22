from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from scripts.build_structural_world_manifest_v0_8_1 import COLUMNS, build
from scripts.validate_structural_world_manifest_v0_8_1 import validate
from seismicshield_rl.structural_worlds import (
    deterministic_lhs,
    load_contract,
    nominal_profiles,
    realizations_from_contract,
)


CONTRACT = Path("open_science/structural_world_freeze_v0.8.1.yaml")


def _ground_rows() -> list[dict[str, str]]:
    partitions = ["training"] * 52 + ["validation"] * 20 + ["pilot"] * 16 + ["confirmatory"] * 48
    return [
        {
            "source": "ESM",
            "event_id": f"event-{index // 4:02d}",
            "record_id": f"record-{index:03d}",
            "partition": partition,
        }
        for index, partition in enumerate(partitions)
    ]


def _write_ground(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "event_id", "record_id", "partition"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def test_sha256_lhs_uses_each_stratum_once_per_dimension():
    lhs = deterministic_lhs(24681357, 3)
    for values in lhs.values():
        strata = sorted(int(value * 3) for value in values)
        assert strata == [0, 1, 2]
        assert all(0.0 <= value < 1.0 for value in values)


def test_structural_realizations_are_nominal_plus_three_lhs():
    contract = load_contract(CONTRACT)
    rows = realizations_from_contract(contract)
    assert [row.realization_id for row in rows] == ["nominal", "lhs-1", "lhs-2", "lhs-3"]
    assert rows[0].is_nominal
    assert rows[0].mass_scale == 1.0
    assert rows[0].stiffness_scale == 1.0
    assert rows[0].damping_ratio == 0.05
    assert rows[0].damper_capacity_scale == 1.0


def test_nominal_profiles_preserve_frozen_end_ratios():
    contract = load_contract(CONTRACT)
    masses, stiffness = nominal_profiles(20, contract)
    assert masses.size == 20
    assert stiffness.size == 20
    assert np.isclose(masses[0], 200000.0)
    assert np.isclose(masses[-1] / masses[0], 0.90)
    assert np.isclose(stiffness[0], 180000000.0)
    assert np.isclose(stiffness[-1] / stiffness[0], 0.60)


def test_full_structural_world_grid_is_2176_with_768_confirmatory():
    contract = load_contract(CONTRACT)
    rows = build(_ground_rows(), contract)
    assert len(rows) == 2176
    assert len({row["world_id"] for row in rows}) == 2176
    assert sum(row["partition"] == "confirmatory" for row in rows) == 768
    assert {row["building_height_stories"] for row in rows} == {"3", "6", "10", "20"}


def test_validator_reconstructs_exact_manifest(tmp_path: Path):
    contract = load_contract(CONTRACT)
    ground_rows = _ground_rows()
    ground_path = tmp_path / "ground.csv"
    manifest_path = tmp_path / "worlds.csv"
    _write_ground(ground_path, ground_rows)
    rows = build(ground_rows, contract)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    assert validate(manifest_path, ground_manifest=ground_path, contract_path=CONTRACT) == []
