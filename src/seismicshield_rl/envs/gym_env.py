from __future__ import annotations
import numpy as np
from seismicshield_rl.physics.base import DamperDesign

try:
    import gymnasium as gym
except ImportError:  # pragma: no cover
    gym = None

if gym is not None:
    class SingleAgentDesignEnv(gym.Env):
        """One-step whole-building design environment for PPO/debugging baselines."""
        metadata = {"render_modes": []}
        def __init__(self, evaluator, slip_force_levels_n, max_dampers_per_story: int):
            super().__init__()
            self.evaluator = evaluator
            self.levels = np.asarray(slip_force_levels_n, dtype=float)
            self.n = evaluator.simulator.building.n_stories
            self.max_dampers = int(max_dampers_per_story)
            nvec = []
            for _ in range(self.n): nvec.extend([self.max_dampers + 1, len(self.levels)])
            self.action_space = gym.spaces.MultiDiscrete(nvec)
            self.observation_space = gym.spaces.Box(-np.inf, np.inf, shape=(self.n*3,), dtype=np.float32)

        def _obs(self):
            b = self.evaluator.simulator.building
            return np.concatenate([
                b.masses_kg / b.masses_kg.mean(),
                b.stiffness_n_per_m / b.stiffness_n_per_m.mean(),
                np.linspace(0, 1, self.n),
            ]).astype(np.float32)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            return self._obs(), {}

        def step(self, action):
            a = np.asarray(action, dtype=int).reshape(self.n, 2)
            counts = a[:,0]
            slips = self.levels[a[:,1]]
            ev = self.evaluator.evaluate(DamperDesign(counts, slips))
            info = ev.__dict__.copy()
            return self._obs(), ev.reward, True, False, info
else:
    class SingleAgentDesignEnv:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Install the 'marl' extra to use Gymnasium environments")
