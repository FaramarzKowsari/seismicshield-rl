from pathlib import Path

import pytest

import scripts.prepare_confirmatory_workspace_v0_8_2 as workspace_module
import scripts.run_confirmatory_stage_a_shard_v0_8_2 as runner


def _prepared_workspace(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    workspace_module.prepare_workspace(root, workspace)
    return workspace


def test_stage_a_runner_source_and_immutable_tag_are_exact():
    root = Path(__file__).resolve().parents[1]
    runner_blob = runner.validate_runtime_source(root)
    assert len(runner_blob) == 40
    assert runner.resolve_scientific_tag(root) == runner.EXPECTED_SCIENTIFIC_COMMIT


def test_workspace_accepts_pristine_tier1_and_rejects_tier2(tmp_path: Path):
    workspace = _prepared_workspace(tmp_path)
    ledger = runner.read_json(workspace / "execution_ledger.json")
    tier1 = next(shard for shard in ledger["shards"] if shard["phase"].startswith("tier1_"))
    tier2 = next(shard for shard in ledger["shards"] if shard["phase"].startswith("tier2_"))
    accepted, _ = runner.validate_workspace(workspace, tier1["shard_id"])
    assert accepted == tier1
    with pytest.raises(RuntimeError, match="refuses every Tier-2"):
        runner.validate_workspace(workspace, tier2["shard_id"])


def test_stage_a_dry_run_needs_no_private_data_and_never_executes_confirmatory(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    workspace = _prepared_workspace(tmp_path)
    ledger = runner.read_json(workspace / "execution_ledger.json")
    feature = next(
        shard for shard in ledger["shards"] if shard["phase"] == "tier1_feature_precompute"
    )
    result = runner.run_shard(
        root=root,
        workspace=workspace,
        private_dir=tmp_path / "does-not-exist",
        results_root=tmp_path / "results",
        feature_dir=tmp_path / "features",
        shard_id=feature["shard_id"],
        dry_run=True,
    )
    assert result["status"] == "DRY_RUN_PASS"
    assert result["confirmatory_execution"] is False
    assert result["calls"] == 52
    assert not (tmp_path / "results").exists()
    assert not (tmp_path / "features").exists()


def test_workspace_with_confirmatory_permission_is_rejected(tmp_path: Path):
    workspace = _prepared_workspace(tmp_path)
    ledger = runner.read_json(workspace / "execution_ledger.json")
    tier1 = next(shard for shard in ledger["shards"] if shard["phase"].startswith("tier1_"))
    summary_path = workspace / "workspace.json"
    summary = runner.read_json(summary_path)
    summary["confirmatory_execution_allowed"] = True
    summary_path.write_text(__import__("json").dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="permitting confirmatory execution"):
        runner.validate_workspace(workspace, tier1["shard_id"])
