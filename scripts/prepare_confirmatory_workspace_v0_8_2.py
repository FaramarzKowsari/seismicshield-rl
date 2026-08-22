#!/usr/bin/env python3
"""Prepare an outcome-free v0.8.2 execution workspace; never execute a scientific shard.

This orchestration layer materializes the reviewed execution ledger and creates local state for
selection work while keeping every Tier-2 confirmatory shard locked. It has deliberately no
command that can unlock confirmatory data hydration or execute a structural-response simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from scripts.plan_confirmatory_execution_v0_8_2 import build_plan

WORKSPACE_SCHEMA = "confirmatory-workspace-v0.8.2-v1"
SELECTION_STATUS = "PLANNED_SELECTION"
CONFIRMATORY_STATUS = "LOCKED_CONFIRMATORY"
PLANNER_RELATIVE = "scripts/plan_confirmatory_execution_v0_8_2.py"
EXPECTED_PLANNER_GIT_BLOB = "87f508944b1788886a658b2e9bcc0a67e777476f"


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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"workspace JSON must be an object: {path}")
    return value


def _expected_state(plan: dict[str, Any], ledger_sha256: str) -> dict[str, Any]:
    shards = plan["shards"]
    states: dict[str, dict[str, Any]] = {}
    selection = 0
    confirmatory = 0
    for shard in shards:
        shard_id = str(shard["shard_id"])
        phase = str(shard["phase"])
        if phase.startswith("tier1_"):
            status = SELECTION_STATUS
            stage = "selection"
            selection += 1
        elif phase.startswith("tier2_confirmatory_"):
            status = CONFIRMATORY_STATUS
            stage = "confirmatory"
            confirmatory += 1
        else:
            raise ValueError(f"unexpected execution phase {phase!r}")
        states[shard_id] = {
            "stage": stage,
            "status": status,
            "attempts": 0,
            "result_artifact_sha256": None,
        }
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


def prepare_workspace(root: Path, workspace: Path) -> dict[str, Any]:
    root = root.resolve()
    workspace = workspace.resolve()
    _validate_planner_source(root)
    plan = build_plan(root)
    ledger_payload = _canonical_bytes(plan)
    ledger_sha = _sha256(ledger_payload)
    state = _expected_state(plan, ledger_sha)
    state_payload = _canonical_bytes(state)
    summary = _workspace_summary(plan, ledger_sha, state)
    summary_payload = _canonical_bytes(summary)

    ledger_path = workspace / "execution_ledger.json"
    state_path = workspace / "workspace_state.json"
    summary_path = workspace / "workspace.json"
    expected_paths = (ledger_path, state_path, summary_path)

    if workspace.exists():
        entries = list(workspace.iterdir())
        if entries and not any(path.exists() for path in expected_paths):
            raise RuntimeError("non-empty unrelated execution workspace exists; refusing to mix state")
        if any(path.exists() for path in expected_paths):
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
            if existing_state != state:
                raise RuntimeError("existing workspace state is not the untouched selection-only state")
            existing_summary = _read_json(summary_path)
            if existing_summary != summary:
                raise RuntimeError("existing workspace summary differs from the authoritative preparation")
            return summary

    workspace.mkdir(parents=True, exist_ok=True)
    _atomic_write(ledger_path, ledger_payload)
    _atomic_write(state_path, state_payload)
    _atomic_write(summary_path, summary_payload)
    return summary


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=root / "results/local/confirmatory_v0.8.2/execution_workspace",
    )
    args = parser.parse_args()
    summary = prepare_workspace(args.root, args.workspace)
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