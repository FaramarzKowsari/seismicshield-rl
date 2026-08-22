import hashlib
import subprocess
from pathlib import Path

import yaml

from scripts.check_confirmatory_gate import (
    check_gate,
    digest_matches,
    validate_seed_ledger,
    validate_source_tag,
)
from scripts.finalize_confirmatory_gate_v0_8_2_local import (
    EXPECTED_ANALYSIS_EVIDENCE_SHA256,
    EXPECTED_ANALYSIS_SHA256,
    EXPECTED_EXECUTION_EVIDENCE_SHA256,
    EXPECTED_EXECUTION_SHA256,
    EXPECTED_GATE_VERSION,
    EXPECTED_VALIDATION_ARTIFACT_SHA256,
    EXPECTED_VALIDATION_RUN,
    FINAL_SOURCE_TAG,
    PARENT_SOURCE_TAG,
)


def _gate_data(root: Path) -> dict:
    data = yaml.safe_load(
        (root / "open_science/confirmatory_gate_v0.8.0.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(data, dict)
    return data


def test_v0_8_2_gate_has_only_the_expected_source_state():
    root = Path(__file__).resolve().parents[1]
    data = _gate_data(root)
    ok, reasons = check_gate(root, root / "open_science/confirmatory_gate_v0.8.0.yaml")

    assert not any("OSF registration status is not public" in reason for reason in reasons)
    assert not any("identifier does not match preregistration" in reason for reason in reasons)
    assert not any("Frozen numerical config SHA-256" in reason for reason in reasons)
    assert not any("Confirmatory algorithm bundle SHA-256" in reason for reason in reasons)
    assert not any("Confirmatory execution v0.8.2 contract SHA-256" in reason for reason in reasons)
    assert not any("Confirmatory analysis v0.8.2 contract SHA-256" in reason for reason in reasons)

    source_tag = data.get("source_git_tag")
    runs_allowed = data.get("confirmatory_runs_allowed")
    if (source_tag, runs_allowed) == (PARENT_SOURCE_TAG, False):
        # Pre-finalization state: execution must remain closed, and the parent immutable
        # tag must not equal the newer v0.8.2 development/finalization HEAD.
        assert not ok
        assert "confirmatory_runs_allowed is false." in reasons
        assert any(
            "does not equal HEAD" in reason
            or ("Required source Git tag" in reason and "does not exist" in reason)
            for reason in reasons
        )
    elif (source_tag, runs_allowed) == (FINAL_SOURCE_TAG, True):
        # Finalized state: a normal local checkout with tags must PASS. GitHub Actions
        # uses fetch-depth=1/fetch-tags=false by default, so CI may legitimately see
        # only the missing-tag blocker even though the tag exists in the remote repo.
        if not ok:
            assert reasons == [f"Required source Git tag {FINAL_SOURCE_TAG!r} does not exist."]
    else:
        raise AssertionError(
            "gate source state must be exactly pre-finalization or immutable-final: "
            f"tag={source_tag!r}, confirmatory_runs_allowed={runs_allowed!r}"
        )


def test_v0_8_2_gate_records_exact_public_validation_evidence():
    root = Path(__file__).resolve().parents[1]
    data = _gate_data(root)
    assert data["version"] == EXPECTED_GATE_VERSION
    assert (data["source_git_tag"], data["confirmatory_runs_allowed"]) in {
        (PARENT_SOURCE_TAG, False),
        (FINAL_SOURCE_TAG, True),
    }
    assert data["confirmatory_execution_contract_sha256"] == EXPECTED_EXECUTION_SHA256
    assert data["confirmatory_analysis_contract_sha256"] == EXPECTED_ANALYSIS_SHA256
    assert data["confirmatory_execution_validation_workflow_run"] == EXPECTED_VALIDATION_RUN
    assert data["confirmatory_analysis_validation_workflow_run"] == EXPECTED_VALIDATION_RUN
    assert (
        data["confirmatory_execution_validation_evidence_sha256"]
        == EXPECTED_EXECUTION_EVIDENCE_SHA256
    )
    assert (
        data["confirmatory_analysis_validation_evidence_sha256"]
        == EXPECTED_ANALYSIS_EVIDENCE_SHA256
    )
    assert (
        data["confirmatory_execution_validation_artifact_sha256"]
        == EXPECTED_VALIDATION_ARTIFACT_SHA256
    )
    assert (
        data["confirmatory_analysis_validation_artifact_sha256"]
        == EXPECTED_VALIDATION_ARTIFACT_SHA256
    )


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


def test_digest_matches_canonical_git_blob_when_worktree_has_crlf(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Software Validation Fixture")
    _git(tmp_path, "config", "user.email", "fixture@invalid.local")
    path = tmp_path / "contract.yaml"
    canonical = b"version: 1\nstatus: frozen\n"
    path.write_bytes(canonical)
    _git(tmp_path, "add", path.name)
    _git(tmp_path, "commit", "-q", "-m", "freeze canonical contract")
    expected = hashlib.sha256(canonical).hexdigest()

    path.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert hashlib.sha256(path.read_bytes()).hexdigest() != expected
    assert digest_matches(tmp_path, path.name, expected)


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
