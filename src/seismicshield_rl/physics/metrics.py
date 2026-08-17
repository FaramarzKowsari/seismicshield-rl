from __future__ import annotations
import numpy as np
from .base import DamperDesign


def normalized_design_cost(design: DamperDesign, *, max_dampers_per_story: int, max_slip_force_n: float) -> float:
    if max_dampers_per_story <= 0 or max_slip_force_n <= 0:
        raise ValueError("normalization constants must be positive")
    n = design.counts.size
    count_term = float(np.sum(design.counts)) / (n * max_dampers_per_story)
    capacity_term = float(np.sum(design.total_story_capacity_n)) / (n * max_dampers_per_story * max_slip_force_n)
    return 0.5 * count_term + 0.5 * capacity_term


def scalarized_objective(*, cost: float, midr_ratio: float, pfa_ratio: float, weights=(0.2, 0.45, 0.35)) -> float:
    w = np.asarray(weights, dtype=float)
    if w.shape != (3,) or np.any(w < 0) or not np.isclose(w.sum(), 1.0):
        raise ValueError("weights must be three non-negative values summing to 1")
    return float(w @ np.asarray([cost, midr_ratio, pfa_ratio], dtype=float))
