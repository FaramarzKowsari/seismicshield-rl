from __future__ import annotations
import numpy as np
from seismicshield_rl.physics.base import DamperDesign

try:
    from pettingzoo import ParallelEnv
    from gymnasium import spaces
except ImportError:  # pragma: no cover
    ParallelEnv = object
    spaces = None

class ParallelDamperDesignEnv(ParallelEnv):
    """One-shot cooperative MARL formulation: one simultaneous design action per story."""
    metadata = {"name": "seismicshield_parallel_design_v0"}

    def __init__(self, evaluator, slip_force_levels_n, max_dampers_per_story: int):
        if spaces is None:  # pragma: no cover
            raise RuntimeError("Install the 'marl' extra to use PettingZoo environments")
        self.evaluator = evaluator
        self.levels = np.asarray(slip_force_levels_n, dtype=float)
        self.n = evaluator.simulator.building.n_stories
        self.max_dampers = int(max_dampers_per_story)
        self.possible_agents = [f"story_{i+1}" for i in range(self.n)]
        self.agents = self.possible_agents[:]
        self._action_spaces = {a: spaces.MultiDiscrete([self.max_dampers+1, len(self.levels)]) for a in self.possible_agents}
        self._observation_spaces = {a: spaces.Box(-np.inf, np.inf, shape=(6,), dtype=np.float32) for a in self.possible_agents}

    def action_space(self, agent): return self._action_spaces[agent]
    def observation_space(self, agent): return self._observation_spaces[agent]

    def _obs_for(self, idx):
        b = self.evaluator.simulator.building
        ref_story = np.max(np.abs(self.evaluator.reference.story_drift_ratio), axis=0)
        return np.asarray([
            idx/max(1,self.n-1), b.masses_kg[idx]/b.masses_kg.mean(),
            b.stiffness_n_per_m[idx]/b.stiffness_n_per_m.mean(),
            ref_story[idx]/max(ref_story.max(),1e-12),
            self.evaluator.reference.metrics["midr"], self.evaluator.reference.metrics["pfa_g"],
        ], dtype=np.float32)

    def reset(self, seed=None, options=None):
        self.agents = self.possible_agents[:]
        return {a:self._obs_for(i) for i,a in enumerate(self.agents)}, {a:{} for a in self.agents}

    def step(self, actions):
        counts=np.zeros(self.n,dtype=int); slips=np.zeros(self.n,dtype=float)
        for i,a in enumerate(self.possible_agents):
            action=np.asarray(actions[a],dtype=int)
            counts[i]=action[0]; slips[i]=self.levels[action[1]]
        ev=self.evaluator.evaluate(DamperDesign(counts,slips))
        rewards={a:ev.reward for a in self.agents}
        terminations={a:True for a in self.agents}; truncations={a:False for a in self.agents}
        observations={a:self._obs_for(i) for i,a in enumerate(self.agents)}
        infos={a:ev.__dict__.copy() for a in self.agents}
        self.agents=[]
        return observations,rewards,terminations,truncations,infos
