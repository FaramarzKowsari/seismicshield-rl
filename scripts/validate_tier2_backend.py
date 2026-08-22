#!/usr/bin/env python3
"""Validate the Tier-2 OpenSees backend without touching confirmatory records."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import yaml

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

from seismicshield_rl.physics.base import DamperDesign  # noqa: E402
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion  # noqa: E402
from seismicshield_rl.physics.opensees_backend import OpenSeesBackend  # noqa: E402
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator  # noqa: E402
from seismicshield_rl.structural_worlds import (  # noqa: E402
    building_for_world,
    load_contract,
    realizations_from_contract,
)


DEFAULT_VALIDATION = Path("open_science/tier2_validation_contract_v0.8.1.yaml")


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-15)


def run_validation(root: Path, validation_path: Path) -> tuple[dict, list[str]]:
    contract = yaml.safe_load(validation_path.read_text(encoding="utf-8"))
    structural = load_contract(root / contract["validation_fixture"]["structural_contract"])
    nominal = realizations_from_contract(structural)[0]
    height = int(contract["validation_fixture"]["building_height_stories"])
    building = building_for_world(height, nominal, structural)
    ground = load_csv_ground_motion(
        root / contract["validation_fixture"]["ground_motion"],
        motion_id="tier2-public-synthetic-validation",
        source="public-synthetic-fixture",
    )
    zero_design = DamperDesign(
        counts=np.zeros(height, dtype=int),
        slip_force_n=np.zeros(height, dtype=float),
    )

    tier1 = ShearBuildingSimulator(building, max_substep_s=0.0025).simulate(zero_design, ground)
    baseline_step = float(contract["acceptance"]["timestep_sensitivity"]["baseline_max_substep_s"])
    fine_step = float(contract["acceptance"]["timestep_sensitivity"]["fine_max_substep_s"])
    tier2 = OpenSeesBackend(building, max_substep_s=baseline_step).simulate(zero_design, ground)
    replay = OpenSeesBackend(building, max_substep_s=baseline_step).simulate(zero_design, ground)
    fine = OpenSeesBackend(building, max_substep_s=fine_step).simulate(zero_design, ground)

    failures: list[str] = []
    parity_limits = contract["acceptance"]["no_damper_tier1_vs_tier2_relative_tolerance"]
    parity = {}
    for metric in ("midr", "pfa_g", "max_displacement_m"):
        difference = _relative_difference(tier1.metrics[metric], tier2.metrics[metric])
        parity[metric] = difference
        if difference > float(parity_limits[metric]):
            failures.append(
                f"Tier-1/Tier-2 {metric} relative difference {difference:.6g} exceeds {parity_limits[metric]}"
            )

    if not tier2.converged or not replay.converged or not fine.converged:
        failures.append("one or more no-damper Tier-2 validation runs did not converge")

    replay_max = max(
        float(np.nanmax(np.abs(tier2.displacement_m - replay.displacement_m))),
        float(np.nanmax(np.abs(tier2.velocity_mps - replay.velocity_mps))),
        float(np.nanmax(np.abs(tier2.relative_accel_mps2 - replay.relative_accel_mps2))),
    )
    replay_limit = float(contract["acceptance"]["deterministic_replay_max_absolute_difference"])
    if replay_max > replay_limit:
        failures.append(f"deterministic replay difference {replay_max:.6g} exceeds {replay_limit}")

    sensitivity_limits = contract["acceptance"]["timestep_sensitivity"]["maximum_relative_change"]
    sensitivity = {}
    for metric in ("midr", "pfa_g"):
        difference = _relative_difference(tier2.metrics[metric], fine.metrics[metric])
        sensitivity[metric] = difference
        if difference > float(sensitivity_limits[metric]):
            failures.append(
                f"Tier-2 timestep sensitivity for {metric} {difference:.6g} exceeds {sensitivity_limits[metric]}"
            )

    damper_cfg = contract["acceptance"]["coulomb_damper"]
    count = int(damper_cfg["count_per_story"])
    slip_force = float(damper_cfg["slip_force_n"])
    damper_design = DamperDesign(
        counts=np.full(height, count, dtype=int),
        slip_force_n=np.full(height, slip_force, dtype=float),
    )
    damped = OpenSeesBackend(building, max_substep_s=baseline_step).simulate(damper_design, ground)
    capacity = count * slip_force
    maximum_force = float(np.nanmax(np.abs(damped.damper_force_n)))
    force_ratio = maximum_force / capacity if capacity > 0 else 0.0
    if not damped.converged:
        failures.append("Coulomb-damper Tier-2 validation run did not converge")
    if force_ratio > float(damper_cfg["maximum_force_ratio_to_capacity"]):
        failures.append(
            f"Coulomb-damper force ratio {force_ratio:.6g} exceeds frozen capacity ratio"
        )
    if bool(damper_cfg["energy_dissipation_must_be_positive"]) and not (
        damped.metrics["dissipated_energy_j"] > 0.0
    ):
        failures.append("Coulomb-damper dissipated energy is not positive")

    absolute_identity = float(
        np.nanmax(
            np.abs(
                tier2.absolute_accel_mps2
                - tier2.relative_accel_mps2
                - ground.accel_mps2[:, None]
            )
        )
    )
    if absolute_identity > 1e-12:
        failures.append("absolute acceleration reconstruction identity failed")

    try:
        import openseespy.opensees as ops

        opensees_version = str(ops.version())
    except Exception:
        opensees_version = "unknown"

    evidence = {
        "status": "PASS" if not failures else "FAIL",
        "validation_contract": str(validation_path.relative_to(root)),
        "validation_contract_sha256": hashlib.sha256(validation_path.read_bytes()).hexdigest(),
        "structural_contract_sha256": hashlib.sha256(
            (root / contract["validation_fixture"]["structural_contract"]).read_bytes()
        ).hexdigest(),
        "opensees_version": opensees_version,
        "ground_motion": contract["validation_fixture"]["ground_motion"],
        "confirmatory_ground_motion_used": False,
        "tier1_tier2_relative_difference": parity,
        "deterministic_replay_max_absolute_difference": replay_max,
        "timestep_relative_change": sensitivity,
        "coulomb_damper_maximum_force_ratio": force_ratio,
        "coulomb_damper_dissipated_energy_j": damped.metrics["dissipated_energy_j"],
        "absolute_acceleration_identity_max_error": absolute_identity,
        "failures": failures,
    }
    return evidence, failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=root / DEFAULT_VALIDATION)
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "results/local/tier2/tier2_validation_v0.8.1.json",
    )
    args = parser.parse_args()
    try:
        evidence, failures = run_validation(root, args.contract)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print("Tier-2 validation: FAIL")
        print(f"- {exc}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"Tier-2 validation: {evidence['status']}")
    print(f"OpenSees version: {evidence['opensees_version']}")
    print(f"Evidence: {args.output}")
    print(f"Evidence SHA-256: {digest}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
