#!/usr/bin/env python3
"""Orchestrate all 424 v0.8.2 Stage-A selection shards; never run Tier-2.

Each scientific shard remains an independent atomic process. Parallelism is only across shard
boundaries already declared independent by the reviewed 475-shard execution ledger. Feature
precomputation completes before any optimizer shard. Failed shards are reported and never
partially resumed; re-running the orchestrator reuses only hash-verified DONE results.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any

EXPECTED_STAGE_A_SHARDS = 424
EXPECTED_STAGE_A_CALLS = 2_780_992
PHASE_ORDER = (
    "tier1_feature_precompute",
    "tier1_train_validate_nonpolicy",
    "tier1_train_validate_learned",
)
EXPECTED_PHASE_SHARDS = {
    "tier1_feature_precompute": 16,
    "tier1_train_validate_nonpolicy": 384,
    "tier1_train_validate_learned": 24,
}
EXPECTED_PHASE_CALLS = {
    "tier1_feature_precompute": 832,
    "tier1_train_validate_nonpolicy": 1_474_560,
    "tier1_train_validate_learned": 1_305_600,
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON must be an object: {path}")
    return value


def selection_shards(workspace: Path) -> dict[str, list[dict[str, Any]]]:
    summary = read_json(workspace / "workspace.json")
    state = read_json(workspace / "workspace_state.json")
    ledger = read_json(workspace / "execution_ledger.json")
    if summary.get("confirmatory_execution_allowed") is not False:
        raise RuntimeError("Stage-A orchestrator refuses a workspace permitting confirmatory execution")
    if summary.get("confirmatory_data_hydration_allowed") is not False:
        raise RuntimeError("Stage-A orchestrator refuses a workspace permitting confirmatory hydration")
    if state.get("confirmatory_outcomes_inspected") is not False:
        raise RuntimeError("Stage-A orchestrator refuses a workspace after confirmatory inspection")
    phases = {phase: [] for phase in PHASE_ORDER}
    for shard in ledger.get("shards", []):
        phase = shard.get("phase")
        if phase in phases:
            phases[phase].append(shard)
        elif str(phase).startswith("tier2_"):
            continue
        else:
            raise RuntimeError(f"unexpected ledger phase {phase!r}")
    for phase in PHASE_ORDER:
        if len(phases[phase]) != EXPECTED_PHASE_SHARDS[phase]:
            raise RuntimeError(
                f"Stage-A phase shard count mismatch for {phase}: {len(phases[phase])}"
            )
        calls = sum(int(shard["calls"]) for shard in phases[phase])
        if calls != EXPECTED_PHASE_CALLS[phase]:
            raise RuntimeError(f"Stage-A phase call count mismatch for {phase}: {calls}")
        phases[phase].sort(key=lambda item: item["shard_id"])
    if sum(len(items) for items in phases.values()) != EXPECTED_STAGE_A_SHARDS:
        raise RuntimeError("Stage-A total shard count mismatch")
    if sum(int(item["calls"]) for items in phases.values() for item in items) != EXPECTED_STAGE_A_CALLS:
        raise RuntimeError("Stage-A total simulator-call accounting mismatch")
    return phases


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    # Prevent nested numerical libraries from multiplying process-level parallelism.
    # These are operational resource controls; algorithms/seeds/budgets are unchanged.
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    return env


def run_one(
    *,
    root: Path,
    workspace: Path,
    private_dir: Path,
    results_root: Path,
    feature_dir: Path,
    shard: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(root / "scripts/run_confirmatory_stage_a_shard_v0_8_2.py"),
        "--root", str(root),
        "--workspace", str(workspace),
        "--private-dir", str(private_dir),
        "--results-root", str(results_root),
        "--feature-dir", str(feature_dir),
        "--shard-id", str(shard["shard_id"]),
    ]
    if dry_run:
        command.append("--dry-run")
    started = perf_counter()
    result = subprocess.run(
        command,
        cwd=root,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        return {
            "status": "BLOCKED",
            "shard_id": shard["shard_id"],
            "phase": shard["phase"],
            "returncode": result.returncode,
            "detail": detail,
            "wall_clock_s": perf_counter() - started,
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": result.stdout.strip()}
    return {
        "status": "PASS",
        "shard_id": shard["shard_id"],
        "phase": shard["phase"],
        "payload": payload,
        "wall_clock_s": perf_counter() - started,
    }


def run_phase(
    *,
    phase: str,
    shards: list[dict[str, Any]],
    workers: int,
    root: Path,
    workspace: Path,
    private_dir: Path,
    results_root: Path,
    feature_dir: Path,
    dry_run: bool,
) -> list[dict[str, Any]]:
    if workers <= 0:
        raise ValueError("worker count must be positive")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=phase) as pool:
        futures = {
            pool.submit(
                run_one,
                root=root,
                workspace=workspace,
                private_dir=private_dir,
                results_root=results_root,
                feature_dir=feature_dir,
                shard=shard,
                dry_run=dry_run,
            ): shard
            for shard in shards
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = result["status"]
            shard_id = result["shard_id"]
            print(f"[{phase}] {shard_id}: {status}", flush=True)
    results.sort(key=lambda item: item["shard_id"])
    blocked = [item for item in results if item["status"] != "PASS"]
    if blocked:
        examples = "; ".join(
            f"{item['shard_id']}: {item.get('detail', 'blocked')}" for item in blocked[:3]
        )
        raise RuntimeError(
            f"Stage-A phase {phase} has {len(blocked)} blocked shard(s); no later phase started. "
            + examples
        )
    return results


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=script_root)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--private-dir", type=Path, default=None)
    parser.add_argument("--results-root", type=Path, default=None)
    parser.add_argument("--feature-dir", type=Path, default=None)
    parser.add_argument("--feature-workers", type=int, default=4)
    parser.add_argument("--nonpolicy-workers", type=int, default=4)
    parser.add_argument("--learned-workers", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--execute-selection",
        action="store_true",
        help="Required for real Stage-A simulation. Omit for dry-run only.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    base = root / "results/local/confirmatory_v0.8.2"
    workspace = (args.workspace or base / "execution_workspace").resolve()
    private_dir = (args.private_dir or root / "data/private/esm/stage-a-v0.8.2").resolve()
    results_root = (args.results_root or base / "stage_a/shards").resolve()
    feature_dir = (args.feature_dir or base / "stage_a/features").resolve()
    dry_run = bool(args.dry_run or not args.execute_selection)
    phases = selection_shards(workspace)
    started = perf_counter()
    summary = {
        "schema": "confirmatory-stage-a-orchestration-v1",
        "mode": "dry-run" if dry_run else "execute-selection",
        "confirmatory_execution": False,
        "confirmatory_hydration": False,
        "expected_stage_a_shards": EXPECTED_STAGE_A_SHARDS,
        "expected_stage_a_calls": EXPECTED_STAGE_A_CALLS,
        "phase_results": {},
    }
    workers = {
        "tier1_feature_precompute": args.feature_workers,
        "tier1_train_validate_nonpolicy": args.nonpolicy_workers,
        "tier1_train_validate_learned": args.learned_workers,
    }
    try:
        for phase in PHASE_ORDER:
            phase_results = run_phase(
                phase=phase,
                shards=phases[phase],
                workers=workers[phase],
                root=root,
                workspace=workspace,
                private_dir=private_dir,
                results_root=results_root,
                feature_dir=feature_dir,
                dry_run=dry_run,
            )
            summary["phase_results"][phase] = {
                "shards": len(phase_results),
                "status": "PASS",
            }
        summary["status"] = "PASS"
        summary["wall_clock_s"] = perf_counter() - started
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        summary["status"] = "BLOCKED"
        summary["wall_clock_s"] = perf_counter() - started
        summary["error"] = str(exc)
        print(json.dumps(summary, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
