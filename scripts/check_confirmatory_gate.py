"""Fail-closed gate for confirmatory execution (expected BLOCKED before OSF registration)."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path
import sys

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_ground_motion_manifest import validate  # noqa: E402

HEX64 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _digest_ok(root: Path, relative: object, expected: object, label: str, reasons: list[str]) -> None:
    if not isinstance(relative, str) or not relative:
        reasons.append(f"{label} path is not recorded.")
        return
    path = root / relative
    if not path.is_file():
        reasons.append(f"{label} does not exist: {relative}.")
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not isinstance(expected, str) or expected.lower() != actual:
        reasons.append(f"{label} SHA-256 is absent or does not match.")


def check_gate(root: Path, gate_path: Path) -> tuple[bool, list[str]]:
    try:
        data = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return False, [f"Cannot read gate configuration: {exc}"]
    reasons: list[str] = []
    if data.get("osf_registration_status") != "public":
        reasons.append("OSF registration status is not public.")
    persistent_id = data.get("osf_registration_persistent_id")
    if not isinstance(persistent_id, str) or not persistent_id.strip():
        reasons.append("A public OSF registration identifier/DOI or persistent ID is absent.")

    manifest = data.get("ground_motion_manifest")
    if not isinstance(manifest, str) or not (root / manifest).is_file():
        reasons.append("A frozen real ground-motion manifest is absent.")
    else:
        manifest_errors = validate(root / manifest)
        reasons.extend(f"Ground-motion manifest: {error}" for error in manifest_errors)
        _digest_ok(root, manifest, data.get("ground_motion_manifest_sha256"), "Ground-motion manifest", reasons)

    _digest_ok(root, data.get("structural_world_manifest"), data.get("structural_world_manifest_sha256"), "Structural-world manifest", reasons)
    if data.get("structural_world_manifest_validated") is not True:
        reasons.append("Structural-world manifest is not validated.")
    seed_ledger = data.get("seed_ledger")
    if not isinstance(seed_ledger, str) or not (root / seed_ledger).is_file():
        reasons.append("Seed ledger is absent.")
    _digest_ok(root, data.get("frozen_numerical_config"), data.get("config_sha256"), "Frozen numerical config", reasons)

    source_sha = data.get("source_commit_sha")
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha, re.IGNORECASE):
        reasons.append("A full source commit SHA is absent or invalid.")
    else:
        current = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
        ).stdout.strip()
        if current != source_sha:
            reasons.append("Recorded source commit SHA does not match HEAD.")
    if data.get("tier_2_backend_validated") is not True:
        reasons.append("Tier-2 backend is not validated.")
    if data.get("confirmatory_runs_allowed") is not True:
        reasons.append("confirmatory_runs_allowed is false.")
    return not reasons, reasons


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, default=root / "open_science/confirmatory_gate_v0.8.0.yaml")
    args = parser.parse_args()
    ok, reasons = check_gate(root, args.gate)
    print(f"Confirmatory gate: {'PASS' if ok else 'BLOCKED'}")
    for reason in reasons:
        print(f"- {reason}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
