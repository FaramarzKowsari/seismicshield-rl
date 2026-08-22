#!/usr/bin/env python3
"""Prepare an outcome-free v0.8.2 execution workspace; never execute a scientific shard.

The workspace materializes the reviewed execution ledger and creates local state for selection
work while every Tier-2 confirmatory shard remains locked. This module deliberately has no
command that can unlock confirmatory hydration or execute a structural-response simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

WORKSPACE_SCHEMA = "confirmatory-workspace-v0.8.2-v1"
SELECTION_STATUS = "PLANNED_SELECTION"
CONFIRMATORY_STATUS = "LOCKED_CONFIRMATORY"
PLANNER_RELATIVE = "scripts/plan_confirmatory_execution_v0_8_2.py"
EXPECTED_PLANNER_GIT_BLOB = "87f508944b1788886a658b2e9bcc0a67e777476f"
EXPECTED_TOTAL_SHARDS = 475
EXPECTED_SELECTION_SHARDS = 424
EXPECTED_CONFIRMATORY_SHARDS = 51
EXPECTED_SCIENTIFIC_TAG = "confirmatory-v0.8.2-final"
EXPECTED_SCIENTIFIC_COMMIT = "cecd3b6c27b5deb6cb6be7ddc478cfc407a45644"


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_text(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _validate_planner_source(root: Path) -> None:
    """Require both committed and working planner bytes to equal the reviewed Git blob."""
    try:
        committed = _git_text(root, "rev-parse", f"HEAD:{PLANNER_RELATIVE}")
        working = _git_text(root, "hash-object", PLANNER_RELATIVE)
    except RuntimeError as exc:
        raise RuntimeError(f"cannot authenticate reviewed execution planner: {exc}") from exc
    if committed != EXPECTED_PLANNER_GIT_BLOB:
        raise RuntimeError(
            "committed execution planner differs from the reviewed frozen planner blob: "
            f"expected {EXPECTED_PLANNER_GIT_BLOB}, found {committed}"
        )
    if working != EXPECTED_PLANNER_GIT_BLOB:
        raise RuntimeError(
            "working-tree execution planner differs from the reviewed frozen planner blob: "
            f"expected {EXPECTED_PLANNER_GIT_BLOB}, found {working}"
        )


def _isolated_python_env() -> dict[str, str]:
    """Remove ambient Python import controls before executing authenticated planner bytes."""
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _reviewed_plan(root: Path) -> dict[str, Any]:
    """Execute exact reviewed planner bytes from Git in isolated Python mode."""
    _validate_planner_source(root)
    blob = subprocess.run(
        ["git", "cat-file", "blob", EXPECTED_PLANNER_GIT_BLOB],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if blob.returncode:
        detail = blob.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot read reviewed planner blob from Git object database: {detail}")

    with tempfile.TemporaryDirectory(prefix="seismicshield-reviewed-planner-") as temp_name:
        temp_dir = Path(temp_name)
        planner = temp_dir / "plan_confirmatory_execution_v0_8_2.py"
        output = temp_dir / "execution_ledger.json"
        planner.write_bytes(blob.stdout)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(planner),
                "--root",
                str(root),
                "--output",
                str(output),
            ],
            cwd=root,
            env=_isolated_python_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            raise RuntimeError(f"reviewed execution planner failed closed:\n{detail}")
        if not output.is_file():
            raise RuntimeError("reviewed execution planner returned success without a ledger")
        value = json.loads(output.read_text(encoding="utf-8"))

    # Detect a concurrent working-tree change between authentication and planner completion.
    _validate_planner_source(root)
    if not isinstance(value, dict):
        raise RuntimeError("reviewed execution planner output is not a JSON object")
    if value.get("authoritative_gate_pass") is not True:
        raise RuntimeError("reviewed execution planner did not record authoritative gate PASS")
    if value.get("scientific_source_tag") != EXPECTED_SCIENTIFIC_TAG:
        raise RuntimeError("reviewed execution planner returned the wrong scientific source tag")
    if value.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError("reviewed execution planner returned the wrong scientific source commit")
    summary = value.get("summary")
    if not isinstance(summary, dict) or int(summary.get("total_shards", -1)) != EXPECTED_TOTAL_SHARDS:
        raise RuntimeError("reviewed execution planner returned an unexpected shard count")
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _fsync_directory(path: Path) -> None:
    """Make directory-entry changes durable before reporting workspace publication."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        if os.name == "nt":  # pragma: no cover - Windows compatibility only
            return
        raise
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_mkdir_chain(path: Path) -> None:
    """Create missing directories and durably persist every new ancestor entry."""
    path = path.resolve()
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            raise RuntimeError(f"cannot find an existing ancestor for {path}")
        cursor = cursor.parent
    if not cursor.is_dir():
        raise RuntimeError(f"workspace parent ancestor is not a directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        if not directory.is_dir():
            raise RuntimeError(f"workspace parent path is not a directory: {directory}")
        _fsync_directory(directory.parent)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"workspace JSON must be an object: {path}")
    return value


def _expected_state(plan: dict[str, Any], ledger_sha256: str) -> dict[str, Any]:
    shards = plan.get("shards")
    if not isinstance(shards, list) or len(shards) != EXPECTED_TOTAL_SHARDS:
        raise ValueError("execution ledger does not contain the expected 475 shards")
    states: dict[str, dict[str, Any]] = {}
    selection = 0
    confirmatory = 0
    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError("execution ledger contains a non-object shard")
        shard_id = str(shard["shard_id"])
        if shard_id in states:
            raise ValueError(f"duplicate execution shard id {shard_id!r}")
        phase = str(shard["phase"])
        if phase.startswith("tier1_"):
            status, stage = SELECTION_STATUS, "selection"
            selection += 1
        elif phase.startswith("tier2_confirmatory_"):
            status, stage = CONFIRMATORY_STATUS, "confirmatory"
            confirmatory += 1
        else:
            raise ValueError(f"unexpected execution phase {phase!r}")
        states[shard_id] = {
            "stage": stage,
            "status": status,
            "attempts": 0,
            "result_artifact_sha256": None,
        }
    if selection != EXPECTED_SELECTION_SHARDS or confirmatory != EXPECTED_CONFIRMATORY_SHARDS:
        raise ValueError(
            "execution ledger stage counts mismatch: "
            f"selection={selection}, confirmatory={confirmatory}"
        )
    return {
        "schema": WORKSPACE_SCHEMA,
        "ledger_sha256": ledger_sha256,
        "execution_planner_git_blob": EXPECTED_PLANNER_GIT_BLOB,
        "scientific_source_tag": plan["scientific_source_tag"],
        "scientific_source_commit": plan["scientific_source_commit"],
        "selection_shards": selection,
        "confirmatory_shards": confirmatory,
        "confirmatory_data_hydration_allowed": False,
        "confirmatory_execution_allowed": False,
        "confirmatory_outcomes_inspected": False,
        "shards": states,
    }


def _workspace_summary(plan: dict[str, Any], ledger_sha256: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": WORKSPACE_SCHEMA,
        "status": "PREPARED_SELECTION_ONLY",
        "ledger_sha256": ledger_sha256,
        "execution_planner_git_blob": EXPECTED_PLANNER_GIT_BLOB,
        "scientific_source_tag": plan["scientific_source_tag"],
        "scientific_source_commit": plan["scientific_source_commit"],
        "authoritative_gate_pass": bool(plan["authoritative_gate_pass"]),
        "total_shards": int(plan["summary"]["total_shards"]),
        "selection_shards": int(state["selection_shards"]),
        "confirmatory_shards": int(state["confirmatory_shards"]),
        "allowed_data_partitions_at_this_stage": ["training", "validation"],
        "forbidden_data_partitions_at_this_stage": ["pilot", "confirmatory"],
        "confirmatory_data_hydration_allowed": False,
        "confirmatory_execution_allowed": False,
        "contains_waveform_bytes": False,
        "contains_response_outcomes": False,
        "next_irreversible_boundary": "selection_artifacts_must_be_complete_and_hash_frozen_before_any_confirmatory_authorization",
    }


def _verify_existing_workspace(
    workspace: Path,
    ledger_payload: bytes,
    expected_state: dict[str, Any],
    expected_summary: dict[str, Any],
) -> dict[str, Any] | None:
    ledger_path = workspace / "execution_ledger.json"
    state_path = workspace / "workspace_state.json"
    summary_path = workspace / "workspace.json"
    expected_paths = (ledger_path, state_path, summary_path)
    if not workspace.exists():
        return None
    if not workspace.is_dir():
        raise RuntimeError("execution workspace path exists and is not a directory")
    entries = list(workspace.iterdir())
    if not entries:
        return None
    if not any(path.exists() for path in expected_paths):
        raise RuntimeError("non-empty unrelated execution workspace exists; refusing to mix state")
    if not all(path.is_file() for path in expected_paths):
        raise RuntimeError("partial execution workspace exists; refusing to repair or overwrite it")
    extra_entries = {entry.name for entry in entries} - {path.name for path in expected_paths}
    if extra_entries:
        raise RuntimeError(
            "execution workspace contains unexpected files; refusing to treat it as untouched: "
            + ", ".join(sorted(extra_entries))
        )
    if ledger_path.read_bytes() != ledger_payload:
        raise RuntimeError("existing workspace ledger differs from the authoritative execution plan")
    existing_state = _read_json(state_path)
    if existing_state != expected_state:
        raise RuntimeError("existing workspace state is not the untouched selection-only state")
    existing_summary = _read_json(summary_path)
    if existing_summary != expected_summary:
        raise RuntimeError("existing workspace summary differs from the authoritative preparation")
    return existing_summary


def _publish_workspace_atomically(
    workspace: Path,
    ledger_payload: bytes,
    state_payload: bytes,
    summary_payload: bytes,
) -> None:
    parent = workspace.parent
    _durable_mkdir_chain(parent)
    staging = Path(tempfile.mkdtemp(prefix=f".{workspace.name}.staging-", dir=parent))
    _fsync_directory(parent)
    published = False
    try:
        _atomic_write(staging / "execution_ledger.json", ledger_payload)
        _atomic_write(staging / "workspace_state.json", state_payload)
        _atomic_write(staging / "workspace.json", summary_payload)
        _fsync_directory(staging)
        if workspace.exists():
            if not workspace.is_dir() or any(workspace.iterdir()):
                raise RuntimeError("execution workspace changed while staging preparation")
            workspace.rmdir()
            _fsync_directory(parent)
        os.replace(staging, workspace)
        _fsync_directory(parent)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
            _fsync_directory(parent)


def prepare_workspace(root: Path, workspace: Path) -> dict[str, Any]:
    root = root.resolve()
    workspace = workspace.resolve()
    plan = _reviewed_plan(root)
    ledger_payload = _canonical_bytes(plan)
    ledger_sha = _sha256(ledger_payload)
    state = _expected_state(plan, ledger_sha)
    state_payload = _canonical_bytes(state)
    summary = _workspace_summary(plan, ledger_sha, state)
    summary_payload = _canonical_bytes(summary)

    existing = _verify_existing_workspace(workspace, ledger_payload, state, summary)
    if existing is not None:
        # Recovery path: a prior run may have completed os.replace but failed while
        # fsyncing the parent. Re-sync the final name before reporting success.
        _fsync_directory(workspace.parent)
        return existing
    _publish_workspace_atomically(workspace, ledger_payload, state_payload, summary_payload)
    return summary


def _resolve_workspace(root: Path, requested: Path | None) -> Path:
    if requested is not None:
        return requested.resolve()
    return (root / "results/local/confirmatory_v0.8.2/execution_workspace").resolve()


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=script_root)
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    workspace = _resolve_workspace(root, args.workspace)
    summary = prepare_workspace(root, workspace)
    print("Confirmatory workspace: PREPARED_SELECTION_ONLY")
    print(f"Ledger SHA-256: {summary['ledger_sha256']}")
    print(f"Planner Git blob: {summary['execution_planner_git_blob']}")
    print(f"Selection shards: {summary['selection_shards']}")
    print(f"Locked confirmatory shards: {summary['confirmatory_shards']}")
    print("Confirmatory hydration allowed: false")
    print("Confirmatory execution allowed: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())