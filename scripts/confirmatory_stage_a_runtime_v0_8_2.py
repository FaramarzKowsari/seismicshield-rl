#!/usr/bin/env python3
"""Internal Stage-A runtime executed with immutable v0.8.2 scientific modules.

Do not invoke directly. The parent shard runner launches this file in isolated Python with the
exact `confirmatory-v0.8.2-final` source tree first on sys.path. Only training and validation
records are accepted; pilot and confirmatory records are rejected before simulation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter
from typing import Any

import numpy as np
import yaml

import seismicshield_rl.algorithms.execution_v0_8_2 as algorithm_execution
import seismicshield_rl.execution_v0_8_2 as execution
import seismicshield_rl.physics.ground_motion as ground_motion_module
import seismicshield_rl.physics.shear_building as shear_building_module
import seismicshield_rl.structural_worlds as structural_worlds_module
from seismicshield_rl.algorithms.confirmatory import DesignContext, DesignSpace
from seismicshield_rl.algorithms.execution_v0_8_2 import (
    run_nsga2_candidates,
    run_random_candidates,
    run_scalar_ga_candidates,
    select_candidate_on_validation,
    train_validation_selected_policy,
)
from seismicshield_rl.execution_v0_8_2 import (
    BalancedOracle,
    FixedObjectiveEvaluator,
    ValidationPanel,
    aggregate_training_response_features,
)
from seismicshield_rl.physics.base import DamperDesign
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator
from seismicshield_rl.structural_worlds import StructuralRealization, building_for_world, load_contract

EXPECTED_SCIENTIFIC_TAG = "confirmatory-v0.8.2-final"
EXPECTED_SCIENTIFIC_COMMIT = "cecd3b6c27b5deb6cb6be7ddc478cfc407a45644"
EXPECTED_GROUND_SHA256 = "0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b"
EXPECTED_STRUCTURAL_SHA256 = "c4fa4d4ee203bbdb5475bd55140fe2c24246db3254a0f099b7535d4f23a8248f"
EXPECTED_EXECUTION_SHA256 = "4be2acca57915ff6954a82dfb03bc5adc647bf1e9594fd01042c7be2af87dd50"
EXPECTED_ALGORITHM_BUNDLE_SHA256 = "cddfc37bab5263ef920a09285edee81cdbdfd2dc6e8247bf1dca981541c6db65"
EXPECTED_SEEDS = [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861]
EXPECTED_STATES = [
    "3:nominal", "3:lhs-1", "3:lhs-2", "3:lhs-3",
    "6:nominal", "6:lhs-1", "6:lhs-2", "6:lhs-3",
    "10:nominal", "10:lhs-1", "10:lhs-2", "10:lhs-3",
    "20:nominal", "20:lhs-1", "20:lhs-2", "20:lhs-3",
]
EXPECTED_CHECKPOINTS = [5120, 10240, 15360, 20480, 25600, 30720, 35840, 40960, 46080, 51200]
MAX_DAMPERS = 4
SLIP_LEVELS = np.asarray([0.0, 50_000.0, 100_000.0, 200_000.0, 350_000.0], dtype=float)
MAX_SLIP = 350_000.0


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_design(design: DamperDesign) -> dict[str, list]:
    counts = np.asarray(design.counts, dtype=int)
    slips = np.asarray(design.slip_force_n, dtype=float)
    slips = np.where(counts > 0, slips, 0.0)
    return {
        "counts": [int(value) for value in counts.tolist()],
        "slip_force_n": [float(value) for value in slips.tolist()],
    }


def design_hash(design: DamperDesign) -> str:
    return hashlib.sha256(canonical_json(canonical_design(design)).encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"YAML must be a mapping: {path}")
    return value


def validate_scientific_source(scientific_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    scientific_root = scientific_root.resolve()
    expected_src = (scientific_root / "src").resolve()
    modules = [execution, algorithm_execution, ground_motion_module, shear_building_module, structural_worlds_module]
    for module in modules:
        module_file = Path(module.__file__).resolve()
        if not module_file.is_relative_to(expected_src):
            raise RuntimeError(f"scientific module escaped immutable source tree: {module.__name__} -> {module_file}")
    required = {
        scientific_root / "data/manifests/ground_motion_manifest.csv": EXPECTED_GROUND_SHA256,
        scientific_root / "data/manifests/structural_world_manifest.csv": EXPECTED_STRUCTURAL_SHA256,
        scientific_root / "open_science/confirmatory_execution_v0.8.2.yaml": EXPECTED_EXECUTION_SHA256,
        scientific_root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml": EXPECTED_ALGORITHM_BUNDLE_SHA256,
    }
    for path, expected in required.items():
        observed = sha256_path(path)
        if observed != expected:
            raise RuntimeError(f"immutable scientific file digest mismatch: {path.name}: {observed}")
    contract = read_yaml(scientific_root / "open_science/confirmatory_execution_v0.8.2.yaml")
    bundle = read_yaml(scientific_root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml")
    if contract["training_budget"]["stochastic_methods"] != ["random_search", "scalar_ga", "nsga2", "ppo", "ippo", "mappo"]:
        raise RuntimeError("unexpected frozen stochastic method order")
    if list(contract["validation_selection"]["learned_methods"]["checkpoints_at_training_calls"]) != EXPECTED_CHECKPOINTS:
        raise RuntimeError("unexpected frozen learned checkpoint schedule")
    if list(bundle.get("seeds") or []) != EXPECTED_SEEDS:
        raise RuntimeError("unexpected frozen algorithm seeds")
    return contract, bundle


def load_manifests(scientific_root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ground = read_csv(scientific_root / "data/manifests/ground_motion_manifest.csv")
    structural = read_csv(scientific_root / "data/manifests/structural_world_manifest.csv")
    if len(ground) != 136 or len(structural) != 136 * 16:
        raise RuntimeError("frozen manifest cardinality mismatch")
    counts = {partition: sum(row["partition"] == partition for row in ground) for partition in ("training", "validation", "pilot", "confirmatory")}
    if counts != {"training": 52, "validation": 20, "pilot": 16, "confirmatory": 48}:
        raise RuntimeError(f"frozen ground partition counts mismatch: {counts}")
    return ground, structural


def private_stage_a_index(private_dir: Path, ground_rows: list[dict[str, str]]) -> dict[str, Path]:
    allowed_rows = [row for row in ground_rows if row["partition"] in {"training", "validation"}]
    expected = {row["processed_sha256"].lower() for row in allowed_rows}
    forbidden = {row["processed_sha256"].lower() for row in ground_rows if row["partition"] in {"pilot", "confirmatory"}}
    if len(expected) != 72:
        raise RuntimeError("Stage-A requires exactly 72 unique training/validation processed records")
    if not private_dir.is_dir():
        raise RuntimeError(f"Stage-A private directory is missing: {private_dir}")
    entries = list(private_dir.iterdir())
    if any(not path.is_file() or path.suffix != ".csv" for path in entries):
        raise RuntimeError("Stage-A private directory may contain only processed CSV waveform files")
    index: dict[str, Path] = {}
    for path in entries:
        stem = path.stem.lower()
        if stem in forbidden:
            raise RuntimeError(f"pilot/confirmatory waveform present in Stage-A runtime directory: {path.name}")
        if stem not in expected:
            raise RuntimeError(f"unrecognized waveform present in Stage-A runtime directory: {path.name}")
        observed = sha256_path(path)
        if observed != stem:
            raise RuntimeError(f"Stage-A waveform digest mismatch: {path.name} -> {observed}")
        index[stem] = path
    if set(index) != expected:
        raise RuntimeError(f"Stage-A private set incomplete: expected 72, found {len(index)}")
    return index


def state_rows(structural_rows: list[dict[str, str]], state_id: str, partition: str) -> list[dict[str, str]]:
    height_text, realization_id = state_id.split(":", 1)
    matches = [
        row for row in structural_rows
        if row["partition"] == partition
        and row["building_height_stories"] == height_text
        and row["realization_id"] == realization_id
    ]
    expected = {"training": 52, "validation": 20}.get(partition)
    if expected is None or len(matches) != expected:
        raise RuntimeError(f"structural rows mismatch for {state_id}/{partition}: {len(matches)}")
    return matches


def realization_from_rows(rows: list[dict[str, str]]) -> StructuralRealization:
    keys = ("realization_id", "is_nominal", "mass_scale", "stiffness_scale", "damping_ratio", "damper_capacity_scale")
    signatures = {tuple(row[key] for key in keys) for row in rows}
    if len(signatures) != 1:
        raise RuntimeError("structural realization parameters vary within one frozen state")
    row = rows[0]
    return StructuralRealization(
        realization_id=row["realization_id"],
        is_nominal=row["is_nominal"].lower() == "true",
        mass_scale=float(row["mass_scale"]),
        stiffness_scale=float(row["stiffness_scale"]),
        damping_ratio=float(row["damping_ratio"]),
        damper_capacity_scale=float(row["damper_capacity_scale"]),
    )


def build_state(scientific_root: Path, structural_rows: list[dict[str, str]], state_id: str):
    training_rows = state_rows(structural_rows, state_id, "training")
    validation_rows = state_rows(structural_rows, state_id, "validation")
    realization = realization_from_rows(training_rows + validation_rows)
    height = int(state_id.split(":", 1)[0])
    contract = load_contract(scientific_root / "open_science/structural_world_freeze_v0.8.1.yaml")
    building = building_for_world(height, realization, contract)
    return building, realization, training_rows, validation_rows


def load_motions(ground_rows: list[dict[str, str]], private_index: dict[str, Path]) -> dict[str, Any]:
    motions: dict[str, Any] = {}
    for row in ground_rows:
        if row["partition"] not in {"training", "validation"}:
            continue
        record_id = row["record_id"]
        if record_id in motions:
            raise RuntimeError(f"duplicate Stage-A record id: {record_id}")
        path = private_index[row["processed_sha256"].lower()]
        motions[record_id] = load_csv_ground_motion(path, motion_id=record_id, source=f"ESM-{row['partition']}")
    if len(motions) != 72:
        raise RuntimeError(f"expected 72 Stage-A motions, loaded {len(motions)}")
    return motions


class AuditWriter:
    def __init__(self, path: Path, *, checkpoints: list[int] | None = None, calls_per_checkpoint: int = 0):
        self.path = path
        self.handle = path.open("w", encoding="utf-8")
        self.total = 0
        self.partition_counts = {"training": 0, "validation": 0}
        self.checkpoints = list(checkpoints or [])
        self.calls_per_checkpoint = int(calls_per_checkpoint)
        self.validation_seen = 0
        self.validation_sums = {checkpoint: np.zeros(3, dtype=float) for checkpoint in self.checkpoints}
        self.validation_counts = {checkpoint: 0 for checkpoint in self.checkpoints}

    def close(self) -> None:
        self.handle.flush()
        os.fsync(self.handle.fileno())
        self.handle.close()

    def record(self, *, method: str, seed: int | None, partition: str, state_id: str, world_id: str, record_id: str, design: DamperDesign, evaluation, wall_clock_s: float) -> None:
        checkpoint_call = None
        if partition == "validation" and self.checkpoints:
            block = self.validation_seen // self.calls_per_checkpoint
            if block >= len(self.checkpoints):
                raise RuntimeError("learned validation exceeded frozen checkpoint blocks")
            checkpoint_call = self.checkpoints[block]
            self.validation_seen += 1
            self.validation_sums[checkpoint_call] += np.asarray(evaluation.vector, dtype=float)
            self.validation_counts[checkpoint_call] += 1
        row = {
            "method": method,
            "seed": seed,
            "partition": partition,
            "world_id": world_id,
            "structural_state_id": state_id,
            "record_id": record_id,
            "design_hash": design_hash(design),
            "status": evaluation.status,
            "vector": [float(value) for value in np.asarray(evaluation.vector, dtype=float).tolist()],
            "scalar": float(evaluation.scalar),
            "wall_clock_s": float(wall_clock_s),
            "checkpoint_training_call": checkpoint_call,
        }
        self.handle.write(json.dumps(row, sort_keys=True) + "\n")
        self.total += 1
        if partition in self.partition_counts:
            self.partition_counts[partition] += 1

    def validation_vector(self, checkpoint: int) -> list[float]:
        count = self.validation_counts.get(int(checkpoint), 0)
        if count != self.calls_per_checkpoint:
            raise RuntimeError(
                f"selected learned checkpoint has {count} validation calls; expected {self.calls_per_checkpoint}"
            )
        return [float(value) for value in (self.validation_sums[int(checkpoint)] / count).tolist()]


class AuditedEvaluator:
    def __init__(self, evaluator: FixedObjectiveEvaluator, *, logger: AuditWriter, method: str, seed: int | None, partition: str, state_id: str, world_id: str, record_id: str):
        self.evaluator = evaluator
        self.logger = logger
        self.method = method
        self.seed = seed
        self.partition = partition
        self.state_id = state_id
        self.world_id = world_id
        self.record_id = record_id

    def evaluate(self, design: DamperDesign):
        started = perf_counter()
        result = self.evaluator.evaluate(design)
        self.logger.record(
            method=self.method,
            seed=self.seed,
            partition=self.partition,
            state_id=self.state_id,
            world_id=self.world_id,
            record_id=self.record_id,
            design=design,
            evaluation=result,
            wall_clock_s=perf_counter() - started,
        )
        return result


class CapturingSimulator:
    def __init__(self, simulator):
        self.simulator = simulator
        self.last_result = None

    def simulate(self, design, ground_motion):
        self.last_result = self.simulator.simulate(design, ground_motion)
        return self.last_result


def world_map(rows: list[dict[str, str]]) -> dict[str, str]:
    result = {row["record_id"]: row["world_id"] for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("duplicate record IDs within one structural-state partition")
    return result


def evaluator_map(*, building, realization: StructuralRealization, rows: list[dict[str, str]], motions: dict[str, Any], logger: AuditWriter, method: str, seed: int | None, partition: str, state_id: str) -> dict[str, AuditedEvaluator]:
    simulator = ShearBuildingSimulator(building, damper_capacity_scale=realization.damper_capacity_scale)
    worlds = world_map(rows)
    result: dict[str, AuditedEvaluator] = {}
    for row in rows:
        record_id = row["record_id"]
        frozen = FixedObjectiveEvaluator(
            simulator,
            motions[record_id],
            max_dampers_per_story=MAX_DAMPERS,
            max_slip_force_n=MAX_SLIP,
        )
        result[record_id] = AuditedEvaluator(
            frozen,
            logger=logger,
            method=method,
            seed=seed,
            partition=partition,
            state_id=state_id,
            world_id=worlds[record_id],
            record_id=record_id,
        )
    return result


def feature_path(feature_dir: Path, state_id: str) -> Path:
    return feature_dir / f"{state_id.replace(':', '__')}.json"


def load_feature(feature_dir: Path, state_id: str, n_stories: int) -> np.ndarray:
    path = feature_path(feature_dir, state_id)
    if not path.is_file():
        raise RuntimeError(f"required feature artifact is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "confirmatory-stage-a-feature-v1":
        raise RuntimeError(f"unexpected feature artifact schema: {path}")
    if value.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT or value.get("structural_state_id") != state_id:
        raise RuntimeError(f"feature artifact identity mismatch: {path}")
    features = np.asarray(value.get("local_features"), dtype=np.float32)
    if features.shape != (n_stories, 6) or not np.all(np.isfinite(features)):
        raise RuntimeError(f"feature matrix shape/value mismatch: {path}: {features.shape}")
    return features


def run_feature(scientific_root: Path, shard: dict[str, Any], ground_rows, structural_rows, motions, output_dir: Path) -> dict[str, Any]:
    state_id = shard["structural_state_id"]
    building, realization, training_rows, _ = build_state(scientific_root, structural_rows, state_id)
    logger = AuditWriter(output_dir / "calls.jsonl")
    simulator = CapturingSimulator(
        ShearBuildingSimulator(building, damper_capacity_scale=realization.damper_capacity_scale)
    )
    zero = DamperDesign(np.zeros(building.n_stories, dtype=int), np.zeros(building.n_stories, dtype=float))
    results = []
    worlds = world_map(training_rows)
    try:
        for row in training_rows:
            record_id = row["record_id"]
            evaluator = FixedObjectiveEvaluator(
                simulator,
                motions[record_id],
                max_dampers_per_story=MAX_DAMPERS,
                max_slip_force_n=MAX_SLIP,
            )
            started = perf_counter()
            evaluation = evaluator.evaluate(zero)
            elapsed = perf_counter() - started
            logger.record(
                method="shared_undamped_feature", seed=None, partition="training",
                state_id=state_id, world_id=worlds[record_id], record_id=record_id,
                design=zero, evaluation=evaluation, wall_clock_s=elapsed,
            )
            if simulator.last_result is None:
                raise RuntimeError("capturing simulator did not retain undamped response")
            results.append(simulator.last_result)
        features = aggregate_training_response_features(building, results)
    finally:
        logger.close()
    if logger.total != int(shard["calls"]) or logger.partition_counts["training"] != 52:
        raise RuntimeError("feature-precompute call accounting mismatch")
    return {
        "schema": "confirmatory-stage-a-feature-v1",
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
        "shard_id": shard["shard_id"],
        "phase": shard["phase"],
        "structural_state_id": state_id,
        "completed_calls": logger.total,
        "local_features": np.asarray(features, dtype=np.float32).tolist(),
        "contains_waveform_bytes": False,
        "contains_confirmatory_outcomes": False,
    }


def run_nonpolicy(scientific_root: Path, shard: dict[str, Any], ground_rows, structural_rows, motions, feature_dir: Path, output_dir: Path) -> dict[str, Any]:
    method = str(shard["method"])
    seed = int(shard["seed"])
    state_id = str(shard["structural_state_id"])
    if method not in {"random_search", "scalar_ga", "nsga2"} or seed not in EXPECTED_SEEDS:
        raise RuntimeError("unexpected nonpolicy method/seed")
    building, realization, training_rows, validation_rows = build_state(scientific_root, structural_rows, state_id)
    features = load_feature(feature_dir, state_id, building.n_stories)
    logger = AuditWriter(output_dir / "calls.jsonl")
    try:
        training = evaluator_map(
            building=building, realization=realization, rows=training_rows, motions=motions,
            logger=logger, method=method, seed=seed, partition="training", state_id=state_id,
        )
        oracle = BalancedOracle(training, seed=seed, structural_state_id=state_id)
        space = DesignSpace(building.n_stories, MAX_DAMPERS, SLIP_LEVELS)
        budget = int(shard["training_calls"])
        if method == "random_search":
            run = run_random_candidates(space, oracle, budget=budget, seed=seed)
        elif method == "scalar_ga":
            run = run_scalar_ga_candidates(space, oracle, budget=budget, seed=seed, population_size=256, crossover_probability=0.90)
        else:
            run = run_nsga2_candidates(space, oracle, budget=budget, seed=seed, population_size=256, crossover_probability=0.90)
        validation = evaluator_map(
            building=building, realization=realization, rows=validation_rows, motions=motions,
            logger=logger, method=method, seed=seed, partition="validation", state_id=state_id,
        )
        panel = ValidationPanel(state_id, features, validation)
        selected = select_candidate_on_validation(run, panel, pool_size=int(shard["candidate_pool"]))
    finally:
        logger.close()
    if run.evaluations != int(shard["training_calls"]):
        raise RuntimeError("nonpolicy training call accounting mismatch")
    if selected.validation_calls != int(shard["validation_calls"]):
        raise RuntimeError("nonpolicy validation call accounting mismatch")
    if logger.total != int(shard["calls"]):
        raise RuntimeError(f"nonpolicy audit row count mismatch: {logger.total} != {shard['calls']}")
    design = canonical_design(selected.design)
    return {
        "schema": "confirmatory-stage-a-selection-v1",
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
        "shard_id": shard["shard_id"],
        "phase": shard["phase"],
        "method": method,
        "seed": seed,
        "structural_state_id": state_id,
        "completed_calls": logger.total,
        "training_calls": run.evaluations,
        "validation_calls": selected.validation_calls,
        "candidate_pool": selected.pool_size,
        "selected_design": design,
        "selected_design_hash": design_hash(selected.design),
        "validation_vector": [float(value) for value in selected.validation_record.vector.tolist()],
        "validation_scalar": float(selected.validation_record.scalar),
        "validation_converged": bool(selected.validation_record.converged),
        "contains_waveform_bytes": False,
        "contains_confirmatory_outcomes": False,
    }


def learned_hyperparameters(bundle: dict[str, Any], method: str) -> dict[str, Any]:
    config = dict(bundle["methods"][method])
    expected = {
        "hidden_units": [128, 128], "learning_rate": 0.0003,
        "batch_design_evaluations": 256, "update_epochs": 4,
        "clip_epsilon": 0.20, "value_loss_coefficient": 0.50,
        "entropy_coefficient": 0.01, "max_grad_norm": 0.50,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise RuntimeError(f"learned hyperparameter mismatch for {method}/{key}: {config.get(key)!r}")
    return expected


def run_learned(scientific_root: Path, shard: dict[str, Any], ground_rows, structural_rows, motions, feature_dir: Path, output_dir: Path, contract: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    method = str(shard["method"])
    seed = int(shard["seed"])
    if method not in {"ppo", "ippo", "mappo"} or seed not in EXPECTED_SEEDS:
        raise RuntimeError("unexpected learned method/seed")
    checkpoints = list(contract["validation_selection"]["learned_methods"]["checkpoints_at_training_calls"])
    calls_per_checkpoint = int(shard["validation_calls_per_checkpoint"])
    if checkpoints != EXPECTED_CHECKPOINTS or calls_per_checkpoint != 320:
        raise RuntimeError("learned validation schedule differs from frozen contract")
    logger = AuditWriter(
        output_dir / "calls.jsonl", checkpoints=checkpoints, calls_per_checkpoint=calls_per_checkpoint
    )
    contexts: list[DesignContext] = []
    panels: list[ValidationPanel] = []
    features_by_state: dict[str, np.ndarray] = {}
    try:
        for state_id in EXPECTED_STATES:
            building, realization, training_rows, validation_rows = build_state(
                scientific_root, structural_rows, state_id
            )
            features = load_feature(feature_dir, state_id, building.n_stories)
            features_by_state[state_id] = features
            training = evaluator_map(
                building=building, realization=realization, rows=training_rows, motions=motions,
                logger=logger, method=method, seed=seed, partition="training", state_id=state_id,
            )
            oracle = BalancedOracle(training, seed=seed, structural_state_id=state_id)
            contexts.append(DesignContext(features, oracle, context_id=state_id))
            validation = evaluator_map(
                building=building, realization=realization, rows=validation_rows, motions=motions,
                logger=logger, method=method, seed=seed, partition="validation", state_id=state_id,
            )
            panels.append(ValidationPanel(state_id, features, validation))
        hp = learned_hyperparameters(bundle, method)
        space = DesignSpace(20, MAX_DAMPERS, SLIP_LEVELS)
        result = train_validation_selected_policy(
            method,
            space,
            contexts,
            panels,
            budget=int(shard["training_calls"]),
            seed=seed,
            checkpoint_calls=checkpoints,
            batch_design_evaluations=int(hp["batch_design_evaluations"]),
            update_epochs=int(hp["update_epochs"]),
            learning_rate=float(hp["learning_rate"]),
            clip_epsilon=float(hp["clip_epsilon"]),
            value_loss_coefficient=float(hp["value_loss_coefficient"]),
            entropy_coefficient=float(hp["entropy_coefficient"]),
            max_grad_norm=float(hp["max_grad_norm"]),
            hidden_units=tuple(int(value) for value in hp["hidden_units"]),
        )
    finally:
        logger.close()
    if result.training_evaluations != int(shard["training_calls"]):
        raise RuntimeError("learned training call accounting mismatch")
    if result.validation_evaluations != int(shard["validation_calls"]):
        raise RuntimeError("learned validation call accounting mismatch")
    if logger.total != int(shard["calls"]):
        raise RuntimeError(f"learned audit row count mismatch: {logger.total} != {shard['calls']}")
    checkpoint = result.checkpoint
    if checkpoint.training_call not in checkpoints:
        raise RuntimeError("selected policy checkpoint is outside frozen checkpoint schedule")
    validation_vector = logger.validation_vector(checkpoint.training_call)
    selected_designs: dict[str, Any] = {}
    for state_id in EXPECTED_STATES:
        design = checkpoint.design(features_by_state[state_id])
        selected_designs[state_id] = {
            "design": canonical_design(design),
            "design_hash": design_hash(design),
        }
    np.savez_compressed(
        output_dir / "checkpoint.npz",
        **{key: np.asarray(value, dtype=np.float32) for key, value in checkpoint.actor_state.items()},
    )
    return {
        "schema": "confirmatory-stage-a-learned-selection-v1",
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
        "shard_id": shard["shard_id"],
        "phase": shard["phase"],
        "method": method,
        "seed": seed,
        "completed_calls": logger.total,
        "training_calls": result.training_evaluations,
        "validation_calls": result.validation_evaluations,
        "selected_checkpoint_training_call": int(checkpoint.training_call),
        "selected_checkpoint_validation_scalar": float(checkpoint.validation_scalar),
        "selected_checkpoint_validation_vector": validation_vector,
        "selected_checkpoint_validation_calls": int(checkpoint.validation_calls),
        "checkpoint_file": "checkpoint.npz",
        "selected_designs": selected_designs,
        "contains_waveform_bytes": False,
        "contains_confirmatory_outcomes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-root", type=Path, required=True)
    parser.add_argument("--shard-json", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--feature-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    scientific_root = args.scientific_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    contract, bundle = validate_scientific_source(scientific_root)
    ground_rows, structural_rows = load_manifests(scientific_root)
    private_index = private_stage_a_index(args.private_dir.resolve(), ground_rows)
    motions = load_motions(ground_rows, private_index)
    shard = json.loads(args.shard_json.read_text(encoding="utf-8"))
    if not isinstance(shard, dict) or not str(shard.get("phase", "")).startswith("tier1_"):
        raise RuntimeError("Stage-A runtime refuses every non-Tier1 shard")
    started = perf_counter()
    if shard["phase"] == "tier1_feature_precompute":
        artifact = run_feature(scientific_root, shard, ground_rows, structural_rows, motions, output_dir)
    elif shard["phase"] == "tier1_train_validate_nonpolicy":
        artifact = run_nonpolicy(
            scientific_root, shard, ground_rows, structural_rows, motions,
            args.feature_dir.resolve(), output_dir,
        )
    elif shard["phase"] == "tier1_train_validate_learned":
        artifact = run_learned(
            scientific_root, shard, ground_rows, structural_rows, motions,
            args.feature_dir.resolve(), output_dir, contract, bundle,
        )
    else:
        raise RuntimeError(f"unsupported Stage-A phase: {shard['phase']!r}")
    artifact["wall_clock_s"] = float(perf_counter() - started)
    artifact["environment"] = {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scientific_root": str(scientific_root),
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
        "module_origins": {
            module.__name__: str(Path(module.__file__).resolve())
            for module in [execution, algorithm_execution, ground_motion_module, shear_building_module, structural_worlds_module]
        },
    }
    if shard["phase"] == "tier1_train_validate_learned":
        try:
            import torch
            artifact["environment"]["torch"] = torch.__version__
        except Exception as exc:
            artifact["environment"]["torch"] = f"unavailable:{exc}"
    (output_dir / "artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "shard_id": shard["shard_id"], "completed_calls": artifact["completed_calls"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
