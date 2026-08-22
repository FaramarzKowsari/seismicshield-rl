from pathlib import Path

import pytest

pytest.importorskip("torch")

from scripts.validate_confirmatory_algorithms import run_smoke, validate_contract


def test_confirmatory_algorithm_contract_matches_preregistered_budget_and_seed_ledger():
    root = Path(__file__).resolve().parents[1]
    bundle = root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml"
    evidence, failures = validate_contract(root, bundle)
    assert failures == [], evidence
    assert evidence["confirmatory_waveform_used"] is False


def test_confirmatory_algorithm_public_synthetic_smoke_passes_and_replays():
    root = Path(__file__).resolve().parents[1]
    bundle = root / "open_science/confirmatory_algorithm_bundle_v0.8.1.yaml"
    evidence, failures = run_smoke(root, bundle)
    assert failures == [], evidence
    assert evidence["status"] == "PASS"
    assert set(evidence["smoke"]) == {"random_search", "nsga2", "ppo", "ippo", "mappo"}
    assert all(result["evaluations"] == 64 for result in evidence["smoke"].values())
