#!/usr/bin/env python3
"""Pilot-only local preflight for v0.8.2 runtime/integrity; never reads confirmatory records."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

from seismicshield_rl.execution_v0_8_2 import FixedObjectiveEvaluator  # noqa: E402
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion  # noqa: E402
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator  # noqa: E402
from seismicshield_rl.physics.base import DamperDesign  # noqa: E402
from seismicshield_rl.structural_worlds import (  # noqa: E402
    StructuralRealization,
    building_for_world,
    load_contract,
)

EXPECTED_GROUND_SHA = "0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b"
PRIVATE_DEFAULT = Path("data/private/esm/processed-selected-v0.8.1")
TIER1_PLANNED_CALLS = 2_780_992  # design training + validation + shared feature precompute.
TIER2_PRIMARY_AND_SUPPORT_CALLS = 39_168


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _private_index(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise RuntimeError(f"private processed directory is missing: {directory}")
    index: dict[str, Path] = {}
    for path in sorted(directory.glob("*.csv")):
        digest = _sha256(path)
        if digest in index:
            raise RuntimeError(f"duplicate processed SHA-256 in private directory: {digest}")
        index[digest] = path
    return index


def _verify_private_set(root: Path, private_dir: Path) -> tuple[list[dict[str, str]], dict[str, Path]]:
    manifest = root / "data/manifests/ground_motion_manifest.csv"
    if _sha256(manifest) != EXPECTED_GROUND_SHA:
        raise RuntimeError("public frozen ground-motion manifest SHA-256 mismatch")
    rows = _manifest_rows(manifest)
    if len(rows) != 136:
        raise RuntimeError(f"expected 136 frozen ground records, found {len(rows)}")
    index = _private_index(private_dir)
    missing = [row["processed_sha256"] for row in rows if row["processed_sha256"] not in index]
    if missing:
        raise RuntimeError(f"private processed set is incomplete: {len(missing)} frozen records are missing")
    return rows, index


def _state_from_row(row: dict[str, str]) -> tuple[int, StructuralRealization, float]:
    realization = StructuralRealization(
        realization_id=row["realization_id"],
        is_nominal=row["is_nominal"].lower() == "true",
        mass_scale=float(row["mass_scale"]),
        stiffness_scale=float(row["stiffness_scale"]),
        damping_ratio=float(row["damping_ratio"]),
        damper_capacity_scale=float(row["damper_capacity_scale"]),
    )
    return int(row["building_height_stories"]), realization, float(row["damper_capacity_scale"])


def _timed_evaluation(evaluator: FixedObjectiveEvaluator, design: DamperDesign) -> tuple[float, bool]:
    started = perf_counter()
    result = evaluator.evaluate(design)
    return perf_counter() - started, bool(result.converged)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, default=root / PRIVATE_DEFAULT)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "results/local/confirmatory_v0.8.2/preflight.json",
    )
    args = parser.parse_args()
    try:
        ground_rows, private_index = _verify_private_set(root, args.private_dir)
        # Preserve the already-frozen manifest order; the public manifest deliberately
        # contains no mutable event-rank/record-rank columns.
        pilot_records = [row for row in ground_rows if row["partition"] == "pilot"]
        if len(pilot_records) != 16:
            raise RuntimeError(f"pilot partition must contain 16 records, found {len(pilot_records)}")
        # Runtime-only fixture: one frozen pilot waveform; smallest and largest nominal buildings.
        record = pilot_records[0]
        motion_path = private_index[record["processed_sha256"]]
        motion = load_csv_ground_motion(motion_path, motion_id=record["record_id"], source="ESM-pilot")
        structural_rows = _manifest_rows(root / "data/manifests/structural_world_manifest.csv")
        fixtures: list[dict[str, str]] = []
        for height in (3, 20):
            matches = [
                row for row in structural_rows
                if row["partition"] == "pilot"
                and row["record_id"] == record["record_id"]
                and int(row["building_height_stories"]) == height
                and row["realization_id"] == "nominal"
            ]
            if len(matches) != 1:
                raise RuntimeError(f"expected one pilot nominal fixture for {height} stories")
            fixtures.append(matches[0])
        contract = load_contract(root / "open_science/structural_world_freeze_v0.8.1.yaml")
        designs = {
            "no_damper": lambda n: DamperDesign(np.zeros(n, dtype=int), np.zeros(n, dtype=float)),
            "uniform": lambda n: DamperDesign(
                np.ones(n, dtype=int), np.full(n, 100_000.0, dtype=float)
            ),
        }
        tier1_times: list[float] = []
        tier2_times: list[float] = []
        tier1_converged = 0
        tier2_converged = 0
        tier2_available = True
        tier2_error = None
        try:
            from seismicshield_rl.physics.opensees_backend import OpenSeesBackend
        except Exception as exc:  # pragma: no cover - workstation dependency check
            OpenSeesBackend = None
            tier2_available = False
            tier2_error = str(exc)

        for row in fixtures:
            height, realization, capacity_scale = _state_from_row(row)
            building = building_for_world(height, realization, contract)
            tier1 = ShearBuildingSimulator(building, damper_capacity_scale=capacity_scale)
            for design_factory in designs.values():
                design = design_factory(height)
                elapsed, converged = _timed_evaluation(
                    FixedObjectiveEvaluator(
                        tier1,
                        motion,
                        max_dampers_per_story=4,
                        max_slip_force_n=350_000.0,
                    ),
                    design,
                )
                tier1_times.append(elapsed)
                tier1_converged += int(converged)
                if OpenSeesBackend is not None:
                    tier2 = OpenSeesBackend(building, damper_capacity_scale=capacity_scale)
                    elapsed, converged = _timed_evaluation(
                        FixedObjectiveEvaluator(
                            tier2,
                            motion,
                            max_dampers_per_story=4,
                            max_slip_force_n=350_000.0,
                        ),
                        design,
                    )
                    tier2_times.append(elapsed)
                    tier2_converged += int(converged)

        tier1_mean = float(np.mean(tier1_times))
        tier2_mean = float(np.mean(tier2_times)) if tier2_times else None
        evidence = {
            "status": "PASS" if tier1_converged == len(tier1_times) and tier2_available and tier2_converged == len(tier2_times) else "BLOCKED",
            "confirmatory_record_read": False,
            "pilot_record_count_read": 1,
            "scientific_response_metrics_emitted": False,
            "private_frozen_records_verified": 136,
            "tier1_fixture_calls": len(tier1_times),
            "tier1_converged": tier1_converged,
            "tier1_mean_wall_clock_s": tier1_mean,
            "tier1_projected_sequential_hours": tier1_mean * TIER1_PLANNED_CALLS / 3600.0,
            "tier2_available": tier2_available,
            "tier2_error": tier2_error,
            "tier2_fixture_calls": len(tier2_times),
            "tier2_converged": tier2_converged,
            "tier2_mean_wall_clock_s": tier2_mean,
            "tier2_projected_sequential_hours": None if tier2_mean is None else tier2_mean * TIER2_PRIMARY_AND_SUPPORT_CALLS / 3600.0,
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Pilot-only runtime preflight: {evidence['status']}")
        print(f"Verified private frozen records: {evidence['private_frozen_records_verified']}")
        print(f"Tier-1 mean seconds/call: {tier1_mean:.6f}")
        print(f"Tier-1 projected sequential hours: {evidence['tier1_projected_sequential_hours']:.2f}")
        if tier2_mean is not None:
            print(f"Tier-2 mean seconds/call: {tier2_mean:.6f}")
            print(f"Tier-2 projected sequential hours: {evidence['tier2_projected_sequential_hours']:.2f}")
        else:
            print(f"Tier-2 unavailable: {tier2_error}")
        print(f"Evidence: {args.output}")
        return 0 if evidence["status"] == "PASS" else 2
    except Exception as exc:
        print(f"Pilot-only runtime preflight: BLOCKED\n- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
