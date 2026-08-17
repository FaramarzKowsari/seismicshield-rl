from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .physics.base import DamperDesign, GroundMotion
from .physics.metrics import normalized_design_cost, scalarized_objective

@dataclass
class Evaluation:
    cost: float
    midr: float
    pfa_g: float
    midr_ratio: float
    pfa_ratio: float
    objective: float
    reward: float
    converged: bool

class DesignEvaluator:
    def __init__(self, simulator, ground_motion: GroundMotion, *, max_dampers_per_story: int, max_slip_force_n: float, weights=(0.2,0.45,0.35)):
        self.simulator = simulator
        self.gm = ground_motion
        self.max_dampers = int(max_dampers_per_story)
        self.max_slip = float(max_slip_force_n)
        self.weights = tuple(float(x) for x in weights)
        n = simulator.building.n_stories
        zero = DamperDesign(np.zeros(n, dtype=int), np.zeros(n, dtype=float))
        self.reference = simulator.simulate(zero, ground_motion)
        if not self.reference.converged:
            raise RuntimeError("undamped reference did not converge")

    def evaluate(self, design: DamperDesign) -> Evaluation:
        result = self.simulator.simulate(design, self.gm)
        cost = normalized_design_cost(design, max_dampers_per_story=self.max_dampers, max_slip_force_n=self.max_slip)
        midr_ratio = result.metrics["midr"] / max(self.reference.metrics["midr"], 1e-12)
        pfa_ratio = result.metrics["pfa_g"] / max(self.reference.metrics["pfa_g"], 1e-12)
        obj = scalarized_objective(cost=cost, midr_ratio=midr_ratio, pfa_ratio=pfa_ratio, weights=self.weights)
        if not result.converged:
            obj += 10.0
        return Evaluation(cost=cost, midr=result.metrics["midr"], pfa_g=result.metrics["pfa_g"],
                          midr_ratio=midr_ratio, pfa_ratio=pfa_ratio, objective=obj,
                          reward=-obj, converged=result.converged)
