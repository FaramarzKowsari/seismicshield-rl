from __future__ import annotations
import numpy as np
from seismicshield_rl.physics.base import DamperDesign


def no_damper(n_stories: int) -> DamperDesign:
    return DamperDesign(np.zeros(n_stories, dtype=int), np.zeros(n_stories, dtype=float))


def uniform_design(n_stories: int, *, count: int = 1, slip_force_n: float = 100_000.0) -> DamperDesign:
    return DamperDesign(np.full(n_stories, count, dtype=int), np.full(n_stories, slip_force_n, dtype=float))


def drift_proportional_design(reference_result, *, total_dampers: int, slip_force_n: float, max_per_story: int) -> DamperDesign:
    demand = np.max(np.abs(reference_result.story_drift_ratio), axis=0)
    n = demand.size
    counts = np.zeros(n, dtype=int)
    if total_dampers <= 0 or demand.sum() <= 0:
        return DamperDesign(counts, np.full(n, slip_force_n, dtype=float))
    for _ in range(total_dampers):
        eligible = counts < max_per_story
        if not np.any(eligible): break
        score = np.where(eligible, demand / (counts + 1), -np.inf)
        counts[int(np.argmax(score))] += 1
    return DamperDesign(counts, np.full(n, slip_force_n, dtype=float))
