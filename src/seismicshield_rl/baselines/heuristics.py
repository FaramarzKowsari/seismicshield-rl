from __future__ import annotations
import numpy as np
from seismicshield_rl.physics.base import DamperDesign


def no_damper(n_stories: int) -> DamperDesign:
    return DamperDesign(np.zeros(n_stories, dtype=int), np.zeros(n_stories, dtype=float))


def uniform_design(
    n_stories: int, *, count: int = 1, slip_force_n: float = 100_000.0
) -> DamperDesign:
    return DamperDesign(
        np.full(n_stories, count, dtype=int),
        np.full(n_stories, slip_force_n, dtype=float),
    )


def drift_proportional_from_demand(
    demand,
    *,
    total_dampers: int,
    slip_force_n: float,
    max_per_story: int,
) -> DamperDesign:
    """Allocate using a precomputed non-negative story-demand vector.

    Confirmatory v0.8.2 uses an aggregate demand vector derived only from the 52
    training records. This helper makes that information boundary explicit instead
    of requiring a record-specific SimulationResult at validation/test time.
    """
    demand = np.asarray(demand, dtype=float)
    if demand.ndim != 1 or demand.size == 0 or not np.all(np.isfinite(demand)):
        raise ValueError("demand must be a finite non-empty 1D vector")
    if np.any(demand < 0):
        raise ValueError("demand must be non-negative")
    if max_per_story < 0:
        raise ValueError("max_per_story must be non-negative")
    n = demand.size
    counts = np.zeros(n, dtype=int)
    if total_dampers <= 0 or demand.sum() <= 0:
        return DamperDesign(counts, np.full(n, slip_force_n, dtype=float))
    for _ in range(int(total_dampers)):
        eligible = counts < int(max_per_story)
        if not np.any(eligible):
            break
        score = np.where(eligible, demand / (counts + 1), -np.inf)
        # np.argmax provides the frozen lowest-story-index tie break.
        counts[int(np.argmax(score))] += 1
    return DamperDesign(counts, np.full(n, slip_force_n, dtype=float))


def drift_proportional_design(
    reference_result,
    *,
    total_dampers: int,
    slip_force_n: float,
    max_per_story: int,
) -> DamperDesign:
    demand = np.max(np.abs(reference_result.story_drift_ratio), axis=0)
    return drift_proportional_from_demand(
        demand,
        total_dampers=total_dampers,
        slip_force_n=slip_force_n,
        max_per_story=max_per_story,
    )
