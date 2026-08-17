import json
from pathlib import Path

from scripts.check_preregistration_gate import check_gate


def test_gate_blocks_draft(tmp_path: Path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({
        "status": "draft",
        "doi": None,
        "prior_pilot_disclosed": True,
        "confirmatory_runs_allowed": False,
    }))
    ok, reasons = check_gate(p)
    assert not ok
    assert reasons


def test_gate_accepts_public_preregistration(tmp_path: Path):
    p = tmp_path / "p.json"
    p.write_text(json.dumps({
        "status": "public",
        "doi": "10.17605/OSF.IO/ABCDE",
        "prior_pilot_disclosed": True,
        "confirmatory_runs_allowed": True,
    }))
    ok, reasons = check_gate(p)
    assert ok
    assert reasons == []
