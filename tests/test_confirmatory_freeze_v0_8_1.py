from pathlib import Path


AMENDMENT = Path("open_science/confirmatory_freeze_v0.8.1_amendment.yaml")
LICENSE_NOTE = Path("open_science/ground_motion_license_amendment_v0.8.1.md")
GATE = Path("open_science/confirmatory_gate_v0.8.0.yaml")


def test_v0_8_1_amendment_freezes_license_clean_34_event_design():
    text = AMENDMENT.read_text(encoding="utf-8")
    assert "base_freeze: open_science/confirmatory_freeze_v0.8.0.yaml" in text
    assert "source_hash_queue_events: 63" in text
    assert "accepted_license_prefixes: [CC-BY3_0-IT, CC-BY4_0]" in text
    assert "network_default_license_D_accepted: false" in text
    assert "unknown_license_U_accepted: false" in text
    assert "selected_events: 34" in text
    assert "total_records: 136" in text
    assert "training: {events: 13, records: 52}" in text
    assert "validation: {events: 5, records: 20}" in text
    assert "pilot: {events: 4, records: 16" in text
    assert "confirmatory: {events: 12, records: 48}" in text
    assert "SeismicShield-RL-v0.8.0-OSF-2026" in text


def test_license_amendment_precedes_osf_and_confirmatory_outcomes():
    text = LICENSE_NOTE.read_text(encoding="utf-8")
    assert "before OSF registration submission" in text
    assert "before any confirmatory simulation result was inspected" in text
    assert "34 events × 4 records = 136 records" in text
    assert "D (network default license)" in text
    assert "U (unknown license)" in text


def test_v0_8_1_does_not_open_confirmatory_gate():
    text = GATE.read_text(encoding="utf-8")
    assert "osf_registration_status: pending" in text
    assert "osf_registration_persistent_id: null" in text
    assert "confirmatory_runs_allowed: false" in text
