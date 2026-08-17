from __future__ import annotations

import json
from pathlib import Path


def check_gate(path: Path) -> tuple[bool, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    reasons: list[str] = []
    if data.get("status") != "public":
        reasons.append("OSF preregistration status is not 'public'.")
    doi = data.get("doi")
    if not isinstance(doi, str) or not doi.startswith("10.17605/OSF.IO/"):
        reasons.append("A valid public OSF registration DOI is not recorded.")
    if not data.get("prior_pilot_disclosed"):
        reasons.append("Prior pilot/software-validation work has not been disclosed.")
    if not data.get("confirmatory_runs_allowed"):
        reasons.append("confirmatory_runs_allowed is false.")
    return not reasons, reasons


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ok, reasons = check_gate(root / "open_science" / "preregistration.json")
    if ok:
        print("Preregistration gate: PASS")
        return 0
    print("Preregistration gate: BLOCKED")
    for reason in reasons:
        print(f"- {reason}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
