#!/usr/bin/env python3
"""Materialize the frozen structural-world grid without running a simulator."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seismicshield_rl.structural_worlds import (  # noqa: E402
    DEFAULT_CONTRACT,
    load_contract,
    realizations_from_contract,
    world_id,
)


COLUMNS = (
    "world_id",
    "source",
    "event_id",
    "record_id",
    "partition",
    "building_height_stories",
    "realization_id",
    "is_nominal",
    "mass_scale",
    "stiffness_scale",
    "damping_ratio",
    "damper_capacity_scale",
    "lhs_seed",
    "archetype_id",
)


def _read_ground_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"source", "event_id", "record_id", "partition"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"ground-motion manifest missing: {', '.join(sorted(missing))}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if len(rows) != 136:
        raise ValueError(f"ground-motion manifest must contain 136 rows; found {len(rows)}")
    identities = {(row["source"], row["event_id"], row["record_id"]) for row in rows}
    if len(identities) != len(rows):
        raise ValueError("ground-motion manifest contains duplicate record identities")
    return rows


def build(ground_rows: list[dict[str, str]], contract: dict) -> list[dict[str, str]]:
    heights = [int(value) for value in contract["canonical_archetype"]["building_heights_stories"]]
    realizations = realizations_from_contract(contract)
    seed = int(contract["structural_uncertainty"]["lhs_seed"])
    archetype_id = str(contract["canonical_archetype"]["id"])
    output: list[dict[str, str]] = []
    for ground in ground_rows:
        for height in heights:
            for realization in realizations:
                output.append(
                    {
                        "world_id": world_id(
                            ground["source"],
                            ground["event_id"],
                            ground["record_id"],
                            height,
                            realization.realization_id,
                            contract,
                        ),
                        "source": ground["source"],
                        "event_id": ground["event_id"],
                        "record_id": ground["record_id"],
                        "partition": ground["partition"],
                        "building_height_stories": str(height),
                        "realization_id": realization.realization_id,
                        "is_nominal": str(realization.is_nominal).lower(),
                        "mass_scale": f"{realization.mass_scale:.17g}",
                        "stiffness_scale": f"{realization.stiffness_scale:.17g}",
                        "damping_ratio": f"{realization.damping_ratio:.17g}",
                        "damper_capacity_scale": f"{realization.damper_capacity_scale:.17g}",
                        "lhs_seed": str(seed),
                        "archetype_id": archetype_id,
                    }
                )
    expected = int(contract["world_manifest"]["total_worlds"])
    if len(output) != expected:
        raise ValueError(f"structural-world count mismatch: expected {expected}, found {len(output)}")
    confirmatory = sum(row["partition"] == "confirmatory" for row in output)
    expected_confirmatory = int(contract["world_manifest"]["confirmatory_worlds"])
    if confirmatory != expected_confirmatory:
        raise ValueError(
            f"confirmatory structural-world count mismatch: expected {expected_confirmatory}, found {confirmatory}"
        )
    if len({row["world_id"] for row in output}) != len(output):
        raise ValueError("structural-world IDs are not unique")
    return output


def write(rows: list[dict[str, str]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-manifest",
        type=Path,
        default=root / "data/manifests/ground_motion_manifest.csv",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=root / DEFAULT_CONTRACT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "data/manifests/structural_world_manifest.csv",
    )
    args = parser.parse_args()
    try:
        contract = load_contract(args.contract)
        rows = build(_read_ground_manifest(args.ground_manifest), contract)
        digest = write(rows, args.output)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote structural-world manifest: {args.output}")
    print(f"Rows: {len(rows)}")
    print("Confirmatory worlds: 768")
    print(f"SHA-256: {digest}")
    print("No structural simulation was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
