#!/usr/bin/env python3
"""Finalize the v0.8.2 confirmatory source tag without reading waveform outcomes.

Run only from a clean, synchronized local ``main`` after the v0.8.2 finalization
infrastructure has been merged. The command verifies that the public gate is blocked
only by the old source tag plus the explicit run-disable flag, switches the gate to the
new immutable tag, commits that one gate file, creates the annotated tag, and requires
the full gate to PASS before an optional atomic push.

This script never opens private waveform files and never executes a confirmatory model.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

import yaml

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

from scripts.check_confirmatory_gate import check_gate, digest_matches  # noqa: E402

GATE_PATH = Path("open_science/confirmatory_gate_v0.8.0.yaml")
PARENT_SOURCE_TAG = "confirmatory-v0.8.1-final"
FINAL_SOURCE_TAG = "confirmatory-v0.8.2-final"
EXPECTED_GATE_VERSION = "v0.8.2"
EXPECTED_EXECUTION_CONTRACT = "open_science/confirmatory_execution_v0.8.2.yaml"
EXPECTED_EXECUTION_SHA256 = "4be2acca57915ff6954a82dfb03bc5adc647bf1e9594fd01042c7be2af87dd50"
EXPECTED_ANALYSIS_CONTRACT = "open_science/confirmatory_analysis_v0.8.2.yaml"
EXPECTED_ANALYSIS_SHA256 = "864575fa42a048c751e6fc6658a70d92c9c398f86fff92422de9bbd8edfef141"
EXPECTED_VALIDATION_RUN = (
    "https://github.com/FaramarzKowsari/seismicshield-rl/actions/runs/32594455504"
)
EXPECTED_EXECUTION_EVIDENCE_SHA256 = (
    "dccb88c63d529ecc3d44d12dbd6091210df73fd04b9761e61cf13e8c817085d1"
)
EXPECTED_ANALYSIS_EVIDENCE_SHA256 = (
    "047523bfc65801062351230fc7cbf28df6dac0bd0e625f907aec168e3b17f62a"
)
EXPECTED_VALIDATION_ARTIFACT_SHA256 = (
    "50f50b0263563d7e13741366c181cd1602f01ded0a41ce32cf63cbcb9af11cfc"
)


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=check
    )


def _status_paths(root: Path) -> set[str]:
    result = _git(root, "status", "--porcelain=v1")
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        payload = line[3:]
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        paths.add(payload.replace("\\", "/"))
    return paths


def _require_synced_clean_main(root: Path) -> None:
    branch = _git(root, "branch", "--show-current").stdout.strip()
    if branch != "main":
        raise RuntimeError(f"Finalization must run from local main; current branch is {branch!r}.")
    if _status_paths(root):
        raise RuntimeError("Finalization requires a clean working tree before the gate mutation.")
    _git(root, "fetch", "origin", "main", "--tags")
    local = _git(root, "rev-parse", "HEAD").stdout.strip()
    remote = _git(root, "rev-parse", "origin/main").stdout.strip()
    if local != remote:
        raise RuntimeError("Local main is not exactly synchronized with origin/main.")
    existing = _git(root, "rev-parse", "--verify", f"refs/tags/{FINAL_SOURCE_TAG}", check=False)
    if existing.returncode == 0:
        raise RuntimeError(f"Final source tag {FINAL_SOURCE_TAG!r} already exists; refusing to move it.")
    parent = _git(
        root,
        "rev-parse",
        "--verify",
        f"refs/tags/{PARENT_SOURCE_TAG}^{{commit}}",
        check=False,
    )
    if parent.returncode != 0:
        raise RuntimeError(f"Parent source tag {PARENT_SOURCE_TAG!r} is missing.")


def _load_gate(root: Path) -> dict:
    path = root / GATE_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Confirmatory gate YAML is not a mapping.")
    return data


def _verify_v0_8_2_metadata(root: Path, data: dict) -> None:
    expected_scalars = {
        "version": EXPECTED_GATE_VERSION,
        "confirmatory_execution_contract": EXPECTED_EXECUTION_CONTRACT,
        "confirmatory_execution_contract_sha256": EXPECTED_EXECUTION_SHA256,
        "confirmatory_execution_validation_workflow_run": EXPECTED_VALIDATION_RUN,
        "confirmatory_execution_validation_evidence_sha256": EXPECTED_EXECUTION_EVIDENCE_SHA256,
        "confirmatory_execution_validation_artifact_sha256": EXPECTED_VALIDATION_ARTIFACT_SHA256,
        "confirmatory_execution_validated": True,
        "confirmatory_analysis_contract": EXPECTED_ANALYSIS_CONTRACT,
        "confirmatory_analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
        "confirmatory_analysis_validation_workflow_run": EXPECTED_VALIDATION_RUN,
        "confirmatory_analysis_validation_evidence_sha256": EXPECTED_ANALYSIS_EVIDENCE_SHA256,
        "confirmatory_analysis_validation_artifact_sha256": EXPECTED_VALIDATION_ARTIFACT_SHA256,
        "confirmatory_analysis_validated": True,
        "source_git_tag": PARENT_SOURCE_TAG,
        "confirmatory_runs_allowed": False,
    }
    mismatches = [
        f"{key}: expected {expected!r}, found {data.get(key)!r}"
        for key, expected in expected_scalars.items()
        if data.get(key) != expected
    ]
    if mismatches:
        raise RuntimeError("v0.8.2 gate metadata mismatch:\n- " + "\n- ".join(mismatches))
    if not digest_matches(root, EXPECTED_EXECUTION_CONTRACT, EXPECTED_EXECUTION_SHA256):
        raise RuntimeError("v0.8.2 execution contract digest mismatch.")
    if not digest_matches(root, EXPECTED_ANALYSIS_CONTRACT, EXPECTED_ANALYSIS_SHA256):
        raise RuntimeError("v0.8.2 analysis contract digest mismatch.")


def _require_pre_finalization_blockers(root: Path) -> None:
    ok, reasons = check_gate(root, root / GATE_PATH)
    if ok:
        raise RuntimeError("Gate unexpectedly passed before v0.8.2 finalization.")
    allowed_run = "confirmatory_runs_allowed is false."
    source_reasons = [
        reason
        for reason in reasons
        if reason.startswith(f"Source Git tag {PARENT_SOURCE_TAG!r} resolves to ")
        and reason.endswith("which does not equal HEAD.")
    ]
    unexpected = [reason for reason in reasons if reason != allowed_run and reason not in source_reasons]
    if len(source_reasons) != 1 or allowed_run not in reasons or unexpected:
        details = "\n- ".join(reasons)
        raise RuntimeError(
            "Pre-finalization gate has unexpected blockers; refusing to mutate it:\n- " + details
        )


def _write_pending_final_gate(root: Path) -> None:
    data = _load_gate(root)
    data["source_git_tag"] = FINAL_SOURCE_TAG
    data["confirmatory_runs_allowed"] = True
    (root / GATE_PATH).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    if _status_paths(root) != {GATE_PATH.as_posix()}:
        raise RuntimeError("Only the confirmatory gate may change during v0.8.2 finalization.")
    ok, reasons = check_gate(root, root / GATE_PATH)
    expected = f"Required source Git tag {FINAL_SOURCE_TAG!r} does not exist."
    if ok or reasons != [expected]:
        raise RuntimeError(
            "Pending v0.8.2 gate must be blocked only by the not-yet-created immutable tag; "
            f"observed blockers: {reasons!r}"
        )


def _commit_tag_verify(root: Path) -> str:
    _git(root, "add", "--", GATE_PATH.as_posix())
    staged = _git(root, "diff", "--cached", "--name-only").stdout.splitlines()
    if staged != [GATE_PATH.as_posix()]:
        raise RuntimeError(f"Unexpected staged finalization set: {staged!r}")
    _git(root, "commit", "-m", "Freeze confirmatory execution gate v0.8.2")
    commit_sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    _git(
        root,
        "tag",
        "-a",
        FINAL_SOURCE_TAG,
        "-m",
        "SeismicShield-RL v0.8.2 immutable confirmatory execution freeze",
    )
    ok, reasons = check_gate(root, root / GATE_PATH)
    if not ok:
        _git(root, "tag", "-d", FINAL_SOURCE_TAG, check=False)
        _git(root, "reset", "--mixed", "HEAD^", check=False)
        raise RuntimeError("Final v0.8.2 gate did not pass:\n- " + "\n- ".join(reasons))
    return commit_sha


def _atomic_push(root: Path) -> None:
    result = _git(
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


def _rollback(root: Path) -> None:
    _git(root, "tag", "-d", FINAL_SOURCE_TAG, check=False)
    _git(root, "reset", "--mixed", "HEAD^", check=False)


def finalize(root: Path, *, publish: bool) -> dict[str, str]:
    root = root.resolve()
    _require_synced_clean_main(root)
    data = _load_gate(root)
    _verify_v0_8_2_metadata(root, data)
    _require_pre_finalization_blockers(root)
    _write_pending_final_gate(root)
    commit_sha = _commit_tag_verify(root)
    if publish:
        try:
            _atomic_push(root)
        except RuntimeError:
            _rollback(root)
            raise
    return {
        "source_commit": commit_sha,
        "source_tag": FINAL_SOURCE_TAG,
        "execution_contract_sha256": EXPECTED_EXECUTION_SHA256,
        "analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
        "validation_artifact_sha256": EXPECTED_VALIDATION_ARTIFACT_SHA256,
        "published": str(bool(publish)).lower(),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Atomically push the verified v0.8.2 gate commit and immutable tag.",
    )
    args = parser.parse_args()
    try:
        result = finalize(root, publish=bool(args.publish))
    except (OSError, RuntimeError, subprocess.CalledProcessError, yaml.YAMLError, ValueError) as exc:
        print(f"V0.8.2 FINALIZATION BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("Confirmatory v0.8.2 finalization: PASS")
    for key, value in result.items():
        print(f"{key}: {value}")
    if not args.publish:
        print("Local commit/tag created but not pushed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
