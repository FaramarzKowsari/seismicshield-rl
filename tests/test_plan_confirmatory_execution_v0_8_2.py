from pathlib import Path

import pytest

from scripts.plan_confirmatory_execution_v0_8_2 import (
    EXPECTED_ALGORITHM_SEEDS,
    EXPECTED_SHARDS,
    _frozen_python_env,
    build_plan,
    frozen_algorithm_seeds,
)


def test_execution_ledger_reproduces_exact_frozen_call_accounting():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    summary = plan["summary"]
    assert summary["total_shards"] == EXPECTED_SHARDS == 475
    assert summary["tier1_calls"] == 2_780_992
    assert summary["tier2_calls"] == 39_168
    assert summary["total_calls"] == 2_820_160
    assert summary["phase_calls"] == {
        "tier1_feature_precompute": 832,
        "tier1_train_validate_learned": 1_305_600,
        "tier1_train_validate_nonpolicy": 1_474_560,
        "tier2_confirmatory_seeded": 36_864,
        "tier2_confirmatory_support": 2_304,
    }
    assert summary["phase_shards"] == {
        "tier1_feature_precompute": 16,
        "tier1_train_validate_learned": 24,
        "tier1_train_validate_nonpolicy": 384,
        "tier2_confirmatory_seeded": 48,
        "tier2_confirmatory_support": 3,
    }


def test_seed_helper_accepts_only_exact_preregistered_values():
    assert frozen_algorithm_seeds({"algorithm_seeds": EXPECTED_ALGORITHM_SEEDS}) == (
        EXPECTED_ALGORITHM_SEEDS
    )
    mutated = list(EXPECTED_ALGORITHM_SEEDS)
    mutated[0] = 1104
    with pytest.raises(ValueError, match="exact preregistered values"):
        frozen_algorithm_seeds({"algorithm_seeds": mutated})
    with pytest.raises(ValueError, match="exact preregistered values"):
        frozen_algorithm_seeds({"algorithm_seeds": EXPECTED_ALGORITHM_SEEDS[:-1]})


def test_frozen_python_env_replaces_inherited_pythonpath(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PYTHONPATH", "/development/editable/src")
    env = _frozen_python_env(tmp_path)
    assert env["PYTHONPATH"] == str((tmp_path / "src").resolve())
    assert "/development/editable/src" not in env["PYTHONPATH"]


def test_nonpolicy_training_and_candidate_validation_stay_atomic():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    nonpolicy = [
        shard for shard in plan["shards"] if shard["phase"] == "tier1_train_validate_nonpolicy"
    ]
    assert len(nonpolicy) == 3 * 8 * 16
    assert {shard["calls"] for shard in nonpolicy} == {3_840}
    assert {shard["training_calls"] for shard in nonpolicy} == {3_200}
    assert {shard["validation_calls"] for shard in nonpolicy} == {640}
    assert {shard["candidate_pool"] for shard in nonpolicy} == {32}
    assert {shard["partition"] for shard in nonpolicy} == {"training+validation"}
    assert all(shard["structural_state_id"] is not None for shard in nonpolicy)
    assert all(
        shard["atomic_reason"] == "candidate_archive_and_validation_selection_stay_in_memory"
        for shard in nonpolicy
    )
    assert not any(shard["phase"] == "tier1_training_nonpolicy" for shard in plan["shards"])
    assert not any(shard["phase"] == "tier1_validation_nonpolicy" for shard in plan["shards"])


def test_learned_training_and_checkpoint_validation_stay_atomic():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    learned = [
        shard for shard in plan["shards"] if shard["phase"] == "tier1_train_validate_learned"
    ]
    assert len(learned) == 3 * 8
    assert {shard["calls"] for shard in learned} == {54_400}
    assert {shard["training_calls"] for shard in learned} == {51_200}
    assert {shard["training_calls_per_state"] for shard in learned} == {3_200}
    assert {shard["validation_calls"] for shard in learned} == {3_200}
    assert {shard["checkpoints"] for shard in learned} == {10}
    assert {shard["validation_calls_per_checkpoint"] for shard in learned} == {320}
    assert {shard["structural_states"] for shard in learned} == {16}
    assert {shard["partition"] for shard in learned} == {"training+validation"}
    assert all(shard["structural_state_id"] is None for shard in learned)
    assert all(
        shard["atomic_reason"] == "frozen_training_loop_performs_checkpoint_validation_inline"
        for shard in learned
    )
    assert not any(shard["phase"] == "tier1_validation_learned" for shard in plan["shards"])


def test_tier2_shards_match_768_worlds_per_method_seed_and_support_method():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    seeded = [
        shard for shard in plan["shards"] if shard["phase"] == "tier2_confirmatory_seeded"
    ]
    support = [
        shard for shard in plan["shards"] if shard["phase"] == "tier2_confirmatory_support"
    ]
    assert len(seeded) == 6 * 8
    assert len(support) == 3
    assert {shard["calls"] for shard in seeded + support} == {768}
    assert {shard["records_per_state"] for shard in seeded + support} == {48}
    assert {shard["structural_states"] for shard in seeded + support} == {16}


def test_ledger_contains_no_pilot_work_and_no_waveform_or_outcome_payloads():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    assert plan["contains_waveform_bytes"] is False
    assert plan["contains_response_outcomes"] is False
    assert plan["pilot_partition_in_execution_ledger"] is False
    assert all("pilot" not in shard["partition"] for shard in plan["shards"])
    assert all("record_id" not in shard for shard in plan["shards"])
    assert all("vector" not in shard and "scalar" not in shard for shard in plan["shards"])


def test_ledger_replay_is_deterministic_and_shard_ids_are_unique():
    root = Path(__file__).resolve().parents[1]
    first = build_plan(root)
    second = build_plan(root)
    assert first == second
    shard_ids = [shard["shard_id"] for shard in first["shards"]]
    assert len(shard_ids) == len(set(shard_ids)) == EXPECTED_SHARDS
    assert first["algorithm_seeds"] == EXPECTED_ALGORITHM_SEEDS
    assert first["structural_states"] == [
        "3:nominal",
        "3:lhs-1",
        "3:lhs-2",
        "3:lhs-3",
        "6:nominal",
        "6:lhs-1",
        "6:lhs-2",
        "6:lhs-3",
        "10:nominal",
        "10:lhs-1",
        "10:lhs-2",
        "10:lhs-3",
        "20:nominal",
        "20:lhs-1",
        "20:lhs-2",
        "20:lhs-3",
    ]
