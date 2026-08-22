#!/usr/bin/env python3
"""Validate the frozen v0.8.2 statistical analysis contract without outcome data."""
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

from seismicshield_rl.confirmatory_analysis_v0_8_2 import (  # noqa: E402
    exact_sign_flip_pvalue,
    holm_adjust,
    hypervolume_3d,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return data


def validate(root: Path, contract_path: Path) -> tuple[dict, list[str]]:
    failures: list[str] = []
    contract = _load(contract_path)
    execution = _load(root / "open_science/confirmatory_execution_v0.8.2.yaml")
    freeze = _load(root / "open_science/confirmatory_freeze_v0.8.0.yaml")
    frozen_analysis = freeze.get("analysis") or {}

    if contract.get("version") != "v0.8.2":
        failures.append("analysis contract version must be v0.8.2")
    if contract.get("confirmatory_outcomes_inspected_before_this_freeze") is not False:
        failures.append("analysis contract must state no confirmatory outcome was inspected")

    hv = contract.get("pareto_hypervolume") or {}
    if hv.get("reference_point") != frozen_analysis.get("pareto_hypervolume_reference_point"):
        failures.append("analysis hypervolume reference point differs from numerical freeze")
    if hv.get("objective_vector") != ["normalized_cost", "MIDR_over_0.02", "PFA_g_over_1.0"]:
        failures.append("analysis objective vector mismatch")
    if hv.get("maximum_expected_points_per_method_world") != 9:
        failures.append("method-world front cardinality must be frozen at <=9 points")

    input_unit = contract.get("input_unit") or {}
    if input_unit.get("primary_confirmatory_worlds") != 768:
        failures.append("analysis must use 768 confirmatory worlds")
    if input_unit.get("earthquake_event_clusters") != 12 or input_unit.get("worlds_per_event") != 64:
        failures.append("analysis event/world hierarchy must be 12 x 64")
    if input_unit.get("failure_vector_retained") != frozen_analysis.get("fixed_failure_vector"):
        failures.append("analysis failure vector mismatch")

    slices = contract.get("cost_slices") or {}
    if slices.get("ceilings") != frozen_analysis.get("normalized_cost_ceilings"):
        failures.append("cost ceilings differ from numerical freeze")
    if slices.get("interpolation") != "none" or slices.get("extrapolation") != "none":
        failures.append("cost-slice analysis must remain discrete")

    h1 = contract.get("H1_pareto_performance") or {}
    expected_contrasts = ["MAPPO_vs_PPO", "MAPPO_vs_NSGA-II", "MAPPO_vs_IPPO"]
    if h1.get("contrasts") != expected_contrasts:
        failures.append("H1 primary contrast family mismatch")
    if h1.get("multiplicity_procedure") != "Holm" or float(h1.get("alpha", -1)) != 0.05:
        failures.append("H1 Holm/alpha mismatch")

    h2 = contract.get("H2_structural_response_tradeoff") or {}
    if h2.get("multiplicity_family_size") != 24:
        failures.append("H2 multiplicity family must contain 24 tests")
    if h2.get("multiplicity_procedure") != "Holm" or float(h2.get("alpha", -1)) != 0.05:
        failures.append("H2 Holm/alpha mismatch")

    resampling = contract.get("resampling") or {}
    if resampling.get("cluster_count") != 12:
        failures.append("resampling cluster count must be 12")
    if resampling.get("bootstrap_repetitions") != frozen_analysis.get("bootstrap_repetitions"):
        failures.append("bootstrap repetitions differ from numerical freeze")
    if resampling.get("bootstrap_seed") != 998035145:
        failures.append("bootstrap seed mismatch")
    if resampling.get("sign_flip_configurations") != frozen_analysis.get(
        "primary_paired_sign_flip_configurations"
    ):
        failures.append("sign-flip count differs from numerical freeze")
    if resampling.get("sign_flip_sidedness") != "two_sided_absolute_mean":
        failures.append("sign-flip sidedness is not frozen as two-sided")

    execution_ref = contract.get("execution_contract")
    if execution_ref != "open_science/confirmatory_execution_v0.8.2.yaml":
        failures.append("analysis contract does not reference execution v0.8.2")
    if (execution.get("pareto_and_cost_slice_rules") or {}).get("cost_ceilings") != slices.get("ceilings"):
        failures.append("execution and analysis cost ceilings disagree")

    # Public mathematical self-checks.
    if not np.isclose(hypervolume_3d([[0.0, 0.0, 0.0]], [1.0, 1.0, 1.0]), 1.0):
        failures.append("hypervolume self-check failed")
    if not np.isclose(
        hypervolume_3d([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5]], [1.0, 1.0, 1.0]),
        0.375,
    ):
        failures.append("hypervolume union self-check failed")
    if not np.isclose(exact_sign_flip_pvalue([1.0, 1.0]), 0.5):
        failures.append("exact sign-flip self-check failed")
    adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.04})
    if not (
        np.isclose(adjusted["a"], 0.03)
        and np.isclose(adjusted["b"], 0.06)
        and np.isclose(adjusted["c"], 0.06)
    ):
        failures.append("Holm self-check failed")

    evidence = {
        "status": "PASS" if not failures else "FAIL",
        "analysis_contract": str(contract_path.relative_to(root)),
        "analysis_contract_sha256": _sha256(contract_path),
        "confirmatory_outcome_inspected": False,
        "mathematical_self_checks": "PASS" if not failures else "FAIL",
    }
    return evidence, failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=root / "open_science/confirmatory_analysis_v0.8.2.yaml",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        evidence, failures = validate(root, args.contract)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        evidence, failures = {"status": "FAIL"}, [str(exc)]
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Evidence: {args.output}")
        print(f"Evidence SHA-256: {_sha256(args.output)}")
    print(f"Confirmatory analysis v0.8.2 validation: {evidence.get('status', 'FAIL')}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
