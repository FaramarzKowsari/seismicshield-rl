#!/usr/bin/env python3
"""Run one reviewed v0.8.2 Stage-A shard against training+validation data only.

The runner never accepts Tier-2 shards. Scientific modules are loaded from a detached worktree of
`confirmatory-v0.8.2-final` under isolated Python. A failed process discards the whole attempt;
there is no mid-shard resume and no retry of scientific solver failures inside an attempt.
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
from time import perf_counter
from typing import Any

EXPECTED_SCIENTIFIC_TAG = "confirmatory-v0.8.2-final"
EXPECTED_SCIENTIFIC_COMMIT = "cecd3b6c27b5deb6cb6be7ddc478cfc407a45644"
EXPECTED_WORKSPACE_SCHEMA = "confirmatory-workspace-v0.8.2-v1"
EXPECTED_PLANNER_GIT_BLOB = "87f508944b1788886a658b2e9bcc0a67e777476f"
RUNTIME_RELATIVE = "scripts/confirmatory_stage_a_runtime_v0_8_2.py"
EXPECTED_RUNTIME_GIT_BLOB = "06549511d80df57e3f30b145eddb43d3337ba69e"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON must be an object: {path}")
    return value


def _git_text(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _isolated_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        if os.name == "nt":  # pragma: no cover
            return
        raise
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_mkdir_chain(path: Path) -> None:
    path = path.resolve()
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            raise RuntimeError(f"no existing ancestor for {path}")
        cursor = cursor.parent
    if not cursor.is_dir():
        raise RuntimeError(f"ancestor is not a directory: {cursor}")
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        _fsync_directory(directory.parent)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate_runtime_source(root: Path) -> str:
    committed = _git_text(root, "rev-parse", f"HEAD:{RUNTIME_RELATIVE}")
    working = _git_text(root, "hash-object", RUNTIME_RELATIVE)
    if committed != EXPECTED_RUNTIME_GIT_BLOB or working != EXPECTED_RUNTIME_GIT_BLOB:
        raise RuntimeError(
            "Stage-A runtime differs from reviewed blob: "
            f"expected {EXPECTED_RUNTIME_GIT_BLOB}, committed={committed}, working={working}"
        )
    runner_relative = "scripts/run_confirmatory_stage_a_shard_v0_8_2.py"
    runner_committed = _git_text(root, "rev-parse", f"HEAD:{runner_relative}")
    runner_working = _git_text(root, "hash-object", runner_relative)
    if runner_committed != runner_working:
        raise RuntimeError("Stage-A shard runner working tree differs from committed source")
    return runner_working


def validate_workspace(workspace: Path, shard_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = read_json(workspace / "workspace.json")
    state = read_json(workspace / "workspace_state.json")
    ledger = read_json(workspace / "execution_ledger.json")
    ledger_sha = sha256_path(workspace / "execution_ledger.json")
    if summary.get("schema") != EXPECTED_WORKSPACE_SCHEMA or state.get("schema") != EXPECTED_WORKSPACE_SCHEMA:
        raise RuntimeError("unexpected confirmatory workspace schema")
    if summary.get("status") != "PREPARED_SELECTION_ONLY":
        raise RuntimeError("Stage-A requires PREPARED_SELECTION_ONLY workspace")
    if summary.get("execution_planner_git_blob") != EXPECTED_PLANNER_GIT_BLOB:
        raise RuntimeError("workspace was not built from reviewed execution planner")
    if summary.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError("workspace scientific source commit mismatch")
    for document in (summary, state):
        if document.get("confirmatory_data_hydration_allowed") is not False:
            raise RuntimeError("Stage-A refuses workspace permitting confirmatory hydration")
        if document.get("confirmatory_execution_allowed") is not False:
            raise RuntimeError("Stage-A refuses workspace permitting confirmatory execution")
    if state.get("confirmatory_outcomes_inspected") is not False:
        raise RuntimeError("Stage-A refuses workspace after confirmatory outcome inspection")
    if state.get("ledger_sha256") != ledger_sha or summary.get("ledger_sha256") != ledger_sha:
        raise RuntimeError("workspace ledger SHA-256 mismatch")
    shards = [item for item in ledger.get("shards", []) if item.get("shard_id") == shard_id]
    if len(shards) != 1:
        raise RuntimeError(f"execution ledger must contain exactly one shard {shard_id!r}")
    shard = shards[0]
    if not str(shard.get("phase", "")).startswith("tier1_"):
        raise RuntimeError("Stage-A runner refuses every Tier-2/confirmatory shard")
    shard_state = (state.get("shards") or {}).get(shard_id)
    if not isinstance(shard_state, dict):
        raise RuntimeError("workspace state does not contain requested shard")
    if shard_state.get("stage") != "selection" or shard_state.get("status") != "PLANNED_SELECTION":
        raise RuntimeError("requested shard is not in pristine selection state")
    return shard, summary


def resolve_scientific_tag(root: Path) -> str:
    resolved = _git_text(root, "rev-parse", "--verify", f"refs/tags/{EXPECTED_SCIENTIFIC_TAG}^{{commit}}")
    if resolved != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError(f"immutable scientific tag moved: {resolved}")
    return resolved


def _write_worker_blob(root: Path, path: Path) -> None:
    result = subprocess.run(
        ["git", "cat-file", "blob", EXPECTED_RUNTIME_GIT_BLOB],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("cannot read reviewed Stage-A runtime blob from Git")
    path.write_bytes(result.stdout)
    if _git_text(root, "hash-object", str(path)) != EXPECTED_RUNTIME_GIT_BLOB:
        raise RuntimeError("materialized Stage-A runtime bytes do not match reviewed blob")


def _count_audit_rows(path: Path, expected_calls: int) -> None:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("partition") not in {"training", "validation"}:
                raise RuntimeError("Stage-A audit contains forbidden non-training/validation partition")
            if row.get("checkpoint_training_call") is not None and row.get("partition") != "validation":
                raise RuntimeError("checkpoint marker appeared outside validation audit")
            count += 1
    if count != expected_calls:
        raise RuntimeError(f"Stage-A audit row count mismatch: expected {expected_calls}, found {count}")


def validate_payload(payload: Path, shard: dict[str, Any]) -> dict[str, str]:
    artifact_path = payload / "artifact.json"
    audit_path = payload / "calls.jsonl"
    if not artifact_path.is_file() or not audit_path.is_file():
        raise RuntimeError("Stage-A worker did not produce required artifact/audit files")
    artifact = read_json(artifact_path)
    if artifact.get("shard_id") != shard["shard_id"] or artifact.get("phase") != shard["phase"]:
        raise RuntimeError("Stage-A artifact identity mismatch")
    if artifact.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError("Stage-A artifact scientific source mismatch")
    if artifact.get("contains_waveform_bytes") is not False or artifact.get("contains_confirmatory_outcomes") is not False:
        raise RuntimeError("Stage-A artifact privacy boundary mismatch")
    expected_calls = int(shard["calls"])
    if int(artifact.get("completed_calls", -1)) != expected_calls:
        raise RuntimeError("Stage-A artifact call count mismatch")
    _count_audit_rows(audit_path, expected_calls)
    files = [path for path in payload.iterdir() if path.is_file()]
    expected_names = {"artifact.json", "calls.jsonl"}
    if shard["phase"] == "tier1_train_validate_learned":
        expected_names.add("checkpoint.npz")
    if {path.name for path in files} != expected_names:
        raise RuntimeError(
            "Stage-A payload contains unexpected files: "
            + ", ".join(sorted(path.name for path in files))
        )
    hashes = {path.name: sha256_path(path) for path in files}
    return hashes


def publish_feature_cache(feature_dir: Path, final_dir: Path, done: dict[str, Any]) -> None:
    if done.get("phase") != "tier1_feature_precompute":
        return
    artifact = read_json(final_dir / "artifact.json")
    state_id = artifact["structural_state_id"]
    destination = feature_dir / f"{state_id.replace(':', '__')}.json"
    _durable_mkdir_chain(feature_dir)
    source_bytes = (final_dir / "artifact.json").read_bytes()
    if destination.exists():
        if destination.read_bytes() != source_bytes:
            raise RuntimeError(f"existing feature cache differs for {state_id}")
        _fsync_directory(feature_dir)
        return
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=feature_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(source_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
        _fsync_directory(feature_dir)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def verify_existing_result(final_dir: Path, shard: dict[str, Any], runner_blob: str, feature_dir: Path) -> dict[str, Any] | None:
    if not final_dir.exists():
        return None
    if not final_dir.is_dir():
        raise RuntimeError("Stage-A result path exists and is not a directory")
    done_path = final_dir / "DONE.json"
    if not done_path.is_file():
        raise RuntimeError("partial Stage-A result exists without DONE.json")
    done = read_json(done_path)
    if done.get("status") != "PASS" or done.get("shard_id") != shard["shard_id"]:
        raise RuntimeError("existing Stage-A DONE identity/status mismatch")
    if done.get("runtime_git_blob") != EXPECTED_RUNTIME_GIT_BLOB or done.get("runner_git_blob") != runner_blob:
        raise RuntimeError("existing Stage-A result was produced by different reviewed orchestration source")
    hashes = done.get("payload_sha256") or {}
    for name, expected in hashes.items():
        path = final_dir / name
        if not path.is_file() or sha256_path(path) != expected:
            raise RuntimeError(f"existing Stage-A result payload hash mismatch: {name}")
    _count_audit_rows(final_dir / "calls.jsonl", int(shard["calls"]))
    _fsync_directory(final_dir)
    _fsync_directory(final_dir.parent)
    publish_feature_cache(feature_dir, final_dir, done)
    return done


def run_shard(*, root: Path, workspace: Path, private_dir: Path, results_root: Path, feature_dir: Path, shard_id: str, dry_run: bool = False) -> dict[str, Any]:
    root = root.resolve()
    runner_blob = validate_runtime_source(root)
    resolve_scientific_tag(root)
    shard, workspace_summary = validate_workspace(workspace.resolve(), shard_id)
    if dry_run:
        return {
            "status": "DRY_RUN_PASS",
            "shard_id": shard_id,
            "phase": shard["phase"],
            "calls": int(shard["calls"]),
            "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
            "confirmatory_execution": False,
        }
    _durable_mkdir_chain(results_root.resolve())
    _durable_mkdir_chain(feature_dir.resolve())
    final_dir = results_root.resolve() / shard_id
    existing = verify_existing_result(final_dir, shard, runner_blob, feature_dir.resolve())
    if existing is not None:
        return existing
    if not private_dir.resolve().is_dir():
        raise RuntimeError(f"Stage-A private data directory missing: {private_dir}")

    started = perf_counter()
    attempt = Path(tempfile.mkdtemp(prefix=f".{shard_id}.attempt-", dir=results_root.resolve()))
    _fsync_directory(results_root.resolve())
    worktree_parent = attempt / "scientific"
    worker_path = attempt / "runtime.py"
    shard_json = attempt / "shard.json"
    payload = attempt / "payload"
    shard_json.write_text(json.dumps(shard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _fsync_file(shard_json)
    _write_worker_blob(root, worker_path)
    _fsync_file(worker_path)
    _fsync_directory(attempt)
    worktree_added = False
    try:
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", "--force", str(worktree_parent), EXPECTED_SCIENTIFIC_TAG],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if add.returncode:
            detail = add.stderr.strip() or add.stdout.strip()
            raise RuntimeError(f"cannot create immutable scientific worktree: {detail}")
        worktree_added = True
        head = _git_text(worktree_parent, "rev-parse", "HEAD")
        if head != EXPECTED_SCIENTIFIC_COMMIT:
            raise RuntimeError("scientific worktree resolved to wrong immutable commit")
        frozen_src = (worktree_parent / "src").resolve()
        bootstrap = (
            "import runpy,sys;"
            f"sys.path.insert(0,{str(frozen_src)!r});"
            f"sys.argv[0]={str(worker_path)!r};"
            f"runpy.run_path({str(worker_path)!r},run_name='__main__')"
        )
        command = [
            sys.executable, "-I", "-c", bootstrap,
            "--scientific-root", str(worktree_parent),
            "--shard-json", str(shard_json),
            "--private-dir", str(private_dir.resolve()),
            "--feature-dir", str(feature_dir.resolve()),
            "--output-dir", str(payload),
        ]
        result = subprocess.run(
            command,
            cwd=root,
            env=_isolated_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
            raise RuntimeError(f"Stage-A scientific shard failed; entire attempt discarded:\n{detail}")
        hashes = validate_payload(payload, shard)
        done = {
            "schema": "confirmatory-stage-a-done-v1",
            "status": "PASS",
            "shard_id": shard_id,
            "phase": shard["phase"],
            "method": shard.get("method"),
            "seed": shard.get("seed"),
            "structural_state_id": shard.get("structural_state_id"),
            "expected_calls": int(shard["calls"]),
            "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
            "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
            "workspace_ledger_sha256": workspace_summary["ledger_sha256"],
            "runtime_git_blob": EXPECTED_RUNTIME_GIT_BLOB,
            "runner_git_blob": runner_blob,
            "payload_sha256": hashes,
            "wall_clock_s": float(perf_counter() - started),
            "confirmatory_data_used": False,
            "confirmatory_outcomes_inspected": False,
        }
        _atomic_json(payload / "DONE.json", done)
        for path in payload.iterdir():
            if path.is_file():
                _fsync_file(path)
        _fsync_directory(payload)
        if final_dir.exists():
            raise RuntimeError("Stage-A result appeared concurrently during execution")
        os.replace(payload, final_dir)
        _fsync_directory(results_root.resolve())
        publish_feature_cache(feature_dir.resolve(), final_dir, done)
        return done
    finally:
        if worktree_added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_parent)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
        if attempt.exists():
            shutil.rmtree(attempt, ignore_errors=True)
            _fsync_directory(results_root.resolve())


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=script_root)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--private-dir", type=Path, default=None)
    parser.add_argument("--results-root", type=Path, default=None)
    parser.add_argument("--feature-dir", type=Path, default=None)
    parser.add_argument("--shard-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / "results/local/confirmatory_v0.8.2"
    workspace = (args.workspace or base / "execution_workspace").resolve()
    private_dir = (args.private_dir or root / "data/private/esm/stage-a-v0.8.2").resolve()
    results_root = (args.results_root or base / "stage_a/shards").resolve()
    feature_dir = (args.feature_dir or base / "stage_a/features").resolve()
    try:
        result = run_shard(
            root=root,
            workspace=workspace,
            private_dir=private_dir,
            results_root=results_root,
            feature_dir=feature_dir,
            shard_id=args.shard_id,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Stage-A shard: BLOCKED\n- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
