from pathlib import Path

import pytest

import scripts.finalize_confirmatory_gate_local as finalizer


def test_finalizer_allows_only_manifest_and_gate_worktree_changes(monkeypatch):
    monkeypatch.setattr(
        finalizer,
        "_status_paths",
        lambda _root: {
            "data/manifests/ground_motion_manifest.csv",
            "data/manifests/ground_motion_manifest.csv.sha256",
        },
    )
    finalizer._assert_only_allowed_dirty_paths(Path("."))


def test_finalizer_rejects_unrelated_worktree_changes(monkeypatch):
    monkeypatch.setattr(
        finalizer,
        "_status_paths",
        lambda _root: {"data/manifests/ground_motion_manifest.csv", "README.md"},
    )
    with pytest.raises(RuntimeError, match="unrelated working-tree changes"):
        finalizer._assert_only_allowed_dirty_paths(Path("."))


def test_preflight_gate_allows_only_missing_final_tag(monkeypatch):
    monkeypatch.setattr(
        finalizer,
        "check_gate",
        lambda _root, _gate: (
            False,
            [f"Required source Git tag '{finalizer.FINAL_SOURCE_TAG}' does not exist."],
        ),
    )
    finalizer._preflight_gate(Path("."), Path("gate.yaml"))


def test_preflight_gate_rejects_any_other_blocker(monkeypatch):
    monkeypatch.setattr(
        finalizer,
        "check_gate",
        lambda _root, _gate: (
            False,
            [
                f"Required source Git tag '{finalizer.FINAL_SOURCE_TAG}' does not exist.",
                "Structural-world manifest SHA-256 is absent or does not match.",
            ],
        ),
    )
    with pytest.raises(RuntimeError, match="unexpected blockers"):
        finalizer._preflight_gate(Path("."), Path("gate.yaml"))


def test_finalizer_never_moves_an_existing_final_tag_name():
    assert finalizer.FINAL_SOURCE_TAG == "confirmatory-v0.8.1-final"
