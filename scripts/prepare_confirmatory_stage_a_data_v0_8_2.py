#!/usr/bin/env python3
"""Hydrate only frozen training+validation ESM records for v0.8.2 Stage A.

This wrapper executes exact reviewed hydrator bytes from Git and refuses pilot or confirmatory
waveform material in its dedicated private directory. It never runs a structural simulation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

EXPECTED_MANIFEST_SHA256 = "0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b"
EXPECTED_HYDRATOR_GIT_BLOB = "59b736215be4c12be8f059cce24571ce1753af79"
HYDRATOR_RELATIVE = "scripts/hydrate_frozen_esm_manifest_v0_8_2.py"
ALLOWED_PARTITIONS = ("training", "validation")
EXPECTED_COUNTS = {"training": 52, "validation": 20}
FORBIDDEN_PARTITIONS = ("pilot", "confirmatory")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_text(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(detail)
    return result.stdout.strip()


def validate_hydrator_source(root: Path) -> None:
    committed = _git_text(root, "rev-parse", f"HEAD:{HYDRATOR_RELATIVE}")
    working = _git_text(root, "hash-object", HYDRATOR_RELATIVE)
    if committed != EXPECTED_HYDRATOR_GIT_BLOB or working != EXPECTED_HYDRATOR_GIT_BLOB:
        raise RuntimeError(
            "Stage-A hydration requires exact reviewed hydrator blob "
            f"{EXPECTED_HYDRATOR_GIT_BLOB}; committed={committed}, working={working}"
        )


def manifest_rows(manifest: Path) -> list[dict[str, str]]:
    if sha256_path(manifest) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("frozen ground-motion manifest SHA-256 mismatch")
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]
    if len(rows) != 136:
        raise RuntimeError(f"expected 136 frozen records, found {len(rows)}")
    counts = {partition: 0 for partition in (*ALLOWED_PARTITIONS, *FORBIDDEN_PARTITIONS)}
    for row in rows:
        partition = row.get("partition", "")
        if partition not in counts:
            raise RuntimeError(f"unexpected partition {partition!r}")
        counts[partition] += 1
        digest = row.get("processed_sha256", "").lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise RuntimeError(f"invalid processed SHA-256 for {row.get('record_id', '')!r}")
    if counts != {"training": 52, "validation": 20, "pilot": 16, "confirmatory": 48}:
        raise RuntimeError(f"frozen partition counts mismatch: {counts}")
    return rows


def partition_hashes(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {partition: set() for partition in (*ALLOWED_PARTITIONS, *FORBIDDEN_PARTITIONS)}
    for row in rows:
        result[row["partition"]].add(row["processed_sha256"].lower())
    return result


def verify_private_stage_a_set(private_dir: Path, rows: list[dict[str, str]], *, require_complete: bool) -> dict:
    hashes = partition_hashes(rows)
    expected = hashes["training"] | hashes["validation"]
    forbidden = hashes["pilot"] | hashes["confirmatory"]
    if not private_dir.exists():
        if require_complete:
            raise RuntimeError(f"Stage-A private directory is missing: {private_dir}")
        return {"present": 0, "expected": len(expected)}
    if not private_dir.is_dir():
        raise RuntimeError("Stage-A private path exists and is not a directory")
    entries = list(private_dir.iterdir())
    unexpected = [entry.name for entry in entries if not entry.is_file() or entry.suffix != ".csv"]
    if unexpected:
        raise RuntimeError("Stage-A private directory contains unexpected entries: " + ", ".join(sorted(unexpected)))
    seen: set[str] = set()
    for path in entries:
        stem = path.stem.lower()
        if stem in forbidden:
            raise RuntimeError(f"forbidden pilot/confirmatory waveform material present in Stage-A directory: {path.name}")
        if stem not in expected:
            raise RuntimeError(f"unrecognized waveform file in Stage-A directory: {path.name}")
        observed = sha256_path(path)
        if observed != stem:
            raise RuntimeError(f"private waveform hash mismatch: {path.name} hashes to {observed}")
        if stem in seen:
            raise RuntimeError(f"duplicate Stage-A processed waveform hash: {stem}")
        seen.add(stem)
    if require_complete and seen != expected:
        missing = expected - seen
        raise RuntimeError(f"Stage-A private set incomplete: {len(missing)} expected records missing")
    return {"present": len(seen), "expected": len(expected)}


def run_reviewed_hydrator(root: Path, manifest: Path, private_dir: Path, audit_out: Path) -> dict:
    validate_hydrator_source(root)
    rows = manifest_rows(manifest)
    verify_private_stage_a_set(private_dir, rows, require_complete=False)
    blob = subprocess.run(
        ["git", "cat-file", "blob", EXPECTED_HYDRATOR_GIT_BLOB],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if blob.returncode:
        raise RuntimeError("cannot read reviewed hydration blob from Git object database")
    audit_out.parent.mkdir(parents=True, exist_ok=True)
    private_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="seismicshield-stage-a-hydrator-") as temp_name:
        script = Path(temp_name) / "hydrate_frozen_esm_manifest_v0_8_2.py"
        script.write_bytes(blob.stdout)
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--manifest",
                str(manifest),
                "--output-dir",
                str(private_dir),
                "--audit-out",
                str(audit_out),
                "--partitions",
                "training",
                "validation",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    if result.returncode:
        detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        raise RuntimeError(f"reviewed Stage-A hydration failed closed:\n{detail}")
    validate_hydrator_source(root)
    if not audit_out.is_file():
        raise RuntimeError("reviewed hydrator returned success without an audit file")
    audit = json.loads(audit_out.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise RuntimeError("reviewed Stage-A hydration audit is not PASS")
    if audit.get("partition_counts") != EXPECTED_COUNTS or int(audit.get("records_verified", -1)) != 72:
        raise RuntimeError(f"Stage-A hydration audit counts mismatch: {audit}")
    verify_private_stage_a_set(private_dir, rows, require_complete=True)
    return audit


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--private-dir", type=Path, default=root / "data/private/esm/stage-a-v0.8.2")
    parser.add_argument(
        "--audit-out",
        type=Path,
        default=root / "results/local/confirmatory_v0.8.2/stage_a_hydration.json",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / "data/manifests/ground_motion_manifest.csv"
    try:
        audit = run_reviewed_hydrator(root, manifest, args.private_dir.resolve(), args.audit_out.resolve())
        print("Stage-A ESM hydration: PASS")
        print(f"Training records: {audit['partition_counts']['training']}")
        print(f"Validation records: {audit['partition_counts']['validation']}")
        print("Pilot records hydrated into Stage-A directory: 0")
        print("Confirmatory records hydrated into Stage-A directory: 0")
        return 0
    except Exception as exc:
        print(f"Stage-A ESM hydration: BLOCKED\n- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
