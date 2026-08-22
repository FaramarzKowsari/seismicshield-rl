#!/usr/bin/env python3
"""Fail-closed validator for the v0.8.1 structural-world manifest."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import sys

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "src"))

from scripts.build_structural_world_manifest_v0_8_1 import (  # noqa: E402
    COLUMNS,
    _read_ground_manifest,
    build,
)
from seismicshield_rl.structural_worlds import DEFAULT_CONTRACT, load_contract  # noqa: E402


EXPECTED_PARTITION_WORLDS = {
    "training": 52 * 16,
    "validation": 20 * 16,
    "pilot": 16 * 16,
    "confirmatory": 48 * 16,
}


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return fields, rows


def validate(
    path: Path,
    *,
    ground_manifest: Path | None = None,
    contract_path: Path | None = None,
) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    ground_manifest = ground_manifest or root / "data/manifests/ground_motion_manifest.csv"
    contract_path = contract_path or root / DEFAULT_CONTRACT
    errors: list[str] = []
    try:
        fields, observed = _read(path)
        contract = load_contract(contract_path)
        expected = build(_read_ground_manifest(ground_manifest), contract)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return [str(exc)]

    if fields != list(COLUMNS):
        errors.append("structural-world manifest columns/order differ from the frozen schema")
    if len(observed) != len(expected):
        errors.append(f"expected {len(expected)} structural worlds, found {len(observed)}")
        return errors

    observed_ids = [row.get("world_id", "") for row in observed]
    if len(set(observed_ids)) != len(observed_ids):
        errors.append("structural-world manifest contains duplicate world_id values")

    partition_counts = Counter(row.get("partition", "") for row in observed)
    if dict(partition_counts) != EXPECTED_PARTITION_WORLDS:
        errors.append(
            f"partition world counts differ from frozen values: {dict(partition_counts)!r}"
        )

    event_partitions: dict[str, set[str]] = defaultdict(set)
    for row in observed:
        event_partitions[row.get("event_id", "")].add(row.get("partition", ""))
    if any(len(values) != 1 for values in event_partitions.values()):
        errors.append("an earthquake event crosses structural-world partitions")

    for index, (actual, frozen) in enumerate(zip(observed, expected, strict=True), start=2):
        if actual != frozen:
            differing = [key for key in COLUMNS if actual.get(key, "") != frozen.get(key, "")]
            errors.append(
                f"row {index} differs from deterministic frozen construction in: {', '.join(differing)}"
            )
            if len(errors) >= 20:
                errors.append("additional row mismatches suppressed")
                break
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=root / "data/manifests/structural_world_manifest.csv",
    )
    parser.add_argument(
        "--ground-manifest",
        type=Path,
        default=root / "data/manifests/ground_motion_manifest.csv",
    )
    parser.add_argument("--contract", type=Path, default=root / DEFAULT_CONTRACT)
    args = parser.parse_args()
    errors = validate(
        args.path,
        ground_manifest=args.ground_manifest,
        contract_path=args.contract,
    )
    if errors:
        print("Structural-world manifest v0.8.1: INVALID")
        for error in errors:
            print(f"- {error}")
        return 2
    print("Structural-world manifest v0.8.1: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
