from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml
import numpy as np

@dataclass(frozen=True)
class BuildingConfig:
    id: str
    story_height_m: float
    masses_kg: np.ndarray
    stiffness_n_per_m: np.ndarray
    damping_ratio: float = 0.05
    notes: str = ""

    @property
    def n_stories(self) -> int:
        return int(self.masses_kg.size)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BuildingConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        masses = np.asarray(data["masses_kg"], dtype=float)
        stiffness = np.asarray(data["stiffness_n_per_m"], dtype=float)
        if masses.ndim != 1 or stiffness.ndim != 1 or masses.size != stiffness.size:
            raise ValueError("masses_kg and stiffness_n_per_m must be equal-length 1D arrays")
        if np.any(masses <= 0) or np.any(stiffness <= 0):
            raise ValueError("mass and stiffness values must be positive")
        return cls(
            id=str(data["id"]), story_height_m=float(data["story_height_m"]),
            masses_kg=masses, stiffness_n_per_m=stiffness,
            damping_ratio=float(data.get("damping_ratio", 0.05)), notes=str(data.get("notes", "")),
        )
