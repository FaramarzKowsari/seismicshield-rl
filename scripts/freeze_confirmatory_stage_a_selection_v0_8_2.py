#!/usr/bin/env python3
"""Freeze completed v0.8.2 Stage-A selections before any confirmatory hydration.

The freezer requires all 424 Stage-A shards and exactly 2,780,992 audited Tier-1 simulator calls.
It verifies every DONE/payload hash, collects all 768 method×seed×state selected designs, retains
learned checkpoint identities, and writes an outcome-free selection manifest. It never reads or
hydrates confirmatory waveforms and never unlocks Tier-2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

EXPECTED_SCIENTIFIC_TAG = "confirmatory-v0.8.2-final"
EXPECTED_SCIENTIFIC_COMMIT = "cecd3b6c27b5deb6cb6be7ddc478cfc407a45644"
EXPECTED_PLANNER_GIT_BLOB = "87f508944b1788886a658b2e9bcc0a67e777476f"
EXPECTED_STAGE_A_SHARDS = 424
EXPECTED_STAGE_A_CALLS = 2_780_992
EXPECTED_FEATURE_SHARDS = 16
EXPECTED_NONPOLICY_SHARDS = 384
EXPECTED_LEARNED_SHARDS = 24
EXPECTED_SELECTED_DESIGNS = 6 * 8 * 16
EXPECTED_SEEDS = [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861]
EXPECTED_STATES = [
    "3:nominal", "3:lhs-1", "3:lhs-2", "3:lhs-3",
    "6:nominal", "6:lhs-1", "6:lhs-2", "6:lhs-3",
    "10:nominal", "10:lhs-1", "10:lhs-2", "10:lhs-3",
    "20:nominal", "20:lhs-1", "20:lhs-2", "20:lhs-3",
]
METHODS = ["random_search", "scalar_ga", "nsga2", "ppo", "ippo", "mappo"]
NONPOLICY = {"random_search", "scalar_ga", "nsga2"}
LEARNED = {"ppo", "ippo", "mappo"}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON must be an object: {path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _count_audit(path: Path, expected: int) -> dict[str, int]:
    counts = {"training": 0, "validation": 0}
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            partition = row.get("partition")
            if partition not in counts:
                raise RuntimeError(f"forbidden audit partition {partition!r} in {path}")
            if "vector" not in row or "scalar" not in row or "design_hash" not in row:
                raise RuntimeError(f"incomplete Stage-A audit row in {path}")
            counts[partition] += 1
            total += 1
    if total != expected:
        raise RuntimeError(f"audit row count mismatch for {path}: expected {expected}, found {total}")
    counts["total"] = total
    return counts


def _validate_workspace(workspace: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    summary = read_json(workspace / "workspace.json")
    state = read_json(workspace / "workspace_state.json")
    ledger_path = workspace / "execution_ledger.json"
    ledger = read_json(ledger_path)
    ledger_sha = sha256_path(ledger_path)
    if summary.get("status") != "PREPARED_SELECTION_ONLY":
        raise RuntimeError("selection freeze requires PREPARED_SELECTION_ONLY workspace")
    if summary.get("execution_planner_git_blob") != EXPECTED_PLANNER_GIT_BLOB:
        raise RuntimeError("workspace planner blob mismatch")
    if summary.get("scientific_source_tag") != EXPECTED_SCIENTIFIC_TAG:
        raise RuntimeError("workspace scientific tag mismatch")
    if summary.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError("workspace scientific commit mismatch")
    for document in (summary, state):
        if document.get("confirmatory_data_hydration_allowed") is not False:
            raise RuntimeError("cannot freeze selection after confirmatory hydration was permitted")
        if document.get("confirmatory_execution_allowed") is not False:
            raise RuntimeError("cannot freeze selection after confirmatory execution was permitted")
    if state.get("confirmatory_outcomes_inspected") is not False:
        raise RuntimeError("cannot freeze selection after confirmatory outcome inspection")
    if summary.get("ledger_sha256") != ledger_sha or state.get("ledger_sha256") != ledger_sha:
        raise RuntimeError("workspace ledger SHA-256 mismatch")
    return summary, state, ledger, ledger_sha


def _verify_result(
    result_dir: Path,
    shard: dict[str, Any],
    ledger_sha: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, int]]:
    done_path = result_dir / "DONE.json"
    artifact_path = result_dir / "artifact.json"
    audit_path = result_dir / "calls.jsonl"
    if not done_path.is_file() or not artifact_path.is_file() or not audit_path.is_file():
        raise RuntimeError(f"Stage-A shard result incomplete: {result_dir}")
    done = read_json(done_path)
    artifact = read_json(artifact_path)
    if done.get("status") != "PASS" or done.get("shard_id") != shard["shard_id"]:
        raise RuntimeError(f"DONE identity/status mismatch: {result_dir}")
    if done.get("phase") != shard["phase"] or artifact.get("phase") != shard["phase"]:
        raise RuntimeError(f"Stage-A phase mismatch: {result_dir}")
    if artifact.get("shard_id") != shard["shard_id"]:
        raise RuntimeError(f"artifact shard identity mismatch: {result_dir}")
    if done.get("scientific_source_tag") != EXPECTED_SCIENTIFIC_TAG:
        raise RuntimeError(f"DONE scientific tag mismatch: {result_dir}")
    if done.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError(f"DONE scientific commit mismatch: {result_dir}")
    if artifact.get("scientific_source_commit") != EXPECTED_SCIENTIFIC_COMMIT:
        raise RuntimeError(f"artifact scientific commit mismatch: {result_dir}")
    if done.get("workspace_ledger_sha256") != ledger_sha:
        raise RuntimeError(f"DONE workspace ledger mismatch: {result_dir}")
    if done.get("confirmatory_data_used") is not False:
        raise RuntimeError(f"Stage-A result claims confirmatory data use: {result_dir}")
    if done.get("confirmatory_outcomes_inspected") is not False:
        raise RuntimeError(f"Stage-A result claims confirmatory inspection: {result_dir}")
    if artifact.get("contains_waveform_bytes") is not False:
        raise RuntimeError(f"Stage-A artifact claims waveform bytes: {result_dir}")
    if artifact.get("contains_confirmatory_outcomes") is not False:
        raise RuntimeError(f"Stage-A artifact claims confirmatory outcomes: {result_dir}")
    expected_calls = int(shard["calls"])
    if int(done.get("expected_calls", -1)) != expected_calls:
        raise RuntimeError(f"DONE expected-call mismatch: {result_dir}")
    if int(artifact.get("completed_calls", -1)) != expected_calls:
        raise RuntimeError(f"artifact completed-call mismatch: {result_dir}")
    payload_hashes = done.get("payload_sha256")
    if not isinstance(payload_hashes, dict) or not payload_hashes:
        raise RuntimeError(f"missing DONE payload hashes: {result_dir}")
    for name, expected in payload_hashes.items():
        path = result_dir / name
        if not path.is_file() or sha256_path(path) != expected:
            raise RuntimeError(f"payload hash mismatch for {result_dir / name}")
    allowed_names = {"DONE.json", *payload_hashes.keys()}
    observed_names = {path.name for path in result_dir.iterdir() if path.is_file()}
    if observed_names != allowed_names:
        raise RuntimeError(
            f"unexpected Stage-A result files in {result_dir}: {sorted(observed_names - allowed_names)}"
        )
    audit_counts = _count_audit(audit_path, expected_calls)
    return done, artifact, dict(payload_hashes), audit_counts


def _design_record(value: object, expected_state: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"selected design missing for {expected_state}")
    design = value.get("design") if "design" in value else value
    design_hash = value.get("design_hash") if "design_hash" in value else None
    if not isinstance(design, dict):
        raise RuntimeError(f"selected design is not an object for {expected_state}")
    counts = design.get("counts")
    slips = design.get("slip_force_n")
    height = int(expected_state.split(":", 1)[0])
    if not isinstance(counts, list) or not isinstance(slips, list) or len(counts) != height or len(slips) != height:
        raise RuntimeError(f"selected design dimensions mismatch for {expected_state}")
    for count in counts:
        if int(count) != count or not (0 <= int(count) <= 4):
            raise RuntimeError(f"selected damper count outside frozen bounds for {expected_state}")
    allowed_slips = {0.0, 50_000.0, 100_000.0, 200_000.0, 350_000.0}
    for count, slip in zip(counts, slips, strict=True):
        if float(slip) not in allowed_slips:
            raise RuntimeError(f"selected slip force outside frozen grid for {expected_state}")
        if int(count) == 0 and float(slip) != 0.0:
            raise RuntimeError(f"zero-count slip was not canonicalized for {expected_state}")
    canonical = json.dumps(
        {"counts": [int(v) for v in counts], "slip_force_n": [float(v) for v in slips]},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    observed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if design_hash is not None and design_hash != observed_hash:
        raise RuntimeError(f"selected design hash mismatch for {expected_state}")
    return {"design": json.loads(canonical), "design_hash": observed_hash}


def build_selection_freeze(workspace: Path, results_root: Path) -> dict[str, Any]:
    summary, state, ledger, ledger_sha = _validate_workspace(workspace)
    selection = [shard for shard in ledger.get("shards", []) if str(shard.get("phase", "")).startswith("tier1_")]
    if len(selection) != EXPECTED_STAGE_A_SHARDS:
        raise RuntimeError(f"expected {EXPECTED_STAGE_A_SHARDS} Stage-A shards, found {len(selection)}")
    if sum(int(shard["calls"]) for shard in selection) != EXPECTED_STAGE_A_CALLS:
        raise RuntimeError("Stage-A ledger call accounting mismatch")

    shard_manifest: list[dict[str, Any]] = []
    selected: dict[str, dict[str, dict[str, Any]]] = {method: {} for method in METHODS}
    learned_checkpoints: dict[str, dict[str, Any]] = {method: {} for method in sorted(LEARNED)}
    phase_counts = {"tier1_feature_precompute": 0, "tier1_train_validate_nonpolicy": 0, "tier1_train_validate_learned": 0}
    completed_calls = 0

    for shard in sorted(selection, key=lambda item: item["shard_id"]):
        shard_id = shard["shard_id"]
        result_dir = results_root / shard_id
        done, artifact, payload_hashes, audit_counts = _verify_result(result_dir, shard, ledger_sha)
        phase = shard["phase"]
        if phase not in phase_counts:
            raise RuntimeError(f"unexpected Stage-A phase {phase!r}")
        phase_counts[phase] += 1
        completed_calls += int(shard["calls"])
        descriptor = {
            "shard_id": shard_id,
            "phase": phase,
            "method": shard.get("method"),
            "seed": shard.get("seed"),
            "structural_state_id": shard.get("structural_state_id"),
            "calls": int(shard["calls"]),
            "done_sha256": sha256_path(result_dir / "DONE.json"),
            "payload_sha256": payload_hashes,
            "audit_partition_counts": audit_counts,
            "runtime_git_blob": done.get("runtime_git_blob"),
            "runner_git_blob": done.get("runner_git_blob"),
        }
        shard_manifest.append(descriptor)

        if phase == "tier1_train_validate_nonpolicy":
            method = str(shard["method"])
            seed = int(shard["seed"])
            state_id = str(shard["structural_state_id"])
            if method not in NONPOLICY or seed not in EXPECTED_SEEDS or state_id not in EXPECTED_STATES:
                raise RuntimeError(f"unexpected nonpolicy shard identity {method}/{seed}/{state_id}")
            seed_key = str(seed)
            selected[method].setdefault(seed_key, {})
            if state_id in selected[method][seed_key]:
                raise RuntimeError(f"duplicate selected design {method}/{seed}/{state_id}")
            selected[method][seed_key][state_id] = _design_record(
                {
                    "design": artifact.get("selected_design"),
                    "design_hash": artifact.get("selected_design_hash"),
                },
                state_id,
            )
        elif phase == "tier1_train_validate_learned":
            method = str(shard["method"])
            seed = int(shard["seed"])
            if method not in LEARNED or seed not in EXPECTED_SEEDS:
                raise RuntimeError(f"unexpected learned shard identity {method}/{seed}")
            seed_key = str(seed)
            if seed_key in selected[method] or seed_key in learned_checkpoints[method]:
                raise RuntimeError(f"duplicate learned selection {method}/{seed}")
            designs = artifact.get("selected_designs")
            if not isinstance(designs, dict) or set(designs) != set(EXPECTED_STATES):
                raise RuntimeError(f"learned selected-design state set mismatch for {method}/{seed}")
            selected[method][seed_key] = {
                state_id: _design_record(designs[state_id], state_id)
                for state_id in EXPECTED_STATES
            }
            checkpoint_name = artifact.get("checkpoint_file")
            if checkpoint_name != "checkpoint.npz" or checkpoint_name not in payload_hashes:
                raise RuntimeError(f"learned checkpoint payload missing for {method}/{seed}")
            checkpoint_call = int(artifact.get("selected_checkpoint_training_call", -1))
            if checkpoint_call not in {5120,10240,15360,20480,25600,30720,35840,40960,46080,51200}:
                raise RuntimeError(f"learned checkpoint call outside frozen schedule for {method}/{seed}")
            vector = artifact.get("selected_checkpoint_validation_vector")
            if not isinstance(vector, list) or len(vector) != 3:
                raise RuntimeError(f"learned checkpoint vector missing for {method}/{seed}")
            learned_checkpoints[method][seed_key] = {
                "training_call": checkpoint_call,
                "validation_calls": int(artifact.get("selected_checkpoint_validation_calls", -1)),
                "validation_scalar": float(artifact.get("selected_checkpoint_validation_scalar")),
                "validation_vector": [float(v) for v in vector],
                "checkpoint_sha256": payload_hashes[checkpoint_name],
            }

    if phase_counts != {
        "tier1_feature_precompute": EXPECTED_FEATURE_SHARDS,
        "tier1_train_validate_nonpolicy": EXPECTED_NONPOLICY_SHARDS,
        "tier1_train_validate_learned": EXPECTED_LEARNED_SHARDS,
    }:
        raise RuntimeError(f"completed Stage-A phase counts mismatch: {phase_counts}")
    if completed_calls != EXPECTED_STAGE_A_CALLS:
        raise RuntimeError(f"completed Stage-A call count mismatch: {completed_calls}")

    selected_count = 0
    for method in METHODS:
        if set(selected[method]) != {str(seed) for seed in EXPECTED_SEEDS}:
            raise RuntimeError(f"selected seed set mismatch for {method}")
        for seed in EXPECTED_SEEDS:
            states = selected[method][str(seed)]
            if set(states) != set(EXPECTED_STATES):
                raise RuntimeError(f"selected structural-state set mismatch for {method}/{seed}")
            selected_count += len(states)
    if selected_count != EXPECTED_SELECTED_DESIGNS:
        raise RuntimeError(f"expected {EXPECTED_SELECTED_DESIGNS} selected designs, found {selected_count}")

    shard_root_payload = json.dumps(shard_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    selected_payload = json.dumps(selected, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "schema": "confirmatory-stage-a-selection-freeze-v1",
        "status": "SELECTION_COMPLETE_CONFIRMATORY_STILL_LOCKED",
        "scientific_source_tag": EXPECTED_SCIENTIFIC_TAG,
        "scientific_source_commit": EXPECTED_SCIENTIFIC_COMMIT,
        "execution_planner_git_blob": EXPECTED_PLANNER_GIT_BLOB,
        "workspace_ledger_sha256": ledger_sha,
        "stage_a_shards": EXPECTED_STAGE_A_SHARDS,
        "stage_a_completed_calls": completed_calls,
        "selected_design_count": selected_count,
        "confirmatory_data_hydrated": False,
        "confirmatory_execution_allowed": False,
        "confirmatory_outcomes_inspected": False,
        "shard_result_manifest_sha256": hashlib.sha256(shard_root_payload.encode("utf-8")).hexdigest(),
        "selected_designs_sha256": hashlib.sha256(selected_payload.encode("utf-8")).hexdigest(),
        "shard_results": shard_manifest,
        "selected_designs": selected,
        "learned_checkpoints": learned_checkpoints,
        "next_irreversible_boundary": "publish_this_selection_freeze_at_an_immutable_git_ref_before_any_confirmatory_hydration",
    }


def write_freeze(path: Path, freeze: dict[str, Any]) -> str:
    payload = _canonical_bytes(freeze)
    digest = hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"existing selection freeze differs: {path}")
        return digest
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return digest


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--results-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / "results/local/confirmatory_v0.8.2"
    workspace = (args.workspace or base / "execution_workspace").resolve()
    results_root = (args.results_root or base / "stage_a/shards").resolve()
    output = (
        args.output.resolve()
        if args.output is not None
        else (base / "selection_freeze/selection_freeze_v0.8.2.json").resolve()
    )
    try:
        freeze = build_selection_freeze(workspace, results_root)
        digest = write_freeze(output, freeze)
        print("Stage-A selection freeze: PASS")
        print(f"Selection freeze: {output}")
        print(f"Selection freeze SHA-256: {digest}")
        print(f"Selected designs: {freeze['selected_design_count']}")
        print("Confirmatory hydration allowed: false")
        print("Confirmatory execution allowed: false")
        return 0
    except Exception as exc:
        print(f"Stage-A selection freeze: BLOCKED\n- {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
