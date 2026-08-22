#!/usr/bin/env python3
"""One-command, fail-closed finalization of the confirmatory execution gate.

This script is intentionally the only step that must run on the workstation holding the
frozen ground-motion manifest. It never reads raw waveform files. It verifies the known
ground-motion manifest digest, materializes the deterministic structural-world manifest,
updates the gate, creates the final source tag, re-runs the gate, and optionally pushes the
commit and tag atomically.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_structural_world_manifest_v0_8_1 import (  # noqa: E402
    _read_ground_manifest,
    build as build_structural_manifest,
    write as write_structural_manifest,
)
from scripts.check_confirmatory_gate import check_gate  # noqa: E402
from scripts.validate_ground_motion_manifest_v0_8_1 import validate as validate_ground  # noqa: E402
from scripts.validate_structural_world_manifest_v0_8_1 import (  # noqa: E402
    validate as validate_structural,
)
from seismicshield_rl.structural_worlds import DEFAULT_CONTRACT, load_contract  # noqa: E402

EXPECTED_GROUND_MANIFEST_SHA256 = "0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b"
FINAL_SOURCE_TAG = "confirmatory-v0.8.1-final"
ALLOWED_DIRTY_PATHS = {
    "data/manifests/ground_motion_manifest.csv",
    "data/manifests/ground_motion_manifest.csv.sha256",
    "data/manifests/structural_world_manifest.csv",
    "data/manifests/structural_world_manifest.csv.sha256",
    "open_science/confirmatory_gate_v0.8.0.yaml",
}


def _run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=check,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status_paths(root: Path) -> set[str]:
    result = _run_git(root, "status", "--porcelain=v1")
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        payload = line[3:]
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        paths.add(payload.replace("\\", "/"))
    return paths


def _assert_only_allowed_dirty_paths(root: Path) -> None:
    unexpected = sorted(_status_paths(root) - ALLOWED_DIRTY_PATHS)
    if unexpected:
        joined = "\n  - ".join(unexpected)
        raise RuntimeError(
            "Refusing to finalize with unrelated working-tree changes. Unexpected paths:\n"
            f"  - {joined}"
        )


def _require_synced_main(root: Path) -> None:
    branch = _run_git(root, "branch", "--show-current").stdout.strip()
    if branch != "main":
        raise RuntimeError(f"Finalization must run from local main; current branch is {branch!r}.")
    _run_git(root, "fetch", "origin", "main", "--tags")
    local = _run_git(root, "rev-parse", "HEAD").stdout.strip()
    remote = _run_git(root, "rev-parse", "origin/main").stdout.strip()
    if local != remote:
        raise RuntimeError(
            "Local main is not exactly synchronized with origin/main. Pull the latest main before finalization."
        )
    existing = _run_git(root, "rev-parse", "--verify", f"refs/tags/{FINAL_SOURCE_TAG}", check=False)
    if existing.returncode == 0:
        raise RuntimeError(f"Final source tag {FINAL_SOURCE_TAG!r} already exists; refusing to move it.")


def _verify_ground_manifest(root: Path) -> Path:
    path = root / "data/manifests/ground_motion_manifest.csv"
    if not path.is_file():
        raise RuntimeError(f"Frozen ground-motion manifest is missing: {path}")
    actual = _sha256(path)
    if actual != EXPECTED_GROUND_MANIFEST_SHA256:
        raise RuntimeError(
            "Ground-motion manifest digest mismatch. "
            f"Expected {EXPECTED_GROUND_MANIFEST_SHA256}, found {actual}."
        )
    errors = validate_ground(path)
    if errors:
        raise RuntimeError("Ground-motion manifest validation failed:\n- " + "\n- ".join(errors))
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{actual}  {path.name}\n", encoding="utf-8")
    return path


def _materialize_structural_manifest(root: Path, ground_path: Path) -> tuple[Path, str]:
    contract_path = root / DEFAULT_CONTRACT
    contract = load_contract(contract_path)
    rows = build_structural_manifest(_read_ground_manifest(ground_path), contract)
    output = root / "data/manifests/structural_world_manifest.csv"
    digest = write_structural_manifest(rows, output)
    errors = validate_structural(output)
    if errors:
        raise RuntimeError("Structural-world manifest validation failed:\n- " + "\n- ".join(errors))
    if len(rows) != 2176:
        raise RuntimeError(f"Expected 2176 structural worlds; found {len(rows)}.")
    confirmatory = sum(row["partition"] == "confirmatory" for row in rows)
    if confirmatory != 768:
        raise RuntimeError(f"Expected 768 confirmatory structural worlds; found {confirmatory}.")
    return output, digest


def _update_gate(root: Path, structural_sha256: str) -> Path:
    gate_path = root / "open_science/confirmatory_gate_v0.8.0.yaml"
    data = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Confirmatory gate YAML is not a mapping.")
    algorithm_bundle = data.get("confirmatory_algorithm_bundle")
    algorithm_sha = data.get("confirmatory_algorithm_bundle_sha256")
    if not isinstance(algorithm_bundle, str) or not (root / algorithm_bundle).is_file():
        raise RuntimeError("Validated confirmatory algorithm bundle is absent.")
    if _sha256(root / algorithm_bundle) != algorithm_sha:
        raise RuntimeError("Confirmatory algorithm bundle SHA-256 no longer matches the gate.")
    if data.get("confirmatory_algorithm_bundle_validated") is not True:
        raise RuntimeError("Confirmatory algorithm bundle is not marked validated.")
    if data.get("tier_2_backend_validated") is not True:
        raise RuntimeError("Tier-2 backend is not marked validated.")
    if data.get("ground_motion_manifest_sha256") != EXPECTED_GROUND_MANIFEST_SHA256:
        raise RuntimeError("Gate ground-motion digest does not match the frozen local manifest.")

    data["structural_world_manifest"] = "data/manifests/structural_world_manifest.csv"
    data["structural_world_manifest_sha256"] = structural_sha256
    data["structural_world_manifest_validated"] = True
    data["source_git_tag"] = FINAL_SOURCE_TAG
    data["confirmatory_runs_allowed"] = True
    gate_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return gate_path


def _preflight_gate(root: Path, gate_path: Path) -> None:
    ok, reasons = check_gate(root, gate_path)
    if ok:
        raise RuntimeError("Gate unexpectedly passed before the final source tag was created.")
    allowed = {
        f"Required source Git tag '{FINAL_SOURCE_TAG}' does not exist.",
    }
    unexpected = [reason for reason in reasons if reason not in allowed]
    if unexpected:
        raise RuntimeError("Pre-tag gate has unexpected blockers:\n- " + "\n- ".join(unexpected))


def _commit_tag_and_verify(root: Path) -> str:
    paths = [
        "data/manifests/ground_motion_manifest.csv",
        "data/manifests/ground_motion_manifest.csv.sha256",
        "data/manifests/structural_world_manifest.csv",
        "data/manifests/structural_world_manifest.csv.sha256",
        "open_science/confirmatory_gate_v0.8.0.yaml",
    ]
    _run_git(root, "add", "--", *paths)
    staged = _run_git(root, "diff", "--cached", "--name-only").stdout.splitlines()
    if set(staged) != set(paths):
        raise RuntimeError(
            "Staged finalization set is not exact; refusing commit. Staged: " + ", ".join(staged)
        )
    _run_git(root, "commit", "-m", "Freeze confirmatory execution gate v0.8.1")
    commit_sha = _run_git(root, "rev-parse", "HEAD").stdout.strip()
    _run_git(
        root,
        "tag",
        "-a",
        FINAL_SOURCE_TAG,
        "-m",
        "SeismicShield-RL v0.8.1 final confirmatory execution freeze",
    )
    gate_path = root / "open_science/confirmatory_gate_v0.8.0.yaml"
    ok, reasons = check_gate(root, gate_path)
    if not ok:
        _run_git(root, "tag", "-d", FINAL_SOURCE_TAG, check=False)
        raise RuntimeError("Final gate did not pass after commit/tag:\n- " + "\n- ".join(reasons))
    return commit_sha


def _atomic_push(root: Path) -> None:
    result = _run_git(
        root,
        "push",
        "--atomic",
        "origin",
        "HEAD:main",
        f"refs/tags/{FINAL_SOURCE_TAG}",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Atomic push failed; GitHub was not partially updated.\n"
            + (result.stderr.strip() or result.stdout.strip())
        )


def finalize(root: Path, *, publish: bool) -> dict[str, str]:
    root = root.resolve()
    _assert_only_allowed_dirty_paths(root)
    _require_synced_main(root)
    ground = _verify_ground_manifest(root)
    structural, structural_sha = _materialize_structural_manifest(root, ground)
    gate = _update_gate(root, structural_sha)
    _preflight_gate(root, gate)
    _assert_only_allowed_dirty_paths(root)
    commit_sha = _commit_tag_and_verify(root)
    if publish:
        _atomic_push(root)
    return {
        "ground_manifest_sha256": EXPECTED_GROUND_MANIFEST_SHA256,
        "structural_world_manifest": str(structural.relative_to(root)),
        "structural_world_manifest_sha256": structural_sha,
        "source_commit": commit_sha,
        "source_tag": FINAL_SOURCE_TAG,
        "published": str(bool(publish)).lower(),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Atomically push the verified final commit and tag to origin/main.",
    )
    args = parser.parse_args()
    try:
        result = finalize(root, publish=bool(args.publish))
    except (OSError, RuntimeError, subprocess.CalledProcessError, yaml.YAMLError, ValueError) as exc:
        print(f"FINALIZATION BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("Confirmatory finalization: PASS")
    for key, value in result.items():
        print(f"{key}: {value}")
    if not args.publish:
        print("Local commit/tag created but not pushed. Re-run only after deleting the local final tag if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
