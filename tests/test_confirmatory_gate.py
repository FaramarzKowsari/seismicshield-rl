from pathlib import Path

from scripts.check_confirmatory_gate import check_gate


def test_confirmatory_gate_remains_blocked_before_registration():
    root = Path(__file__).resolve().parents[1]
    ok, reasons = check_gate(root, root / "open_science/confirmatory_gate_v0.8.0.yaml")
    assert not ok
    assert any("OSF registration" in reason for reason in reasons)

