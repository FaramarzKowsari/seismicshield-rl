from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import scripts.confirmatory_stage_a_runtime_v0_8_2 as runtime
from seismicshield_rl.physics.base import DamperDesign


def test_stage_a_design_hash_ignores_slip_for_zero_count_stories():
    left = DamperDesign(
        np.asarray([0, 1, 0], dtype=int),
        np.asarray([350_000.0, 50_000.0, 100_000.0], dtype=float),
    )
    right = DamperDesign(
        np.asarray([0, 1, 0], dtype=int),
        np.asarray([0.0, 50_000.0, 0.0], dtype=float),
    )
    assert runtime.canonical_design(left) == runtime.canonical_design(right)
    assert runtime.design_hash(left) == runtime.design_hash(right)


def test_audit_writer_retains_unscalarized_vector_per_checkpoint_without_extra_calls(tmp_path: Path):
    logger = runtime.AuditWriter(
        tmp_path / "calls.jsonl", checkpoints=[10, 20], calls_per_checkpoint=2
    )
    design = DamperDesign(np.asarray([1], dtype=int), np.asarray([50_000.0], dtype=float))
    try:
        for index, vector in enumerate(
            [
                [0.2, 0.4, 0.6],
                [0.4, 0.6, 0.8],
                [0.6, 0.8, 1.0],
                [0.8, 1.0, 1.2],
            ]
        ):
            evaluation = SimpleNamespace(
                vector=np.asarray(vector, dtype=float),
                scalar=float(sum(vector)),
                status="valid_converged",
            )
            logger.record(
                method="mappo",
                seed=1103,
                partition="validation",
                state_id="3:nominal",
                world_id=f"world-{index}",
                record_id=f"record-{index}",
                design=design,
                evaluation=evaluation,
                wall_clock_s=0.1,
            )
    finally:
        logger.close()
    assert logger.total == 4
    assert np.allclose(logger.validation_vector(10), [0.3, 0.5, 0.7])
    assert np.allclose(logger.validation_vector(20), [0.7, 0.9, 1.1])
    assert len((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()) == 4


def test_validation_vector_fails_closed_if_checkpoint_block_is_incomplete(tmp_path: Path):
    logger = runtime.AuditWriter(
        tmp_path / "calls.jsonl", checkpoints=[10], calls_per_checkpoint=2
    )
    design = DamperDesign(np.asarray([1], dtype=int), np.asarray([50_000.0], dtype=float))
    evaluation = SimpleNamespace(
        vector=np.asarray([0.2, 0.4, 0.6]), scalar=0.5, status="valid_converged"
    )
    try:
        logger.record(
            method="ppo", seed=1103, partition="validation", state_id="3:nominal",
            world_id="world", record_id="record", design=design, evaluation=evaluation,
            wall_clock_s=0.1,
        )
    finally:
        logger.close()
    with pytest.raises(RuntimeError, match="expected 2"):
        logger.validation_vector(10)


def test_learned_hyperparameters_match_frozen_bundle():
    root = Path(__file__).resolve().parents[1]
    bundle = runtime.read_yaml(root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml")
    for method in ("ppo", "ippo", "mappo"):
        hp = runtime.learned_hyperparameters(bundle, method)
        assert hp["hidden_units"] == [128, 128]
        assert hp["batch_design_evaluations"] == 256
        assert hp["update_epochs"] == 4


def test_runtime_rejects_forbidden_waveform_file_by_partition_identity(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    ground = runtime.read_csv(root / "data/manifests/ground_motion_manifest.csv")
    forbidden = next(
        row["processed_sha256"]
        for row in ground
        if row["partition"] in {"pilot", "confirmatory"}
    )
    private_dir = tmp_path / "stage-a"
    private_dir.mkdir()
    (private_dir / f"{forbidden}.csv").write_text("not used\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="pilot/confirmatory waveform"):
        runtime.private_stage_a_index(private_dir, ground)
