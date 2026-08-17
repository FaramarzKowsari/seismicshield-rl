from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import numpy as np

@dataclass(frozen=True)
class GroundMotion:
    id: str
    time_s: np.ndarray
    accel_mps2: np.ndarray
    source: str = "synthetic"

    def __post_init__(self) -> None:
        if self.time_s.ndim != 1 or self.accel_mps2.ndim != 1:
            raise ValueError("ground-motion arrays must be 1D")
        if self.time_s.size != self.accel_mps2.size or self.time_s.size < 3:
            raise ValueError("ground-motion arrays must have equal length >= 3")
        if not np.all(np.diff(self.time_s) > 0):
            raise ValueError("time_s must be strictly increasing")

@dataclass(frozen=True)
class DamperDesign:
    counts: np.ndarray
    slip_force_n: np.ndarray

    def __post_init__(self) -> None:
        if self.counts.ndim != 1 or self.slip_force_n.ndim != 1:
            raise ValueError("design arrays must be 1D")
        if self.counts.size != self.slip_force_n.size:
            raise ValueError("design arrays must have equal length")
        if np.any(self.counts < 0) or np.any(self.slip_force_n < 0):
            raise ValueError("damper count and slip force must be non-negative")

    @property
    def total_story_capacity_n(self) -> np.ndarray:
        return self.counts.astype(float) * self.slip_force_n

@dataclass
class SimulationResult:
    time_s: np.ndarray
    displacement_m: np.ndarray
    velocity_mps: np.ndarray
    relative_accel_mps2: np.ndarray
    absolute_accel_mps2: np.ndarray
    story_drift_ratio: np.ndarray
    damper_force_n: np.ndarray
    metrics: dict[str, float]
    converged: bool = True
    backend: str = "unknown"

class StructuralBackend(Protocol):
    def simulate(self, design: DamperDesign, ground_motion: GroundMotion) -> SimulationResult: ...
