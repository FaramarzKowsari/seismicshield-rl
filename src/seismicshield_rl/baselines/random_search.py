from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from seismicshield_rl.physics.base import DamperDesign

@dataclass
class SearchRecord:
    design: DamperDesign
    objective: float
    reward: float


def random_search(evaluator, *, n_stories: int, max_dampers_per_story: int, slip_force_levels_n, budget: int, seed: int) -> SearchRecord:
    rng = np.random.default_rng(seed)
    levels = np.asarray(slip_force_levels_n, dtype=float)
    best = None
    for _ in range(int(budget)):
        counts = rng.integers(0, max_dampers_per_story + 1, size=n_stories)
        slips = rng.choice(levels, size=n_stories)
        design = DamperDesign(counts.astype(int), slips.astype(float))
        ev = evaluator.evaluate(design)
        rec = SearchRecord(design, ev.objective, ev.reward)
        if best is None or rec.objective < best.objective:
            best = rec
    if best is None:
        raise ValueError("budget must be >= 1")
    return best
