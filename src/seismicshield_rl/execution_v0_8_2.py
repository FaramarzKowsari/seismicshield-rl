from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Iterable

import numpy as np

from seismicshield_rl.algorithms.confirmatory import ObjectiveRecord
from seismicshield_rl.physics.base import DamperDesign, SimulationResult
from seismicshield_rl.physics.metrics import normalized_design_cost

MIDR_NORMALIZER = 0.02
PFA_G_NORMALIZER = 1.0
OBJECTIVE_WEIGHTS = np.asarray([0.20, 0.45, 0.35], dtype=float)
FAILURE_VECTOR = np.asarray([1.05, 5.00, 5.00], dtype=float)
FAILURE_SCALAR_PENALTY = 10.0


@dataclass(frozen=True)
class FixedObjectiveEvaluation:
    cost: float
    midr: float
    pfa_g: float
    vector: np.ndarray
    scalar: float
    converged: bool
    status: str
    max_displacement_m: float
    dissipated_energy_j: float

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=float)
        if vector.shape != (3,) or not np.all(np.isfinite(vector)):
            raise ValueError("fixed objective vector must be finite with shape (3,)")
        if not np.isfinite(self.scalar):
            raise ValueError("fixed scalar objective must be finite")
        object.__setattr__(self, "vector", vector)

    def as_objective_record(self) -> ObjectiveRecord:
        return ObjectiveRecord(self.vector.copy(), float(self.scalar), bool(self.converged))


class FixedObjectiveEvaluator:
    """Evaluate the exact objective frozen in the public OSF preregistration.

    The generic repository evaluator predates the public registration and normalizes
    response against an undamped record-specific reference. Confirmatory execution must
    instead use the registered vector [C, MIDR/0.02, PFA_g/1.0]. Failed simulations are
    retained with the preregistered finite failure vector and fixed scalar penalty.
    """

    def __init__(
        self,
        simulator,
        ground_motion,
        *,
        max_dampers_per_story: int,
        max_slip_force_n: float,
        weights: Iterable[float] = OBJECTIVE_WEIGHTS,
    ) -> None:
        self.simulator = simulator
        self.ground_motion = ground_motion
        self.max_dampers = int(max_dampers_per_story)
        self.max_slip = float(max_slip_force_n)
        self.weights = np.asarray(tuple(weights), dtype=float)
        if self.weights.shape != (3,) or np.any(self.weights < 0) or not np.isclose(
            self.weights.sum(), 1.0
        ):
            raise ValueError("objective weights must be three non-negative values summing to one")

    def evaluate(self, design: DamperDesign) -> FixedObjectiveEvaluation:
        result: SimulationResult = self.simulator.simulate(design, self.ground_motion)
        cost = normalized_design_cost(
            design,
            max_dampers_per_story=self.max_dampers,
            max_slip_force_n=self.max_slip,
        )
        raw_midr = float(result.metrics.get("midr", float("inf")))
        raw_pfa_g = float(result.metrics.get("pfa_g", float("inf")))
        raw_disp = float(result.metrics.get("max_displacement_m", float("inf")))
        raw_energy = float(result.metrics.get("dissipated_energy_j", float("inf")))
        finite_primary = np.isfinite(raw_midr) and np.isfinite(raw_pfa_g)
        converged = bool(result.converged and finite_primary)
        if converged:
            vector = np.asarray(
                [cost, raw_midr / MIDR_NORMALIZER, raw_pfa_g / PFA_G_NORMALIZER],
                dtype=float,
            )
            scalar = float(self.weights @ vector)
            status = "valid_converged"
        else:
            vector = FAILURE_VECTOR.copy()
            scalar = float(self.weights @ vector + FAILURE_SCALAR_PENALTY)
            status = "solver_or_numerical_failure"
        return FixedObjectiveEvaluation(
            cost=float(cost),
            midr=raw_midr,
            pfa_g=raw_pfa_g,
            vector=vector,
            scalar=scalar,
            converged=converged,
            status=status,
            max_displacement_m=raw_disp,
            dissipated_energy_j=raw_energy,
        )

    def record(self, design: DamperDesign) -> ObjectiveRecord:
        return self.evaluate(design).as_objective_record()


def aggregate_training_response_features(
    building,
    undamped_training_results: Iterable[SimulationResult],
) -> np.ndarray:
    """Build six story features using training responses only.

    This function is deliberately partition-agnostic: callers must provide only the 52
    training-record responses belonging to one frozen structural state. It accepts no
    event/record identifier and therefore cannot encode confirmatory identity.
    """

    results = list(undamped_training_results)
    if not results:
        raise ValueError("at least one undamped training response is required")
    n = int(building.n_stories)
    story_rows: list[np.ndarray] = []
    midr_values: list[float] = []
    pfa_values: list[float] = []
    for result in results:
        if not result.converged:
            raise RuntimeError("undamped training feature response did not converge")
        drift = np.asarray(result.story_drift_ratio, dtype=float)
        if drift.ndim != 2 or drift.shape[1] != n or not np.all(np.isfinite(drift)):
            raise RuntimeError("invalid undamped training drift history")
        story_rows.append(np.max(np.abs(drift), axis=0))
        midr = float(result.metrics.get("midr", float("nan")))
        pfa = float(result.metrics.get("pfa_g", float("nan")))
        if not np.isfinite(midr) or not np.isfinite(pfa):
            raise RuntimeError("invalid undamped training summary metric")
        midr_values.append(midr)
        pfa_values.append(pfa)
    mean_story = np.mean(np.stack(story_rows), axis=0)
    max_story = max(float(np.max(mean_story)), 1e-12)
    mean_midr = float(np.mean(midr_values))
    mean_pfa = float(np.mean(pfa_values))
    local = np.zeros((n, 6), dtype=np.float32)
    mass_mean = float(np.mean(building.masses_kg))
    stiffness_mean = float(np.mean(building.stiffness_n_per_m))
    for index in range(n):
        local[index] = np.asarray(
            [
                index / max(1, n - 1),
                float(building.masses_kg[index]) / mass_mean,
                float(building.stiffness_n_per_m[index]) / stiffness_mean,
                float(mean_story[index]) / max_story,
                mean_midr,
                mean_pfa,
            ],
            dtype=np.float32,
        )
    return local


def sha256_balanced_order(
    identities: Iterable[str],
    *,
    seed: int,
    namespace: str,
    cycle_index: int,
) -> list[str]:
    """Version-stable balanced cycle order independent of Python/NumPy RNG versions."""

    values = [str(value) for value in identities]
    if len(values) != len(set(values)):
        raise ValueError("balanced-order identities must be unique")
    return sorted(
        values,
        key=lambda value: hashlib.sha256(
            f"{namespace}:{seed}:{cycle_index}:{value}".encode("utf-8")
        ).hexdigest(),
    )


class BalancedOracle:
    """One-call-per-world deterministic training oracle over a fixed record panel."""

    def __init__(
        self,
        evaluators: dict[str, FixedObjectiveEvaluator],
        *,
        seed: int,
        structural_state_id: str,
        audit: Callable[[str, DamperDesign, FixedObjectiveEvaluation], None] | None = None,
    ) -> None:
        if not evaluators:
            raise ValueError("balanced oracle requires at least one record evaluator")
        self.evaluators = dict(evaluators)
        self.seed = int(seed)
        self.state_id = str(structural_state_id)
        self.audit = audit
        self.completed = 0
        self._ids = sorted(self.evaluators)

    def _record_id(self) -> str:
        n = len(self._ids)
        cycle, position = divmod(self.completed, n)
        order = sha256_balanced_order(
            self._ids,
            seed=self.seed,
            namespace=f"training-record:{self.state_id}",
            cycle_index=cycle,
        )
        return order[position]

    def __call__(self, design: DamperDesign) -> ObjectiveRecord:
        record_id = self._record_id()
        evaluation = self.evaluators[record_id].evaluate(design)
        self.completed += 1
        if self.audit is not None:
            self.audit(record_id, design, evaluation)
        return evaluation.as_objective_record()


@dataclass(frozen=True)
class ValidationPanel:
    structural_state_id: str
    local_features: np.ndarray
    evaluators: dict[str, FixedObjectiveEvaluator]

    def __post_init__(self) -> None:
        features = np.asarray(self.local_features, dtype=np.float32)
        if features.ndim != 2 or features.shape[0] == 0 or features.shape[1] == 0:
            raise ValueError("validation local_features must be [stories, features]")
        if not self.evaluators:
            raise ValueError("validation panel requires record evaluators")
        object.__setattr__(self, "local_features", features)

    def evaluate_design(self, design: DamperDesign) -> list[FixedObjectiveEvaluation]:
        return [self.evaluators[key].evaluate(design) for key in sorted(self.evaluators)]

    def mean_record(self, design: DamperDesign) -> ObjectiveRecord:
        evaluations = self.evaluate_design(design)
        vectors = np.stack([item.vector for item in evaluations])
        scalars = np.asarray([item.scalar for item in evaluations], dtype=float)
        return ObjectiveRecord(
            vectors.mean(axis=0),
            float(scalars.mean()),
            all(item.converged for item in evaluations),
        )
