from pathlib import Path

from scripts.plan_confirmatory_execution_v0_8_2 import build_plan


def test_execution_ledger_reproduces_exact_frozen_call_accounting():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    summary = plan["summary"]
    assert summary["total_shards"] == 883
    assert summary["tier1_calls"] == 2_780_992
    assert summary["tier2_calls"] == 39_168
    assert summary["total_calls"] == 2_820_160
    assert summary["phase_calls"] == {
        "tier1_feature_precompute": 832,
        "tier1_training_learned": 1_228_800,
        "tier1_training_nonpolicy": 1_228_800,
        "tier1_validation_learned": 76_800,
        "tier1_validation_nonpolicy": 245_760,
        "tier2_confirmatory_seeded": 36_864,
        "tier2_confirmatory_support": 2_304,
    }
    assert summary["phase_shards"] == {
        "tier1_feature_precompute": 16,
        "tier1_training_learned": 24,
        "tier1_training_nonpolicy": 384,
        "tier1_validation_learned": 24,
        "tier1_validation_nonpolicy": 384,
        "tier2_confirmatory_seeded": 48,
        "tier2_confirmatory_support": 3,
    }


def test_learned_training_is_never_split_into_independent_state_jobs():
    root = Path(__file__).resolve().parents[1]
    plan = build_plan(root)
    learned = [
        shard for shard in plan["shards"] if shard["phase"] == "tier1_training_learned"
    ]
    assert len(learned) == 3 * 8
    assert {shard["calls"] for shard in learned} == {51_200}
    assert {shard["calls_per_state"] for shard in learned} == {3_200}
    assert {shard["structural_states"] for shard in learned} == {16}
    assert all(shard["structural_state_id"] is None for shard in learned)
    assert all(
        shard["atomic_reason"] == "shared_policy_budget_across_all_16_structural_states"
        for shard in learned
    )


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
    assert all(shard["partition"] != "pilot" for shard in plan["shards"])
    assert all("record_id" not in shard for shard in plan["shards"])
    assert all("vector" not in shard and "scalar" not in shard for shard in plan["shards"])


def test_ledger_replay_is_deterministic_and_shard_ids_are_unique():
    root = Path(__file__).resolve().parents[1]
    first = build_plan(root)
    second = build_plan(root)
    assert first == second
    shard_ids = [shard["shard_id"] for shard in first["shards"]]
    assert len(shard_ids) == len(set(shard_ids)) == 883
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
