#!/usr/bin/env python3
"""Validate the frozen confirmatory algorithm bundle on a public synthetic oracle only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seismicshield_rl.algorithms.confirmatory import (  # noqa: E402
    DesignContext,
    DesignSpace,
    ObjectiveRecord,
    run_nsga2,
    run_ppo_family,
    run_random_search,
)

EXPECTED_SEEDS = [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861]
EXPECTED_BUDGET = 51200
EXPECTED_METHODS = {"random_search", "nsga2", "ppo", "ippo", "mappo"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_problem() -> tuple[DesignSpace, DesignContext]:
    space = DesignSpace(3, 2, np.asarray([0.0, 50_000.0, 100_000.0], dtype=float))
    local = np.asarray(
        [
            [0.0, 1.00, 1.15, 0.80, 0.015, 0.55],
            [0.5, 1.05, 1.00, 1.00, 0.015, 0.55],
            [1.0, 0.95, 0.85, 0.70, 0.015, 0.55],
        ],
        dtype=np.float32,
    )
    target = np.asarray([100_000.0, 150_000.0, 50_000.0], dtype=float)

    def oracle(design) -> ObjectiveRecord:
        capacity = design.total_story_capacity_n.astype(float)
        scale = 200_000.0
        cost = float(np.sum(capacity) / (3.0 * scale))
        mismatch = (capacity - target) / scale
        midr_ratio = float(0.55 + np.mean(mismatch * mismatch))
        pfa_ratio = float(0.65 + 0.40 * np.mean(np.abs(mismatch)))
        vector = np.asarray([cost, midr_ratio, pfa_ratio], dtype=float)
        scalar = float(0.20 * cost + 0.45 * midr_ratio + 0.35 * pfa_ratio)
        return ObjectiveRecord(vector, scalar, True)

    return space, DesignContext(local, oracle, context_id="public-synthetic-oracle-v0.8.1")


def _result_signature(result) -> dict:
    return {
        "method": result.method,
        "evaluations": result.evaluations,
        "counts": result.best_design.counts.tolist(),
        "slip_force_n": result.best_design.slip_force_n.tolist(),
        "vector": result.best_record.vector.tolist(),
        "scalar": result.best_record.scalar,
        "pareto_size": len(result.pareto_records),
    }


def _same_result(left, right) -> bool:
    return (
        left.evaluations == right.evaluations
        and np.array_equal(left.best_design.counts, right.best_design.counts)
        and np.array_equal(left.best_design.slip_force_n, right.best_design.slip_force_n)
        and np.array_equal(left.best_record.vector, right.best_record.vector)
        and left.best_record.scalar == right.best_record.scalar
    )


def validate_contract(root: Path, bundle_path: Path) -> tuple[dict, list[str]]:
    failures: list[str] = []
    try:
        bundle = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return {}, [f"algorithm bundle cannot be read: {exc}"]
    if not isinstance(bundle, dict):
        return {}, ["algorithm bundle must be a YAML mapping"]

    if bundle.get("version") != "v0.8.1":
        failures.append("algorithm bundle version must be v0.8.1")
    if bundle.get("frozen_before_confirmatory_outcome_inspection") is not True:
        failures.append("algorithm bundle is not explicitly frozen before confirmatory inspection")
    boundary = bundle.get("scientific_boundary") or {}
    for key in (
        "confirmatory_data_permitted_for_training",
        "confirmatory_data_permitted_for_model_selection",
        "confirmatory_data_permitted_for_hyperparameter_tuning",
    ):
        if boundary.get(key) is not False:
            failures.append(f"scientific boundary {key} must be false")
    if boundary.get("model_selection_partition") != "validation":
        failures.append("model selection must be restricted to the validation partition")

    budget = bundle.get("budget") or {}
    if budget.get("completed_design_evaluations_per_stochastic_method_per_seed") != EXPECTED_BUDGET:
        failures.append("stochastic-method budget does not match preregistered 51200 evaluations")
    if budget.get("failed_simulation_consumes_budget") is not True:
        failures.append("failed simulations must consume budget")
    if bundle.get("seeds") != EXPECTED_SEEDS:
        failures.append("algorithm seed list does not match the preregistered seed ledger")
    methods = bundle.get("methods") or {}
    if set(methods) != EXPECTED_METHODS:
        failures.append("algorithm method set must be exactly random_search, nsga2, ppo, ippo, mappo")

    freeze_path = root / "open_science/confirmatory_freeze_v0.8.0.yaml"
    try:
        freeze = yaml.safe_load(freeze_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        failures.append(f"cannot read preregistered numerical freeze: {exc}")
        freeze = {}
    if (freeze.get("algorithms") or {}).get("primary_seeds") != EXPECTED_SEEDS:
        failures.append("repository numerical freeze no longer carries the expected primary seeds")
    if (freeze.get("budgets") or {}).get(
        "tier_1_completed_design_evaluations_per_stochastic_method_per_seed"
    ) != EXPECTED_BUDGET:
        failures.append("repository numerical freeze no longer carries the expected stochastic budget")

    validation = bundle.get("validation") or {}
    smoke_budget = validation.get("smoke_budget_per_method")
    if smoke_budget != 64:
        failures.append("public synthetic smoke budget must remain 64 evaluations per method")
    if validation.get("public_synthetic_oracle_only") is not True:
        failures.append("algorithm validation must use only the public synthetic oracle")
    if validation.get("confirmatory_waveform_used") is not False:
        failures.append("algorithm validation must explicitly prohibit confirmatory waveforms")

    evidence = {
        "status": "FAIL" if failures else "PENDING_SMOKE",
        "algorithm_bundle": str(bundle_path.relative_to(root)),
        "algorithm_bundle_sha256": _sha256(bundle_path),
        "confirmatory_waveform_used": False,
        "smoke": {},
    }
    return evidence, failures


def run_smoke(root: Path, bundle_path: Path) -> tuple[dict, list[str]]:
    evidence, failures = validate_contract(root, bundle_path)
    if failures:
        evidence["status"] = "FAIL"
        return evidence, failures

    bundle = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    smoke_budget = int(bundle["validation"]["smoke_budget_per_method"])
    seed = int(bundle["seeds"][0])
    space, context = _synthetic_problem()

    runners = {
        "random_search": lambda: run_random_search(
            space, context.evaluate, budget=smoke_budget, seed=seed
        ),
        "nsga2": lambda: run_nsga2(
            space,
            context.evaluate,
            budget=smoke_budget,
            seed=seed,
            population_size=16,
            crossover_probability=float(bundle["methods"]["nsga2"]["crossover_probability"]),
        ),
        "ppo": lambda: run_ppo_family(
            "ppo",
            space,
            [context],
            budget=smoke_budget,
            seed=seed,
            batch_design_evaluations=16,
            update_epochs=2,
            hidden_units=(32, 32),
        ),
        "ippo": lambda: run_ppo_family(
            "ippo",
            space,
            [context],
            budget=smoke_budget,
            seed=seed,
            batch_design_evaluations=16,
            update_epochs=2,
            hidden_units=(32, 32),
        ),
        "mappo": lambda: run_ppo_family(
            "mappo",
            space,
            [context],
            budget=smoke_budget,
            seed=seed,
            batch_design_evaluations=16,
            update_epochs=2,
            hidden_units=(32, 32),
        ),
    }

    for method, runner in runners.items():
        first = runner()
        second = runner()
        if first.evaluations != smoke_budget:
            failures.append(f"{method} did not consume exactly {smoke_budget} completed evaluations")
        if not _same_result(first, second):
            failures.append(f"{method} deterministic replay failed for seed {seed}")
        if not np.all(np.isfinite(first.best_record.vector)) or not np.isfinite(
            first.best_record.scalar
        ):
            failures.append(f"{method} produced non-finite objective values")
        if np.any(first.best_design.counts < 0) or np.any(
            first.best_design.counts > space.max_dampers_per_story
        ):
            failures.append(f"{method} produced an out-of-bounds damper count")
        if not np.all(np.isin(first.best_design.slip_force_n, space.slip_force_levels_n)):
            failures.append(f"{method} produced an out-of-grid slip force")
        if method == "nsga2" and not first.pareto_records:
            failures.append("nsga2 returned an empty Pareto archive")
        evidence["smoke"][method] = _result_signature(first)

    try:
        import torch

        evidence["torch_version"] = torch.__version__
    except ImportError:  # pragma: no cover
        evidence["torch_version"] = None
        failures.append("PyTorch is not installed for learned-method validation")
    evidence["numpy_version"] = np.__version__
    evidence["status"] = "PASS" if not failures else "FAIL"
    return evidence, failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    evidence, failures = run_smoke(root, args.bundle)
    if args.output is not None:
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Evidence: {args.output}")
        print(f"Evidence SHA-256: {_sha256(args.output)}")
    print(f"Confirmatory algorithm bundle validation: {evidence.get('status', 'FAIL')}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
