from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Iterable, Sequence

import numpy as np

REFERENCE_POINT = np.asarray([1.05, 5.0, 5.0], dtype=float)
COST_CEILINGS = (0.25, 0.50, 0.75, 1.00)
BOOTSTRAP_REPETITIONS = 20_000
BOOTSTRAP_SEED = 998_035_145


@dataclass(frozen=True)
class InferenceResult:
    effect: float
    ci_low: float
    ci_high: float
    p_raw: float


def _points_array(points: Iterable[Sequence[float]]) -> np.ndarray:
    array = np.asarray(list(points), dtype=float)
    if array.size == 0:
        return np.empty((0, 3), dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError("objective points must have shape [n, 3]")
    if not np.all(np.isfinite(array)):
        raise ValueError("objective points must be finite")
    return array


def nondominated(points: Iterable[Sequence[float]]) -> np.ndarray:
    """Return unique weakly nondominated minimization points in lexical order."""
    array = _points_array(points)
    if not array.size:
        return array
    unique = np.unique(array, axis=0)
    keep = np.ones(unique.shape[0], dtype=bool)
    for i in range(unique.shape[0]):
        for j in range(unique.shape[0]):
            if i == j:
                continue
            if np.all(unique[j] <= unique[i]) and np.any(unique[j] < unique[i]):
                keep[i] = False
                break
    kept = unique[keep]
    if not kept.size:
        return kept.reshape(0, 3)
    order = np.lexsort((kept[:, 2], kept[:, 1], kept[:, 0]))
    return kept[order]


def hypervolume_3d(
    points: Iterable[Sequence[float]],
    reference: Sequence[float] = REFERENCE_POINT,
) -> float:
    """Exact union volume of minimization boxes for the frozen <=9-point method fronts."""
    reference_array = np.asarray(reference, dtype=float)
    if reference_array.shape != (3,) or not np.all(np.isfinite(reference_array)):
        raise ValueError("reference point must be a finite 3-vector")
    array = nondominated(points)
    if not array.size:
        return 0.0
    # A minimization point outside the reference box has no positive-volume box.
    array = array[np.all(array <= reference_array, axis=1)]
    if not array.size:
        return 0.0
    if array.shape[0] > 20:
        raise ValueError("inclusion-exclusion hypervolume is intentionally limited to <=20 points")
    volume = 0.0
    indices = range(array.shape[0])
    for subset_size in range(1, array.shape[0] + 1):
        sign = 1.0 if subset_size % 2 else -1.0
        for subset in combinations(indices, subset_size):
            lower = np.max(array[list(subset)], axis=0)
            extent = reference_array - lower
            if np.any(extent <= 0.0):
                continue
            volume += sign * float(np.prod(extent))
    # Numerical cancellation at duplicated/touching faces may produce tiny negatives.
    return max(0.0, float(volume))


def select_cost_slice(
    rows: Iterable[dict],
    *,
    ceiling: float,
    metric: str,
) -> dict:
    """Select one discrete design under a frozen cost ceiling, with no interpolation."""
    if metric not in {"MIDR", "PFA_g"}:
        raise ValueError("metric must be MIDR or PFA_g")
    candidates = [row for row in rows if float(row["normalized_cost"]) <= float(ceiling)]
    if not candidates:
        raise ValueError(f"no eligible design at cost ceiling {ceiling}")
    if metric == "MIDR":
        key = lambda row: (
            float(row["MIDR"]),
            float(row["PFA_g"]),
            float(row["normalized_cost"]),
            int(row.get("seed", -1)),
        )
    else:
        key = lambda row: (
            float(row["PFA_g"]),
            float(row["MIDR"]),
            float(row["normalized_cost"]),
            int(row.get("seed", -1)),
        )
    return min(candidates, key=key)


def event_mean(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("event mean requires finite non-empty values")
    return float(np.mean(array))


def event_median(values: Iterable[float]) -> float:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("event median requires finite non-empty values")
    return float(np.median(array))


def bootstrap_mean_ci(
    event_differences: Sequence[float],
    *,
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    differences = np.asarray(event_differences, dtype=float)
    if differences.ndim != 1 or differences.size == 0 or not np.all(np.isfinite(differences)):
        raise ValueError("event differences must be a finite non-empty vector")
    if repetitions <= 0:
        raise ValueError("bootstrap repetitions must be positive")
    rng = np.random.default_rng(int(seed))
    n = differences.size
    # Draw in moderate chunks to avoid a large temporary matrix when reused outside n=12.
    means = np.empty(int(repetitions), dtype=float)
    chunk = 4096
    offset = 0
    while offset < repetitions:
        size = min(chunk, repetitions - offset)
        indices = rng.integers(0, n, size=(size, n))
        means[offset : offset + size] = differences[indices].mean(axis=1)
        offset += size
    low, high = np.percentile(means, [2.5, 97.5], method="linear")
    return float(low), float(high)


def exact_sign_flip_pvalue(event_differences: Sequence[float]) -> float:
    """Exact two-sided paired sign-flip p-value over all 2^n patterns."""
    differences = np.asarray(event_differences, dtype=float)
    if differences.ndim != 1 or differences.size == 0 or not np.all(np.isfinite(differences)):
        raise ValueError("event differences must be a finite non-empty vector")
    if differences.size > 20:
        raise ValueError("exact sign-flip enumeration is limited to <=20 clusters")
    observed = abs(float(np.mean(differences)))
    exceed = 0
    total = 0
    tolerance = 1e-15
    for signs in product((-1.0, 1.0), repeat=differences.size):
        statistic = abs(float(np.mean(differences * np.asarray(signs, dtype=float))))
        if statistic + tolerance >= observed:
            exceed += 1
        total += 1
    return float(exceed / total)


def paired_event_inference(event_differences: Sequence[float]) -> InferenceResult:
    differences = np.asarray(event_differences, dtype=float)
    if differences.size != 12:
        raise ValueError("primary confirmatory inference requires exactly 12 event clusters")
    low, high = bootstrap_mean_ci(differences)
    return InferenceResult(
        effect=float(np.mean(differences)),
        ci_low=low,
        ci_high=high,
        p_raw=exact_sign_flip_pvalue(differences),
    )


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Standard Holm step-down adjusted p-values with stable lexical tie ordering."""
    if not p_values:
        return {}
    for key, value in p_values.items():
        if not np.isfinite(value) or value < 0.0 or value > 1.0:
            raise ValueError(f"invalid p-value for {key!r}")
    ordered = sorted(p_values, key=lambda key: (float(p_values[key]), str(key)))
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, key in enumerate(ordered):
        candidate = min(1.0, (m - rank) * float(p_values[key]))
        running = max(running, candidate)
        adjusted[key] = min(1.0, running)
    return {key: adjusted[key] for key in sorted(adjusted)}


def orient_hv_difference(mappo: float, comparator: float) -> float:
    return float(mappo - comparator)


def orient_response_difference(mappo: float, comparator: float) -> float:
    return float(comparator - mappo)
