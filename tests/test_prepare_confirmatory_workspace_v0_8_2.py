from pathlib import Path

import json
import pytest

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
