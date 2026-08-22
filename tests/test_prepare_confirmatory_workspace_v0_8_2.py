from pathlib import Path

import json
import subprocess
import sys

import pytest

import scripts.prepare_confirmatory_workspace_v0_8_2 as workspace_module
from scripts.prepare_confirmatory_workspace_v0_8_2 import (
    CONFIRMATORY_STATUS,
    SELECTION_STATUS,
    prepare_workspace,
)


def test_workspace_prepares_selection_and_locks_every_confirmatory_shard(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    summary = prepare_workspace(root, workspace)
    state = json.loads((workspace / "workspace_state.json").read_text(encoding="utf-8"))
    ledger = json.loads((workspace / "execution_ledger.json").read_text(encoding="utf-8"))

    assert summary["status"] == "PREPARED_SELECTION_ONLY"
    assert summary["total_shards"] == 475
    assert summary["selection_shards"] == 424
    assert summary["confirmatory_shards"] == 51
    assert summary["allowed_data_partitions_at_this_stage"] == ["training", "validation"]
    assert summary["forbidden_data_partitions_at_this_stage"] == ["pilot", "confirmatory"]
    assert summary["confirmatory_data_hydration_allowed"] is False
    assert summary["confirmatory_execution_allowed"] is False
    assert state["confirmatory_outcomes_inspected"] is False

    statuses = {item["status"] for item in state["shards"].values()}
    assert statuses == {SELECTION_STATUS, CONFIRMATORY_STATUS}
    assert sum(item["status"] == SELECTION_STATUS for item in state["shards"].values()) == 424
    assert sum(item["status"] == CONFIRMATORY_STATUS for item in state["shards"].values()) == 51
    assert all(item["attempts"] == 0 for item in state["shards"].values())
    assert all(item["result_artifact_sha256"] is None for item in state["shards"].values())

    assert ledger["contains_waveform_bytes"] is False
    assert ledger["contains_response_outcomes"] is False
    assert all("record_id" not in shard for shard in ledger["shards"])
    assert all("vector" not in shard and "scalar" not in shard for shard in ledger["shards"])


def test_workspace_prepare_is_idempotent_only_while_untouched(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    first = prepare_workspace(root, workspace)
    second = prepare_workspace(root, workspace)
    assert first == second

    state_path = workspace / "workspace_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    first_shard = next(iter(state["shards"].values()))
    first_shard["attempts"] = 1
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="untouched selection-only state"):
        prepare_workspace(root, workspace)


def test_workspace_refuses_partial_existing_state(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workspace.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="partial execution workspace"):
        prepare_workspace(root, workspace)


def test_workspace_refuses_unrelated_nonempty_directory(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "unrelated.txt").write_text("do not mix\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="non-empty unrelated execution workspace"):
        prepare_workspace(root, workspace)


def test_workspace_refuses_extra_files_after_preparation(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    prepare_workspace(root, workspace)
    (workspace / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="contains unexpected files"):
        prepare_workspace(root, workspace)


def test_workspace_publication_failure_never_exposes_partial_final_state(
    tmp_path: Path, monkeypatch
):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    original = workspace_module._atomic_write
    calls = 0

    def fail_on_second_write(path: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated infrastructure interruption")
        original(path, payload)

    monkeypatch.setattr(workspace_module, "_atomic_write", fail_on_second_write)
    with pytest.raises(OSError, match="simulated infrastructure interruption"):
        prepare_workspace(root, workspace)

    assert not workspace.exists()
    assert not list(tmp_path.glob(".workspace.staging-*"))

    monkeypatch.setattr(workspace_module, "_atomic_write", original)
    summary = prepare_workspace(root, workspace)
    assert summary["status"] == "PREPARED_SELECTION_ONLY"
    assert sorted(path.name for path in workspace.iterdir()) == [
        "execution_ledger.json",
        "workspace.json",
        "workspace_state.json",
    ]


def test_workspace_publication_fsyncs_staging_and_parent(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    observed: list[Path] = []
    original = workspace_module._fsync_directory

    def record_fsync(path: Path) -> None:
        observed.append(path.resolve())
        original(path)

    monkeypatch.setattr(workspace_module, "_fsync_directory", record_fsync)
    prepare_workspace(root, workspace)

    assert any(
        path.parent == tmp_path.resolve() and path.name.startswith(".workspace.staging-")
        for path in observed
    )
    assert observed[-1] == tmp_path.resolve()


def test_fresh_workspace_parent_chain_is_persisted_level_by_level(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "new-local" / "confirmatory-v0.8.2" / "workspace"
    observed: list[Path] = []
    original = workspace_module._fsync_directory

    def record_fsync(path: Path) -> None:
        observed.append(path.resolve())
        original(path)

    monkeypatch.setattr(workspace_module, "_fsync_directory", record_fsync)
    prepare_workspace(root, workspace)

    # Creating new-local is persisted by fsync(tmp_path), then creating
    # confirmatory-v0.8.2 is persisted by fsync(new-local).
    assert tmp_path.resolve() in observed
    assert (tmp_path / "new-local").resolve() in observed
    assert workspace.is_dir()
    assert observed[-1] == workspace.parent.resolve()


def test_preparer_is_directly_executable_in_script_mode():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/prepare_confirmatory_workspace_v0_8_2.py", "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Prepare an outcome-free v0.8.2 execution workspace" in result.stdout


def test_reviewed_plan_executes_git_blob_against_supplied_root(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    calls: list[tuple[list[str], Path | None]] = []
    original = workspace_module.subprocess.run

    def record_run(args, *pargs, **kwargs):
        cwd = kwargs.get("cwd")
        calls.append((list(args), Path(cwd).resolve() if cwd is not None else None))
        return original(args, *pargs, **kwargs)

    monkeypatch.setattr(workspace_module.subprocess, "run", record_run)
    workspace_module._reviewed_plan(root)

    planner_calls = [
        (args, cwd)
        for args, cwd in calls
        if args and args[0] == sys.executable and "--output" in args
    ]
    assert len(planner_calls) == 1
    args, cwd = planner_calls[0]
    root_index = args.index("--root") + 1
    assert Path(args[root_index]).resolve() == root.resolve()
    assert cwd == root.resolve()
