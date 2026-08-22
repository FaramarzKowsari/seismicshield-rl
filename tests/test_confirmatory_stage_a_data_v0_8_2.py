from pathlib import Path

import pytest

import scripts.prepare_confirmatory_stage_a_data_v0_8_2 as stage_a_data


def test_stage_a_manifest_is_exactly_training_plus_validation_capable():
    root = Path(__file__).resolve().parents[1]
    rows = stage_a_data.manifest_rows(root / "data/manifests/ground_motion_manifest.csv")
    counts = {
        partition: sum(row["partition"] == partition for row in rows)
        for partition in stage_a_data.FROZEN_COUNTS
    }
    assert counts == {"training": 52, "validation": 20, "pilot": 16, "confirmatory": 48}
    hashes = stage_a_data.partition_hashes(rows)
    assert len(hashes["training"] | hashes["validation"]) == 72
    assert (hashes["training"] | hashes["validation"]).isdisjoint(
        hashes["pilot"] | hashes["confirmatory"]
    )


def test_stage_a_private_directory_rejects_forbidden_partition_before_content_use(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    rows = stage_a_data.manifest_rows(root / "data/manifests/ground_motion_manifest.csv")
    forbidden = next(
        row["processed_sha256"]
        for row in rows
        if row["partition"] in {"pilot", "confirmatory"}
    )
    private_dir = tmp_path / "stage-a"
    private_dir.mkdir()
    (private_dir / f"{forbidden}.csv").write_text("never read as science\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="forbidden pilot/confirmatory"):
        stage_a_data.verify_private_stage_a_set(private_dir, rows, require_complete=False)


def test_hydrator_source_is_exact_reviewed_blob_and_python_environment_is_isolated(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    stage_a_data.validate_hydrator_source(root)
    monkeypatch.setenv("PYTHONPATH", "/tmp/shadow")
    monkeypatch.setenv("PYTHONHOME", "/tmp/home")
    env = stage_a_data._isolated_python_env()
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "PYTHONSTARTUP" not in env
    assert "PYTHONUSERBASE" not in env
    assert env["PYTHONNOUSERSITE"] == "1"


def test_stage_a_default_private_and_audit_paths_follow_selected_root(tmp_path: Path):
    root = (tmp_path / "alternate-checkout").resolve()
    private_dir, audit_out = stage_a_data._resolve_paths(root, None, None)
    assert private_dir == root / "data/private/esm/stage-a-v0.8.2"
    assert audit_out == root / "results/local/confirmatory_v0.8.2/stage_a_hydration.json"
