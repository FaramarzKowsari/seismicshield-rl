#!/usr/bin/env python3
"""Validate v0.8.2 confirmatory execution semantics without private/confirmatory data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import yaml

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

from seismicshield_rl.algorithms.confirmatory import DesignContext, DesignSpace, ObjectiveRecord  # noqa: E402
from seismicshield_rl.algorithms.execution_v0_8_2 import (  # noqa: E402
    run_scalar_ga_candidates,
    train_validation_selected_policy,
)
from seismicshield_rl.execution_v0_8_2 import (  # noqa: E402
    FAILURE_VECTOR,
    FixedObjectiveEvaluation,
    ValidationPanel,
    sha256_balanced_order,
)

EXPECTED_SEEDS = [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861]
EXPECTED_PARTITIONS = {"training": 52, "validation": 20, "pilot": 16, "confirmatory": 48}
EXPECTED_METHODS = ["random_search", "scalar_ga", "nsga2", "ppo", "ippo", "mappo"]
EXPECTED_GRID = [0.0, 50_000.0, 100_000.0, 200_000.0, 350_000.0]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return data


def _static_validation(root: Path, contract: dict) -> list[str]:
    failures: list[str] = []
    if contract.get("version") != "v0.8.2":
        failures.append("execution contract version must be v0.8.2")
    if contract.get("confirmatory_outcomes_inspected_before_this_freeze") is not False:
        failures.append("execution contract must state that no confirmatory outcome was inspected")
    if contract.get("parent_source_tag") != "confirmatory-v0.8.1-final":
        failures.append("execution contract parent source tag mismatch")

    freeze = _load_yaml(root / "open_science/confirmatory_freeze_v0.8.0.yaml")
    objective = contract.get("objective_contract") or {}
    analysis = freeze.get("analysis") or {}
    if objective.get("vector") != ["normalized_cost", "MIDR_over_0.02", "PFA_g_over_1.0"]:
        failures.append("execution objective vector is not the public OSF vector")
    if float(objective.get("midr_normalizer", -1)) != 0.02:
        failures.append("MIDR normalizer must be 0.02")
    if float(objective.get("pfa_g_normalizer", -1)) != 1.0:
        failures.append("PFA-g normalizer must be 1.0")
    if objective.get("pareto_hypervolume_reference_point") != analysis.get(
        "pareto_hypervolume_reference_point"
    ):
        failures.append("hypervolume reference point differs from numerical freeze")
    if objective.get("fixed_failure_vector") != analysis.get("fixed_failure_vector"):
        failures.append("failure vector differs from numerical freeze")

    design = contract.get("design_space") or {}
    smoke = _load_yaml(root / "configs/experiments/smoke.yaml")
    if design.get("max_dampers_per_story") != smoke.get("max_dampers_per_story"):
        failures.append("execution damper-count bound differs from the pre-existing public grid")
    observed_grid = [float(value) for value in design.get("slip_force_levels_n", [])]
    if observed_grid != [float(value) for value in smoke.get("slip_force_levels_n", [])]:
        failures.append("execution slip-force grid differs from the pre-existing public grid")
    if observed_grid != EXPECTED_GRID:
        failures.append("execution slip-force grid mismatch")

    ground_path = root / "data/manifests/ground_motion_manifest.csv"
    if not ground_path.is_file():
        failures.append("ground-motion manifest is missing")
    else:
        counts = {key: 0 for key in EXPECTED_PARTITIONS}
        with ground_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                partition = str(row.get("partition", ""))
                if partition in counts:
                    counts[partition] += 1
        if counts != EXPECTED_PARTITIONS:
            failures.append(f"ground partition counts mismatch: {counts}")

    structural_path = root / "data/manifests/structural_world_manifest.csv"
    if not structural_path.is_file():
        failures.append("structural-world manifest is missing")
    else:
        rows = list(csv.DictReader(structural_path.open("r", encoding="utf-8", newline="")))
        if len(rows) != 2176:
            failures.append(f"structural-world manifest must contain 2176 rows, found {len(rows)}")
        confirmatory = sum(row.get("partition") == "confirmatory" for row in rows)
        if confirmatory != 768:
            failures.append(f"confirmatory structural worlds must be 768, found {confirmatory}")
        states = {
            (row.get("building_height_stories"), row.get("realization_id")) for row in rows
        }
        if len(states) != 16:
            failures.append(f"structural-state count must be 16, found {len(states)}")

    budget = contract.get("training_budget") or {}
    frozen_budget = (freeze.get("budgets") or {}).get(
        "tier_1_completed_design_evaluations_per_stochastic_method_per_seed"
    )
    if budget.get("simulator_calls_per_method_per_seed") != frozen_budget or frozen_budget != 51200:
        failures.append("Tier-1 stochastic budget must remain 51200")
    if budget.get("calls_per_structural_state_for_nonpolicy_optimizers") != 3200:
        failures.append("nonpolicy per-state training budget must be 3200")
    if budget.get("learned_policy_calls_per_state_exactly") != 3200:
        failures.append("learned-policy per-state training count must be 3200")
    if list(budget.get("stochastic_methods") or []) != EXPECTED_METHODS:
        failures.append("v0.8.2 stochastic method set mismatch")

    old_bundle = _load_yaml(root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml")
    if old_bundle.get("seeds") != EXPECTED_SEEDS:
        failures.append("v0.8.1 algorithm seed ledger changed")
    if (freeze.get("algorithms") or {}).get("primary_seeds") != EXPECTED_SEEDS:
        failures.append("numerical freeze seed ledger changed")

    validation = contract.get("validation_selection") or {}
    learned = validation.get("learned_methods") or {}
    checkpoints = learned.get("checkpoints_at_training_calls") or []
    if checkpoints != list(range(5120, 51201, 5120)):
        failures.append("learned checkpoint schedule mismatch")
    if learned.get("calls_per_checkpoint") != 320 or learned.get(
        "total_validation_calls_per_seed_per_learned_method"
    ) != 3200:
        failures.append("learned validation call accounting mismatch")
    nonpolicy = validation.get("nonpolicy_optimizers") or {}
    if nonpolicy.get("candidate_pool_per_seed_per_structural_state") != 32:
        failures.append("nonpolicy candidate pool must be 32")
    if nonpolicy.get("validation_calls_per_seed_per_structural_state") != 640:
        failures.append("nonpolicy validation calls per state must be 640")
    if nonpolicy.get("total_validation_calls_per_seed_per_nonpolicy_method") != 10240:
        failures.append("nonpolicy total validation call accounting mismatch")

    confirm = contract.get("confirmatory_execution") or {}
    if confirm.get("Tier2_calls_per_seeded_method") != 6144:
        failures.append("Tier-2 calls per seeded method must be 6144")
    maximum = (freeze.get("budgets") or {}).get("maximum_tier_2_openseespy_evaluations")
    if int(confirm.get("maximum_seeded_method_Tier2_calls_total", 10**9)) > int(maximum):
        failures.append("planned seeded Tier-2 workload exceeds preregistered ceiling")

    inference = contract.get("primary_event_level_inference") or {}
    if inference.get("confirmatory_event_clusters") != 12:
        failures.append("event-cluster count must be 12")
    if inference.get("cluster_bootstrap_repetitions") != analysis.get("bootstrap_repetitions"):
        failures.append("bootstrap repetition count differs from numerical freeze")
    if inference.get("exact_event_level_sign_flips") != analysis.get(
        "primary_paired_sign_flip_configurations"
    ):
        failures.append("sign-flip count differs from numerical freeze")
    if float(inference.get("alpha", -1)) != float(analysis.get("primary_alpha", -2)):
        failures.append("primary alpha differs from numerical freeze")
    if inference.get("multiplicity") != (analysis.get("multiplicity") or {}).get("procedure"):
        failures.append("multiplicity procedure differs from numerical freeze")
    return failures


def _synthetic_oracle(design) -> ObjectiveRecord:
    capacity = design.total_story_capacity_n.astype(float)
    target = np.linspace(50_000.0, 150_000.0, capacity.size)
    mismatch = (capacity - target) / 350_000.0
    cost = float(np.mean(capacity) / 1_400_000.0)
    vector = np.asarray(
        [cost, 0.6 + np.mean(mismatch * mismatch), 0.8 + 0.25 * np.mean(np.abs(mismatch))],
        dtype=float,
    )
    return ObjectiveRecord(vector, float(np.asarray([0.2, 0.45, 0.35]) @ vector), True)


class _ValidationEvaluator:
    def evaluate(self, design):
        record = _synthetic_oracle(design)
        return FixedObjectiveEvaluation(
            cost=float(record.vector[0]),
            midr=0.02 * float(record.vector[1]),
            pfa_g=float(record.vector[2]),
            vector=record.vector,
            scalar=record.scalar,
            converged=True,
            status="valid_converged",
            max_displacement_m=0.01,
            dissipated_energy_j=1.0,
        )


def _context(n: int, context_id: str) -> DesignContext:
    local = np.zeros((n, 6), dtype=np.float32)
    local[:, 0] = np.linspace(0.0, 1.0, n)
    local[:, 1:3] = 1.0
    local[:, 3] = np.linspace(0.4, 1.0, n)
    local[:, 4] = 0.015
    local[:, 5] = 0.55
    return DesignContext(local, _synthetic_oracle, context_id=context_id)


def _public_smoke() -> tuple[dict, list[str]]:
    failures: list[str] = []
    evidence: dict = {"confirmatory_waveform_used": False, "smoke": {}}
    space = DesignSpace(6, 4, np.asarray(EXPECTED_GRID, dtype=float))

    first = run_scalar_ga_candidates(space, _synthetic_oracle, budget=64, seed=1103, population_size=16)
    replay = run_scalar_ga_candidates(space, _synthetic_oracle, budget=64, seed=1103, population_size=16)
    if first.evaluations != 64:
        failures.append("scalar GA did not consume exact public smoke budget")
    if not np.array_equal(first.designs[0].counts, replay.designs[0].counts) or not np.array_equal(
        first.designs[0].slip_force_n, replay.designs[0].slip_force_n
    ):
        failures.append("scalar GA deterministic replay failed")
    evidence["smoke"]["scalar_ga"] = {
        "evaluations": first.evaluations,
        "retained_population": len(first.designs),
    }

    try:
        import torch
        evidence["torch_version"] = torch.__version__
    except ImportError:
        failures.append("PyTorch is required for v0.8.2 learned-policy validation")
        evidence["status"] = "FAIL"
        return evidence, failures

    contexts = [_context(3, "3-nominal"), _context(6, "6-nominal")]
    panels = [
        ValidationPanel(
            context.context_id,
            context.local_features,
            {"v1": _ValidationEvaluator(), "v2": _ValidationEvaluator()},
        )
        for context in contexts
    ]
    for method in ("ppo", "ippo", "mappo"):
        first_policy = train_validation_selected_policy(
            method,
            space,
            contexts,
            panels,
            budget=32,
            seed=1103,
            checkpoint_calls=[16, 32],
            batch_design_evaluations=8,
            update_epochs=1,
            hidden_units=(16, 16),
        )
        replay_policy = train_validation_selected_policy(
            method,
            space,
            contexts,
            panels,
            budget=32,
            seed=1103,
            checkpoint_calls=[16, 32],
            batch_design_evaluations=8,
            update_epochs=1,
            hidden_units=(16, 16),
        )
        first_design = first_policy.checkpoint.design(contexts[0].local_features)
        replay_design = replay_policy.checkpoint.design(contexts[0].local_features)
        if first_policy.training_evaluations != 32 or first_policy.validation_evaluations != 8:
            failures.append(f"{method} smoke call accounting failed")
        if first_policy.checkpoint.training_call not in {16, 32}:
            failures.append(f"{method} selected a checkpoint outside the frozen smoke schedule")
        if not np.array_equal(first_design.counts, replay_design.counts) or not np.array_equal(
            first_design.slip_force_n, replay_design.slip_force_n
        ):
            failures.append(f"{method} validation-selected policy replay failed")
        evidence["smoke"][method] = {
            "training_evaluations": first_policy.training_evaluations,
            "validation_evaluations": first_policy.validation_evaluations,
            "selected_checkpoint": first_policy.checkpoint.training_call,
            "three_story_action_count": first_design.counts.tolist(),
        }

    cycle = sha256_balanced_order(
        ["s01", "s02", "s03", "s04"], seed=1103, namespace="execution-smoke", cycle_index=0
    )
    if sorted(cycle) != ["s01", "s02", "s03", "s04"]:
        failures.append("SHA-256 balanced schedule failed its one-per-cycle invariant")
    if not np.array_equal(FAILURE_VECTOR, np.asarray([1.05, 5.0, 5.0])):
        failures.append("runtime fixed failure vector changed")
    evidence["numpy_version"] = np.__version__
    evidence["status"] = "PASS" if not failures else "FAIL"
    return evidence, failures


def validate(root: Path, contract_path: Path) -> tuple[dict, list[str]]:
    try:
        contract = _load_yaml(contract_path)
        failures = _static_validation(root, contract)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"status": "FAIL"}, [str(exc)]
    smoke, smoke_failures = _public_smoke()
    failures.extend(smoke_failures)
    evidence = {
        "status": "PASS" if not failures else "FAIL",
        "execution_contract": str(contract_path.relative_to(root)),
        "execution_contract_sha256": _sha256(contract_path),
        "confirmatory_waveform_used": False,
        "confirmatory_outcome_inspected": False,
        "static_contract_checks": "PASS" if not failures[: len(failures) - len(smoke_failures)] else "FAIL",
        **{key: value for key, value in smoke.items() if key != "status"},
    }
    return evidence, failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=root / "open_science/confirmatory_execution_v0.8.2.yaml",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    evidence, failures = validate(root, args.contract)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Evidence: {args.output}")
        print(f"Evidence SHA-256: {_sha256(args.output)}")
    print(f"Confirmatory execution v0.8.2 validation: {evidence.get('status', 'FAIL')}")
    for failure in failures:
        print(f"- {failure}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
