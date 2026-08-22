#!/usr/bin/env python3
"""Build a compact, outcome-free execution-shard ledger from frozen v0.8.2 contracts.

The planner does not read waveform bytes, train a model, select a design, or run a structural
simulation. It verifies the authoritative immutable gate at the exact scientific tag, verifies
public frozen contracts/manifests, and groups the preregistered calls into atomic orchestration
units. In particular, learned-policy training is never split by structural state because the
frozen contract requires one shared policy budget across all 16 states.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import yaml

EXPECTED_SCIENTIFIC_TAG = "confirmatory-v0.8.2-final"
EXPECTED_SCIENTIFIC_COMMIT = "cecd3b6c27b5deb6cb6be7ddc478cfc407a45644"
EXPECTED_EXECUTION_SHA256 = "4be2acca57915ff6954a82dfb03bc5adc647bf1e9594fd01042c7be2af87dd50"
EXPECTED_STRUCTURAL_MANIFEST_SHA256 = "c4fa4d4ee203bbdb5475bd55140fe2c24246db3254a0f099b7535d4f23a8248f"
EXPECTED_ALGORITHM_SEEDS = [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861]
EXPECTED_TIER1_CALLS = 2_780_992
EXPECTED_TIER2_CALLS = 39_168
EXPECTED_STATES = 16
FROZEN_GATE_RELATIVE = "open_science/confirmatory_gate_v0.8.0.yaml"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return data


def _git_text(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise ValueError(detail)
    return result.stdout.strip()


def _frozen_python_env(worktree: Path) -> dict[str, str]:
    """Force subprocess package imports to resolve from the immutable worktree only."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str((worktree / "src").resolve())
    return env


def validate_immutable_scientific_gate(root: Path) -> str:
    """Run the frozen gate checker inside a detached worktree of the exact source tag."""
    try:
        resolved = _git_text(
            root, "rev-parse", "--verify", f"refs/tags/{EXPECTED_SCIENTIFIC_TAG}^{{commit}}"
        )
    except ValueError as exc:
        raise ValueError(
            f"required immutable source tag {EXPECTED_SCIENTIFIC_TAG!r} cannot be resolved: {exc}"
        ) from exc
    if resolved != EXPECTED_SCIENTIFIC_COMMIT:
        raise ValueError(
            f"immutable source tag moved: expected {EXPECTED_SCIENTIFIC_COMMIT}, found {resolved}"
        )

    frozen_gate = subprocess.run(
        ["git", "show", f"refs/tags/{EXPECTED_SCIENTIFIC_TAG}:{FROZEN_GATE_RELATIVE}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if frozen_gate.returncode:
        raise ValueError("cannot read the gate file from the immutable scientific tag")
    current_gate = root / FROZEN_GATE_RELATIVE
    if not current_gate.is_file() or current_gate.read_bytes() != frozen_gate.stdout:
        raise ValueError(
            "current orchestration checkout does not contain the exact gate bytes frozen at "
            f"{EXPECTED_SCIENTIFIC_TAG}"
        )

    with tempfile.TemporaryDirectory(prefix="seismicshield-gate-") as temp_name:
        worktree = Path(temp_name)
        added = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                "--force",
                str(worktree),
                EXPECTED_SCIENTIFIC_TAG,
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if added.returncode:
            detail = added.stderr.strip() or added.stdout.strip()
            raise ValueError(f"cannot create immutable gate validation worktree: {detail}")
        try:
            if _git_text(worktree, "rev-parse", "HEAD") != EXPECTED_SCIENTIFIC_COMMIT:
                raise ValueError("immutable gate validation worktree resolved to the wrong commit")
            frozen_env = _frozen_python_env(worktree)
            module_probe = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import pathlib, seismicshield_rl.structural_worlds as m; "
                    "print(pathlib.Path(m.__file__).resolve())",
                ],
                cwd=worktree,
                env=frozen_env,
                text=True,
                capture_output=True,
                check=False,
            )
            if module_probe.returncode:
                detail = module_probe.stderr.strip() or module_probe.stdout.strip()
                raise ValueError(f"cannot import frozen scientific package: {detail}")
            module_path = Path(module_probe.stdout.strip()).resolve()
            frozen_src = (worktree / "src").resolve()
            try:
                module_path.relative_to(frozen_src)
            except ValueError as exc:
                raise ValueError(
                    "frozen gate checker package isolation failed: "
                    f"seismicshield_rl resolved to {module_path}, outside {frozen_src}"
                ) from exc
            gate_check = subprocess.run(
                [sys.executable, "scripts/check_confirmatory_gate.py"],
                cwd=worktree,
                env=frozen_env,
                text=True,
                capture_output=True,
                check=False,
            )
            if gate_check.returncode:
                output = "\n".join(
                    part.strip() for part in (gate_check.stdout, gate_check.stderr) if part.strip()
                )
                raise ValueError(f"authoritative frozen confirmatory gate is not PASS:\n{output}")
            if "Confirmatory gate: PASS" not in gate_check.stdout:
                raise ValueError("frozen gate checker returned success without an explicit PASS marker")
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
    return resolved


def frozen_algorithm_seeds(seed_doc: dict[str, Any]) -> list[int]:
    """Return the exact preregistered algorithm seed list or fail closed."""
    observed = seed_doc.get("algorithm_seeds")
    if observed != EXPECTED_ALGORITHM_SEEDS:
        raise ValueError(
            "algorithm seed ledger differs from the exact preregistered values: "
            f"expected {EXPECTED_ALGORITHM_SEEDS!r}, found {observed!r}"
        )
    return list(EXPECTED_ALGORITHM_SEEDS)


def _state_sort_key(state: tuple[int, str]) -> tuple[int, int, str]:
    height, realization = state
    if realization == "nominal":
        rank = 0
    elif realization.startswith("lhs-") and realization[4:].isdigit():
        rank = int(realization[4:])
    else:
        rank = 10_000
    return height, rank, realization


def load_structural_states(path: Path, expected_partition_counts: dict[str, int]) -> list[str]:
    if sha256_path(path) != EXPECTED_STRUCTURAL_MANIFEST_SHA256:
        raise ValueError("structural-world manifest SHA-256 mismatch")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    states: set[tuple[int, str]] = set()
    counts: Counter[tuple[str, tuple[int, str]]] = Counter()
    for row in rows:
        state = (int(row["building_height_stories"]), row["realization_id"].strip())
        partition = row["partition"].strip()
        states.add(state)
        counts[(partition, state)] += 1
    if len(states) != EXPECTED_STATES:
        raise ValueError(f"expected {EXPECTED_STATES} structural states, found {len(states)}")
    for state in states:
        for partition, expected in expected_partition_counts.items():
            observed = counts[(partition, state)]
            if observed != expected:
                raise ValueError(
                    f"structural manifest count mismatch for {partition}/{state}: "
                    f"expected {expected}, found {observed}"
                )
    return [
        f"{height}:{realization}"
        for height, realization in sorted(states, key=_state_sort_key)
    ]


def make_shard(**fields: Any) -> dict[str, Any]:
    identity = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {"shard_id": hashlib.sha256(identity.encode()).hexdigest()[:24], **fields}


def build_plan(root: Path) -> dict[str, Any]:
    scientific_commit = validate_immutable_scientific_gate(root)
    contract_path = root / "open_science/confirmatory_execution_v0.8.2.yaml"
    if sha256_path(contract_path) != EXPECTED_EXECUTION_SHA256:
        raise ValueError("confirmatory execution contract SHA-256 mismatch")
    contract = load_yaml(contract_path)
    seeds_doc = load_yaml(root / "open_science/seed_ledger_v0.8.0.yaml")
    seeds = frozen_algorithm_seeds(seeds_doc)

    partitions = contract.get("partitions") or {}
    partition_counts = {
        "training": int(partitions["training_records"]),
        "validation": int(partitions["validation_records"]),
        "pilot": int(partitions["pilot_records"]),
        "confirmatory": int(partitions["confirmatory_records"]),
    }
    states = load_structural_states(
        root / "data/manifests/structural_world_manifest.csv", partition_counts
    )

    budget = contract.get("training_budget") or {}
    validation = contract.get("validation_selection") or {}
    nonpolicy_cfg = validation.get("nonpolicy_optimizers") or {}
    learned_cfg = validation.get("learned_methods") or {}
    methods_cfg = contract.get("methods") or {}
    confirm = contract.get("confirmatory_execution") or {}

    stochastic = list(budget.get("stochastic_methods") or [])
    required = list(methods_cfg.get("stochastic_required") or [])
    if stochastic != required:
        raise ValueError("training and required stochastic method ordering differs")
    nonpolicy = list((nonpolicy_cfg.get("candidate_pool_source") or {}).keys())
    learned = [method for method in stochastic if method not in nonpolicy]
    if nonpolicy != ["random_search", "scalar_ga", "nsga2"]:
        raise ValueError(f"unexpected nonpolicy method set/order: {nonpolicy}")
    if learned != ["ppo", "ippo", "mappo"]:
        raise ValueError(f"unexpected learned method set/order: {learned}")
    support = list(methods_cfg.get("deterministic_support") or [])
    if support != ["no_damper", "uniform_allocation", "drift_proportional_heuristic"]:
        raise ValueError(f"unexpected deterministic support methods: {support}")

    training_records = partition_counts["training"]
    validation_records = partition_counts["validation"]
    confirmatory_records = partition_counts["confirmatory"]
    calls_per_state = int(budget["calls_per_structural_state_for_nonpolicy_optimizers"])
    learned_budget = int(budget["simulator_calls_per_method_per_seed"])
    learned_calls_per_state = int(budget["learned_policy_calls_per_state_exactly"])
    nonpolicy_validation_calls = int(
        nonpolicy_cfg["validation_calls_per_seed_per_structural_state"]
    )
    learned_validation_calls = int(
        learned_cfg["total_validation_calls_per_seed_per_learned_method"]
    )
    tier2_per_method = int(confirm["Tier2_calls_per_seeded_method"])

    if calls_per_state * len(states) != learned_budget:
        raise ValueError("nonpolicy per-state training calls do not reproduce the frozen budget")
    if learned_calls_per_state * len(states) != learned_budget:
        raise ValueError("learned per-state accounting does not reproduce the frozen shared budget")
    if nonpolicy_validation_calls != (
        int(nonpolicy_cfg["candidate_pool_per_seed_per_structural_state"])
        * validation_records
    ):
        raise ValueError("nonpolicy validation accounting mismatch")
    if learned_validation_calls != (
        len(learned_cfg["checkpoints_at_training_calls"])
        * int(learned_cfg["calls_per_checkpoint"])
    ):
        raise ValueError("learned checkpoint validation accounting mismatch")
    calls_per_seeded_tier2_shard = len(states) * confirmatory_records
    if calls_per_seeded_tier2_shard * len(seeds) != tier2_per_method:
        raise ValueError("Tier-2 seeded method accounting mismatch")

    shards: list[dict[str, Any]] = []

    for state in states:
        shards.append(
            make_shard(
                phase="tier1_feature_precompute",
                backend="Tier1",
                partition="training",
                method="shared_undamped_feature",
                seed=None,
                structural_state_id=state,
                calls=training_records,
                atomic_reason="complete_training_only_state_descriptor",
            )
        )

    for method in nonpolicy:
        for seed in seeds:
            for state in states:
                shards.append(
                    make_shard(
                        phase="tier1_training_nonpolicy",
                        backend="Tier1",
                        partition="training",
                        method=method,
                        seed=seed,
                        structural_state_id=state,
                        calls=calls_per_state,
                        atomic_reason="one_frozen_optimizer_run_for_one_structural_state",
                    )
                )

    # Learned policies MUST remain one atomic method×seed training job across all 16 states.
    for method in learned:
        for seed in seeds:
            shards.append(
                make_shard(
                    phase="tier1_training_learned",
                    backend="Tier1",
                    partition="training",
                    method=method,
                    seed=seed,
                    structural_state_id=None,
                    structural_states=len(states),
                    calls=learned_budget,
                    calls_per_state=learned_calls_per_state,
                    atomic_reason="shared_policy_budget_across_all_16_structural_states",
                )
            )

    for method in nonpolicy:
        for seed in seeds:
            for state in states:
                shards.append(
                    make_shard(
                        phase="tier1_validation_nonpolicy",
                        backend="Tier1",
                        partition="validation",
                        method=method,
                        seed=seed,
                        structural_state_id=state,
                        calls=nonpolicy_validation_calls,
                        candidate_pool=int(
                            nonpolicy_cfg["candidate_pool_per_seed_per_structural_state"]
                        ),
                        atomic_reason="select_one_design_from_exact_32_candidate_pool",
                    )
                )

    for method in learned:
        for seed in seeds:
            shards.append(
                make_shard(
                    phase="tier1_validation_learned",
                    backend="Tier1",
                    partition="validation",
                    method=method,
                    seed=seed,
                    structural_state_id=None,
                    structural_states=len(states),
                    calls=learned_validation_calls,
                    checkpoints=len(learned_cfg["checkpoints_at_training_calls"]),
                    calls_per_checkpoint=int(learned_cfg["calls_per_checkpoint"]),
                    atomic_reason="earliest_tie_broken_checkpoint_selection_across_all_states",
                )
            )

    for method in stochastic:
        for seed in seeds:
            shards.append(
                make_shard(
                    phase="tier2_confirmatory_seeded",
                    backend="Tier2_OpenSeesPy",
                    partition="confirmatory",
                    method=method,
                    seed=seed,
                    structural_state_id=None,
                    structural_states=len(states),
                    records_per_state=confirmatory_records,
                    calls=calls_per_seeded_tier2_shard,
                    atomic_reason="one_selected_design_per_state_for_one_method_seed",
                )
            )

    for method in support:
        shards.append(
            make_shard(
                phase="tier2_confirmatory_support",
                backend="Tier2_OpenSeesPy",
                partition="confirmatory",
                method=method,
                seed=None,
                structural_state_id=None,
                structural_states=len(states),
                records_per_state=confirmatory_records,
                calls=calls_per_seeded_tier2_shard,
                atomic_reason="deterministic_support_across_all_confirmatory_worlds",
            )
        )

    phase_calls: Counter[str] = Counter()
    phase_shards: Counter[str] = Counter()
    for shard in shards:
        phase_calls[shard["phase"]] += int(shard["calls"])
        phase_shards[shard["phase"]] += 1
    tier1_calls = sum(
        calls for phase, calls in phase_calls.items() if phase.startswith("tier1_")
    )
    tier2_calls = sum(
        calls for phase, calls in phase_calls.items() if phase.startswith("tier2_")
    )
    if tier1_calls != EXPECTED_TIER1_CALLS:
        raise ValueError(f"Tier-1 planned calls mismatch: {tier1_calls}")
    if tier2_calls != EXPECTED_TIER2_CALLS:
        raise ValueError(f"Tier-2 planned calls mismatch: {tier2_calls}")
    if len({shard["shard_id"] for shard in shards}) != len(shards):
        raise ValueError("execution shard IDs are not unique")

    return {
        "schema": "confirmatory-execution-shards-v1",
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": scientific_commit,
        "authoritative_gate_pass": True,
        "execution_contract_sha256": EXPECTED_EXECUTION_SHA256,
        "structural_world_manifest_sha256": EXPECTED_STRUCTURAL_MANIFEST_SHA256,
        "contains_waveform_bytes": False,
        "contains_response_outcomes": False,
        "pilot_partition_in_execution_ledger": False,
        "structural_states": states,
        "algorithm_seeds": seeds,
        "methods": {
            "nonpolicy": nonpolicy,
            "learned": learned,
            "stochastic": stochastic,
            "deterministic_support": support,
        },
        "summary": {
            "total_shards": len(shards),
            "tier1_calls": tier1_calls,
            "tier2_calls": tier2_calls,
            "total_calls": tier1_calls + tier2_calls,
            "phase_calls": dict(sorted(phase_calls.items())),
            "phase_shards": dict(sorted(phase_shards.items())),
        },
        "shards": shards,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(f"Execution ledger: {args.output}")
    print(f"Ledger SHA-256: {hashlib.sha256(payload.encode()).hexdigest()}")
    print(f"Shards: {plan['summary']['total_shards']}")
    print(f"Tier-1 calls: {plan['summary']['tier1_calls']}")
    print(f"Tier-2 calls: {plan['summary']['tier2_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())