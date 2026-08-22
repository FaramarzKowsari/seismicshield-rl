from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from seismicshield_rl.algorithms.confirmatory import DesignContext, DesignSpace, ObjectiveRecord
from seismicshield_rl.algorithms.execution_v0_8_2 import (
    CandidateRunResult,
    run_scalar_ga_candidates,
    select_candidate_on_validation,
    train_validation_selected_policy,
)
from seismicshield_rl.execution_v0_8_2 import (
    BalancedOracle,
    FAILURE_VECTOR,
    FixedObjectiveEvaluation,
    FixedObjectiveEvaluator,
    ValidationPanel,
    aggregate_training_response_features,
    sha256_balanced_order,
)
from seismicshield_rl.physics.base import DamperDesign, SimulationResult


def _result(n: int, *, midr: float, pfa_g: float, converged: bool = True) -> SimulationResult:
    t = np.asarray([0.0, 0.01, 0.02], dtype=float)
    drift = np.zeros((3, n), dtype=float)
    drift[1, :] = np.linspace(midr / max(n, 1), midr, n)
    zeros = np.zeros((3, n), dtype=float)
    return SimulationResult(
        time_s=t,
        displacement_m=zeros.copy(),
        velocity_mps=zeros.copy(),
        relative_accel_mps2=zeros.copy(),
        absolute_accel_mps2=zeros.copy(),
        story_drift_ratio=drift,
        damper_force_n=zeros.copy(),
        metrics={
            "midr": float(midr),
            "pfa_mps2": float(pfa_g * 9.80665),
            "pfa_g": float(pfa_g),
            "max_displacement_m": 0.01,
            "dissipated_energy_j": 12.0,
        },
        converged=bool(converged),
        backend="public-synthetic-v0.8.2",
    )


class _Simulator:
    def __init__(self, result: SimulationResult):
        self.result = result

    def simulate(self, design, ground_motion):
        return self.result


class _GroundMotion:
    pass


def test_fixed_objective_matches_public_osf_normalization():
    evaluator = FixedObjectiveEvaluator(
        _Simulator(_result(2, midr=0.01, pfa_g=0.5)),
        _GroundMotion(),
        max_dampers_per_story=2,
        max_slip_force_n=100_000.0,
    )
    design = DamperDesign(
        np.asarray([1, 1], dtype=int),
        np.asarray([100_000.0, 100_000.0], dtype=float),
    )
    observed = evaluator.evaluate(design)
    # Cost = 0.5*count_fraction + 0.5*capacity_fraction = 0.5.
    assert np.allclose(observed.vector, [0.5, 0.5, 0.5])
    assert observed.scalar == pytest.approx(0.5)
    assert observed.status == "valid_converged"


def test_failed_simulation_uses_frozen_finite_failure_vector():
    evaluator = FixedObjectiveEvaluator(
        _Simulator(_result(1, midr=float("inf"), pfa_g=float("inf"), converged=False)),
        _GroundMotion(),
        max_dampers_per_story=2,
        max_slip_force_n=100_000.0,
    )
    design = DamperDesign(np.asarray([0], dtype=int), np.asarray([0.0], dtype=float))
    observed = evaluator.evaluate(design)
    assert np.array_equal(observed.vector, FAILURE_VECTOR)
    assert observed.scalar == pytest.approx(0.20 * 1.05 + 0.45 * 5.0 + 0.35 * 5.0 + 10.0)
    assert not observed.converged


@dataclass
class _Building:
    n_stories: int
    masses_kg: np.ndarray
    stiffness_n_per_m: np.ndarray


def test_training_response_features_are_aggregate_only_and_deterministic():
    building = _Building(
        3,
        np.asarray([200_000.0, 190_000.0, 180_000.0]),
        np.asarray([180e6, 150e6, 120e6]),
    )
    first = _result(3, midr=0.012, pfa_g=0.45)
    second = _result(3, midr=0.018, pfa_g=0.55)
    features = aggregate_training_response_features(building, [first, second])
    replay = aggregate_training_response_features(building, [first, second])
    assert features.shape == (3, 6)
    assert np.array_equal(features, replay)
    assert features[0, 4] == pytest.approx(0.015)
    assert features[0, 5] == pytest.approx(0.50)
    assert not np.array_equal(features[:, 3], np.zeros(3))


def test_balanced_sha_schedule_uses_each_identity_once_per_cycle():
    ids = ["a", "b", "c", "d"]
    first = sha256_balanced_order(ids, seed=1103, namespace="fixture", cycle_index=0)
    second = sha256_balanced_order(ids, seed=1103, namespace="fixture", cycle_index=1)
    assert sorted(first) == ids
    assert sorted(second) == ids
    assert first == sha256_balanced_order(ids, seed=1103, namespace="fixture", cycle_index=0)


class _FixedEvaluatorStub:
    def __init__(self, record_id: str):
        self.record_id = record_id

    def evaluate(self, design: DamperDesign) -> FixedObjectiveEvaluation:
        value = float(ord(self.record_id[-1]) - ord("a") + 1) / 10.0
        vector = np.asarray([0.1, 0.5 + value, 0.7 + value], dtype=float)
        return FixedObjectiveEvaluation(
            cost=0.1,
            midr=0.02 * vector[1],
            pfa_g=vector[2],
            vector=vector,
            scalar=float(np.asarray([0.2, 0.45, 0.35]) @ vector),
            converged=True,
            status="valid_converged",
            max_displacement_m=0.01,
            dissipated_energy_j=1.0,
        )


def test_balanced_oracle_charges_records_in_complete_cycles():
    seen: list[str] = []
    evaluators = {key: _FixedEvaluatorStub(key) for key in ["ra", "rb", "rc"]}
    oracle = BalancedOracle(
        evaluators,
        seed=2207,
        structural_state_id="3-nominal",
        audit=lambda record_id, design, evaluation: seen.append(record_id),
    )
    design = DamperDesign(np.asarray([0]), np.asarray([0.0]))
    for _ in range(6):
        oracle(design)
    assert sorted(seen[:3]) == ["ra", "rb", "rc"]
    assert sorted(seen[3:]) == ["ra", "rb", "rc"]
    assert oracle.completed == 6


def _synthetic_oracle(design: DamperDesign) -> ObjectiveRecord:
    capacity = design.total_story_capacity_n.astype(float)
    cost = float(np.mean(capacity) / 200_000.0)
    target = np.linspace(50_000.0, 150_000.0, capacity.size)
    mismatch = (capacity - target) / 200_000.0
    vector = np.asarray(
        [cost, 0.5 + float(np.mean(mismatch * mismatch)), 0.7 + float(np.mean(np.abs(mismatch)))],
        dtype=float,
    )
    scalar = float(np.asarray([0.2, 0.45, 0.35]) @ vector)
    return ObjectiveRecord(vector, scalar, True)


def test_scalar_ga_consumes_exact_budget_and_returns_valid_population():
    space = DesignSpace(3, 2, np.asarray([0.0, 50_000.0, 100_000.0]))
    first = run_scalar_ga_candidates(space, _synthetic_oracle, budget=64, seed=3313, population_size=16)
    second = run_scalar_ga_candidates(space, _synthetic_oracle, budget=64, seed=3313, population_size=16)
    assert first.evaluations == 64
    assert len(first.designs) == 16
    assert np.array_equal(first.designs[0].counts, second.designs[0].counts)
    assert np.array_equal(first.designs[0].slip_force_n, second.designs[0].slip_force_n)


def test_candidate_selection_uses_full_validation_panel_and_is_deterministic():
    space = DesignSpace(2, 2, np.asarray([0.0, 50_000.0, 100_000.0]))
    designs = [
        DamperDesign(np.asarray([0, 0]), np.asarray([0.0, 0.0])),
        DamperDesign(np.asarray([1, 1]), np.asarray([50_000.0, 50_000.0])),
    ]
    records = [_synthetic_oracle(design) for design in designs]
    run = CandidateRunResult("scalar_ga", 1103, 2, designs, records)

    class _PanelEvaluator:
        def __init__(self, preferred: DamperDesign):
            self.preferred = preferred

        def evaluate(self, design):
            match = np.array_equal(design.counts, self.preferred.counts)
            value = 0.2 if match else 0.8
            vector = np.asarray([0.2, value, value])
            return FixedObjectiveEvaluation(
                cost=0.2, midr=0.02 * value, pfa_g=value, vector=vector,
                scalar=float(np.asarray([0.2, 0.45, 0.35]) @ vector), converged=True,
                status="valid_converged", max_displacement_m=0.0, dissipated_energy_j=0.0,
            )

    panel = ValidationPanel(
        "2-nominal",
        np.ones((2, 6), dtype=np.float32),
        {"v1": _PanelEvaluator(designs[1]), "v2": _PanelEvaluator(designs[1])},
    )
    selected = select_candidate_on_validation(run, panel, pool_size=2)
    assert np.array_equal(selected.design.counts, designs[1].counts)
    assert selected.validation_calls == 4


def test_variable_height_policy_is_validation_selected_and_replayable():
    torch = pytest.importorskip("torch")
    del torch
    space = DesignSpace(6, 2, np.asarray([0.0, 50_000.0, 100_000.0]))

    def context(n: int, context_id: str) -> DesignContext:
        local = np.zeros((n, 6), dtype=np.float32)
        local[:, 0] = np.linspace(0.0, 1.0, n)
        local[:, 1:3] = 1.0
        local[:, 3] = np.linspace(0.5, 1.0, n)
        local[:, 4] = 0.015
        local[:, 5] = 0.50
        return DesignContext(local, _synthetic_oracle, context_id=context_id)

    train_contexts = [context(3, "3-nominal"), context(6, "6-nominal")]

    class _PolicyPanelEvaluator:
        def evaluate(self, design):
            record = _synthetic_oracle(design)
            return FixedObjectiveEvaluation(
                cost=float(record.vector[0]), midr=0.02 * float(record.vector[1]),
                pfa_g=float(record.vector[2]), vector=record.vector, scalar=record.scalar,
                converged=True, status="valid_converged", max_displacement_m=0.0,
                dissipated_energy_j=0.0,
            )

    validation = [
        ValidationPanel(
            item.context_id,
            item.local_features,
            {"v1": _PolicyPanelEvaluator(), "v2": _PolicyPanelEvaluator()},
        )
        for item in train_contexts
    ]
    result = train_validation_selected_policy(
        "mappo",
        space,
        train_contexts,
        validation,
        budget=32,
        seed=1103,
        checkpoint_calls=[16, 32],
        batch_design_evaluations=8,
        update_epochs=1,
        hidden_units=(16, 16),
    )
    assert result.training_evaluations == 32
    assert result.validation_evaluations == 8  # 2 checkpoints * 2 panels * 2 records.
    first = result.checkpoint.design(train_contexts[0].local_features)
    second = result.checkpoint.design(train_contexts[0].local_features)
    assert first.counts.shape == (3,)
    assert np.array_equal(first.counts, second.counts)
    assert np.array_equal(first.slip_force_n, second.slip_force_n)
