from pathlib import Path

import pytest

pytest.importorskip("openseespy.opensees")

from scripts.validate_tier2_backend import run_validation


def test_tier2_validation_contract_passes_on_public_synthetic_fixture():
    root = Path(__file__).resolve().parents[1]
    evidence, failures = run_validation(
        root, root / "open_science/tier2_validation_contract_v0.8.1.yaml"
    )
    assert failures == [], evidence
    assert evidence["status"] == "PASS"
    assert evidence["confirmatory_ground_motion_used"] is False
