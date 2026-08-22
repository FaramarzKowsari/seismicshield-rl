import subprocess
from pathlib import Path

import yaml

from scripts.check_confirmatory_gate import check_gate, validate_seed_ledger, validate_source_tag


def test_confirmatory_gate_remains_blocked_after_public_registration_until_other_prerequisites_are_met():
    root = Path(__file__).resolve().parents[1]
    ok, reasons = check_gate(root, root / "open_science/confirmatory_gate_v0.8.0.yaml")
    assert not ok
    assert not any("OSF registration status is not public" in reason for reason in reasons)
    assert not any("identifier does not match preregistration" in reason for reason in reasons)
    assert any("confirmatory_runs_allowed is false" in reason for reason in reasons)


def _mutated_ledger(tmp_path: Path, mutation) -> Path:
    source = Path(__file__).resolve().parents[1] / "open_science/seed_ledger_v0.8.0.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    mutation(data)
    path = tmp_path / "seed-ledger.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_seed_ledger_rejects_null_bootstrap_seed(tmp_path: Path):
    path = _mutated_ledger(
        tmp_path, lambda data: data["bootstrap_resampling"].update(random_seed=None)
    )
    assert any("bootstrap_random_seed mismatch" in error for error in validate_seed_ledger(path))


def test_seed_ledger_rejects_altered_algorithm_seed(tmp_path: Path):
    path = _mutated_ledger(tmp_path, lambda data: data["algorithm_seeds"].__setitem__(0, 1104))
    assert any("algorithm_seeds mismatch" in error for error in validate_seed_ledger(path))


def test_seed_ledger_rejects_altered_lhs_seed(tmp_path: Path):
    path = _mutated_ledger(
        tmp_path, lambda data: data.update(structural_latin_hypercube_seed=24681358)
    )
    assert any(
        "structural_latin_hypercube_seed mismatch" in error
        for error in validate_seed_ledger(path)
    )


def test_seed_ledger_rejects_altered_manifest_salt(tmp_path: Path):
    path = _mutated_ledger(
        tmp_path,
        lambda data: data["manifest_deterministic_selection"].update(salt="altered"),
    )
    assert any("manifest_salt mismatch" in error for error in validate_seed_ledger(path))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def test_source_git_tag_missing_is_rejected(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _, error = validate_source_tag(tmp_path, "confirmatory-v0.8.0")
    assert error == "Required source Git tag 'confirmatory-v0.8.0' does not exist."


def test_source_git_tag_pointing_to_wrong_commit_is_rejected(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Software Validation Fixture")
    _git(tmp_path, "config", "user.email", "fixture@invalid.local")
    fixture = tmp_path / "software-validation-fixture.txt"
    fixture.write_text("first\n", encoding="utf-8")
    _git(tmp_path, "add", fixture.name)
    _git(tmp_path, "commit", "-q", "-m", "fixture commit one")
    tagged_sha = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "tag", "confirmatory-v0.8.0")
    fixture.write_text("second\n", encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "fixture commit two")

    resolved, error = validate_source_tag(tmp_path, "confirmatory-v0.8.0")
    assert resolved == tagged_sha
    assert error and "does not equal HEAD" in error
