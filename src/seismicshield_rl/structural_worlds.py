from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import yaml

from .config import BuildingConfig


DEFAULT_CONTRACT = Path("open_science/structural_world_freeze_v0.8.1.yaml")
DIMENSIONS = ("mass_scale", "stiffness_scale", "damping_ratio", "damper_capacity_scale")


@dataclass(frozen=True)
class StructuralRealization:
    realization_id: str
    is_nominal: bool
    mass_scale: float
    stiffness_scale: float
    damping_ratio: float
    damper_capacity_scale: float


def load_contract(path: str | Path = DEFAULT_CONTRACT) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("structural-world contract must be a YAML mapping")
    return data


def _unit_interval_from_sha256(text: str) -> float:
    # 52 bits fit exactly in a Python float mantissa and provide deterministic jitter.
    integer = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:13], 16)
    return integer / float(16**13)


def deterministic_lhs(seed: int, n: int, dimensions: Iterable[str] = DIMENSIONS) -> dict[str, list[float]]:
    """Return a version-stable SHA-256 Latin hypercube on [0, 1).

    Each dimension uses every stratum exactly once. Both the stratum permutation and
    within-stratum jitter are derived from SHA-256 rather than a library RNG so the
    frozen seed has identical meaning across NumPy/Python releases.
    """
    if n <= 0:
        raise ValueError("Latin-hypercube sample count must be positive")
    result: dict[str, list[float]] = {}
    for dimension in tuple(dimensions):
        strata = sorted(
            range(n),
            key=lambda s: hashlib.sha256(
                f"{seed}:perm:{dimension}:{s}".encode("utf-8")
            ).hexdigest(),
        )
        points: list[float] = []
        for index, stratum in enumerate(strata):
            jitter = _unit_interval_from_sha256(f"{seed}:jitter:{dimension}:{index}")
            points.append((stratum + jitter) / n)
        result[dimension] = points
    return result


def _scale(unit_value: float, minimum: float, maximum: float) -> float:
    return float(minimum + unit_value * (maximum - minimum))


def realizations_from_contract(contract: dict) -> list[StructuralRealization]:
    uncertainty = contract["structural_uncertainty"]
    seed = int(uncertainty["lhs_seed"])
    n = int(uncertainty["realizations_per_height"]["latin_hypercube"])
    dimensions = uncertainty["dimensions"]
    lhs = deterministic_lhs(seed, n)
    rows = [
        StructuralRealization(
            realization_id="nominal",
            is_nominal=True,
            mass_scale=1.0,
            stiffness_scale=1.0,
            damping_ratio=float(contract["canonical_archetype"]["nominal_damping_ratio"]),
            damper_capacity_scale=1.0,
        )
    ]
    for index in range(n):
        values = {}
        for dimension in DIMENSIONS:
            bounds = dimensions[dimension]
            values[dimension] = _scale(
                lhs[dimension][index], float(bounds["minimum"]), float(bounds["maximum"])
            )
        rows.append(
            StructuralRealization(
                realization_id=f"lhs-{index + 1}",
                is_nominal=False,
                mass_scale=values["mass_scale"],
                stiffness_scale=values["stiffness_scale"],
                damping_ratio=values["damping_ratio"],
                damper_capacity_scale=values["damper_capacity_scale"],
            )
        )
    return rows


def nominal_profiles(n_stories: int, contract: dict) -> tuple[np.ndarray, np.ndarray]:
    if n_stories <= 0:
        raise ValueError("n_stories must be positive")
    archetype = contract["canonical_archetype"]
    mass = archetype["nominal_mass_profile"]
    stiffness = archetype["nominal_stiffness_profile"]
    normalized = np.linspace(0.0, 1.0, n_stories, dtype=float) if n_stories > 1 else np.zeros(1)
    masses = float(mass["base_floor_mass_kg"]) * (
        1.0 - (1.0 - float(mass["roof_to_base_ratio"])) * normalized
    )
    stiffnesses = float(stiffness["base_story_stiffness_n_per_m"]) * (
        1.0 - (1.0 - float(stiffness["roof_to_base_ratio"])) * normalized
    )
    return masses, stiffnesses


def building_for_world(
    n_stories: int,
    realization: StructuralRealization,
    contract: dict,
) -> BuildingConfig:
    heights = {int(value) for value in contract["canonical_archetype"]["building_heights_stories"]}
    if n_stories not in heights:
        raise ValueError(f"building height {n_stories} is outside the frozen structural contract")
    masses, stiffness = nominal_profiles(n_stories, contract)
    archetype = contract["canonical_archetype"]
    return BuildingConfig(
        id=f"{archetype['id']}-{n_stories}story-{realization.realization_id}",
        story_height_m=float(archetype["story_height_m"]),
        masses_kg=masses * realization.mass_scale,
        stiffness_n_per_m=stiffness * realization.stiffness_scale,
        damping_ratio=realization.damping_ratio,
        notes="Synthetic canonical preregistered benchmark archetype; not calibrated to a real building.",
    )


def world_id(
    source: str,
    event_id: str,
    record_id: str,
    n_stories: int,
    realization_id: str,
    contract: dict,
) -> str:
    salt = str(contract["world_manifest"]["world_id_salt"])
    identity = ":".join(
        (source, event_id, record_id, str(n_stories), realization_id)
    )
    return hashlib.sha256(f"{salt}:{identity}".encode("utf-8")).hexdigest()
