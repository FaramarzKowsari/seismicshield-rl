from pathlib import Path

import yaml


FREEZE = Path("open_science/confirmatory_freeze_v0.8.0.yaml")
GATE = Path("open_science/confirmatory_gate_v0.8.0.yaml")
AMENDMENT = Path("open_science/ground_motion_source_amendment_v0.8.0.md")


def test_freeze_uses_esm_only_primary_source_contract():
    text = FREEZE.read_text(encoding="utf-8")
    assert "esm_contract:" in text
    assert "canonical_source: ESM" in text
    assert "canonical_record_id: exact_source_distributed_ESM_ASCII_basename" in text
    assert "eligible_accelerometric_families: [HN, HG, HL]" in text
    assert "afad_tadas_contract:" not in text
    assert "salt: SeismicShield-RL-v0.8.0-OSF-2026" in text
    assert "physical_events: 40" in text
    assert "records_per_event: 4" in text
    assert "total_records: 160" in text


def test_amendment_explicitly_precedes_registration_and_confirmatory_results():
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "before OSF registration submission" in text
    assert "before any confirmatory simulation result is inspected" in text
    assert "ESM-only" in text
    assert "AFAD/TADAS" in text


def test_public_osf_and_v0_8_2_gate_state_are_recorded():
    data = yaml.safe_load(GATE.read_text(encoding="utf-8"))
    assert data["version"] == "v0.8.2"
    assert data["osf_registration_status"] == "public"
    assert data["osf_registration_persistent_id"] == "https://doi.org/10.17605/OSF.IO/64DTX"
    assert data["structural_world_manifest_validated"] is True
    assert data["tier_2_backend_validated"] is True
    assert data["confirmatory_execution_validated"] is True
    assert data["confirmatory_analysis_validated"] is True
    assert (data["source_git_tag"], data["confirmatory_runs_allowed"]) in {
        ("confirmatory-v0.8.1-final", False),
        ("confirmatory-v0.8.2-final", True),
    }
