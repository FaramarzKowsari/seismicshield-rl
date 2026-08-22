"""Fail-closed gate for the public OSF-registered confirmatory execution contract."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path
import sys

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_ground_motion_manifest_v0_8_1 import validate as validate_ground  # noqa: E402
from scripts.validate_structural_world_manifest_v0_8_1 import validate as validate_structural  # noqa: E402

EXPECTED_OSF_PERSISTENT_IDS = {
    "64dtx",
    "10.17605/OSF.IO/64DTX",
    "https://doi.org/10.17605/OSF.IO/64DTX",
    "https://osf.io/64dtx/",
}
EXPECTED_SEED_LEDGER = {
    "algorithm_seeds": [1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861],
    "structural_latin_hypercube_seed": 24681357,
    "bootstrap_repetitions": 20000,
    "bootstrap_random_seed": 998035145,
    "manifest_algorithm": "SHA-256",
    "manifest_salt": "SeismicShield-RL-v0.8.0-OSF-2026",
}


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value.lower()
    )


def _git_blob_sha256(root: Path, relative: str) -> str | None:
    """Return SHA-256 of the exact bytes stored at HEAD for a tracked path.

    Git may present CRLF bytes in a Windows working tree even when the immutable blob is LF.
    Integrity checks therefore accept the frozen Git blob digest for tracked contracts while
    still using exact working-tree bytes for generated/untracked manifests.
    """
    relative = relative.replace("\\", "/")
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def digest_matches(root: Path, relative: str, expected: str) -> bool:
    """Match either exact working-tree bytes or the canonical tracked Git blob bytes."""
    path = root / relative
    if not path.is_file() or not _is_sha256(expected):
        return False
    working = hashlib.sha256(path.read_bytes()).hexdigest()
    if working == expected.lower():
        return True
    tracked = _git_blob_sha256(root, relative)
    return tracked == expected.lower()


def _digest_ok(root: Path, relative: object, expected: object, label: str, reasons: list[str]) -> None:
    if not isinstance(relative, str) or not relative:
        reasons.append(f"{label} path is not recorded.")
        return
    path = root / relative
    if not path.is_file():
        reasons.append(f"{label} does not exist: {relative}.")
        return
    if not isinstance(expected, str) or not digest_matches(root, relative, expected):
        reasons.append(f"{label} SHA-256 is absent or does not match.")


def validate_seed_ledger(path: Path) -> list[str]:
    """Verify the exact preregistered seed namespaces, values, and selection inputs."""
    try:
        ledger = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [f"Seed ledger cannot be read: {exc}"]
    if not isinstance(ledger, dict):
        return ["Seed ledger must be a YAML mapping."]
    bootstrap = ledger.get("bootstrap_resampling")
    manifest = ledger.get("manifest_deterministic_selection")
    bootstrap = bootstrap if isinstance(bootstrap, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    observed = {
        "algorithm_seeds": ledger.get("algorithm_seeds"),
        "structural_latin_hypercube_seed": ledger.get("structural_latin_hypercube_seed"),
        "bootstrap_repetitions": bootstrap.get("repetitions"),
        "bootstrap_random_seed": bootstrap.get("random_seed"),
        "manifest_algorithm": manifest.get("algorithm"),
        "manifest_salt": manifest.get("salt"),
    }
    return [
        f"Seed ledger {key} mismatch: expected {expected!r}, found {observed[key]!r}."
        for key, expected in EXPECTED_SEED_LEDGER.items()
        if observed[key] != expected
    ]


def validate_source_tag(root: Path, tag: object) -> tuple[str | None, str | None]:
    """Resolve the frozen tag to a commit and require that exact commit to be HEAD."""
    if not isinstance(tag, str) or not tag:
        return None, "Source Git tag is absent from the gate configuration."
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if resolved.returncode:
        return None, f"Required source Git tag {tag!r} does not exist."
    sha = resolved.stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if head.returncode or head.stdout.strip() != sha:
        return sha, f"Source Git tag {tag!r} resolves to {sha}, which does not equal HEAD."
    return sha, None


def _require_validation_evidence(data: dict, prefix: str, label: str, reasons: list[str]) -> None:
    workflow = data.get(f"{prefix}_validation_workflow_run")
    evidence_sha = data.get(f"{prefix}_validation_evidence_sha256")
    if not isinstance(workflow, str) or not workflow.startswith("https://github.com/"):
        reasons.append(f"{label} validation workflow run is not recorded.")
    if not _is_sha256(evidence_sha):
        reasons.append(f"{label} validation evidence SHA-256 is not recorded.")


def check_gate(root: Path, gate_path: Path) -> tuple[bool, list[str]]:
    try:
        data = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return False, [f"Cannot read gate configuration: {exc}"]
    reasons: list[str] = []
    if data.get("osf_registration_status") != "public":
        reasons.append("OSF registration status is not public.")
    persistent_id = data.get("osf_registration_persistent_id")
    if not isinstance(persistent_id, str) or persistent_id.strip() not in EXPECTED_OSF_PERSISTENT_IDS:
        reasons.append(
            "Public OSF registration identifier does not match preregistration 64dtx / DOI 10.17605/OSF.IO/64DTX."
        )

    manifest = data.get("ground_motion_manifest")
    if not isinstance(manifest, str) or not (root / manifest).is_file():
        reasons.append("A frozen real ground-motion manifest is absent.")
    else:
        manifest_errors = validate_ground(root / manifest)
        reasons.extend(f"Ground-motion manifest: {error}" for error in manifest_errors)
        _digest_ok(
            root,
            manifest,
            data.get("ground_motion_manifest_sha256"),
            "Ground-motion manifest",
            reasons,
        )

    structural = data.get("structural_world_manifest")
    if not isinstance(structural, str) or not (root / structural).is_file():
        reasons.append("A frozen structural-world manifest is absent.")
    else:
        structural_errors = validate_structural(root / structural)
        reasons.extend(f"Structural-world manifest: {error}" for error in structural_errors)
        _digest_ok(
            root,
            structural,
            data.get("structural_world_manifest_sha256"),
            "Structural-world manifest",
            reasons,
        )
    if data.get("structural_world_manifest_validated") is not True:
        reasons.append("Structural-world manifest is not validated.")

    structural_contract = data.get("structural_world_contract")
    if not isinstance(structural_contract, str) or not (root / structural_contract).is_file():
        reasons.append("Structural-world implementation freeze is absent.")

    seed_ledger = data.get("seed_ledger")
    if not isinstance(seed_ledger, str) or not (root / seed_ledger).is_file():
        reasons.append("Seed ledger is absent.")
    else:
        reasons.extend(validate_seed_ledger(root / seed_ledger))
    _digest_ok(
        root,
        data.get("frozen_numerical_config"),
        data.get("config_sha256"),
        "Frozen numerical config",
        reasons,
    )

    algorithm_bundle = data.get("confirmatory_algorithm_bundle")
    _digest_ok(
        root,
        algorithm_bundle,
        data.get("confirmatory_algorithm_bundle_sha256"),
        "Confirmatory algorithm bundle",
        reasons,
    )
    if data.get("confirmatory_algorithm_bundle_validated") is not True:
        reasons.append("Confirmatory algorithm bundle is not validated/frozen.")
    else:
        _require_validation_evidence(
            data, "confirmatory_algorithm_bundle", "Confirmatory algorithm bundle", reasons
        )

    _, source_error = validate_source_tag(root, data.get("source_git_tag"))
    if source_error:
        reasons.append(source_error)

    if data.get("tier_2_backend_validated") is not True:
        reasons.append("Tier-2 backend is not validated.")
    else:
        _require_validation_evidence(data, "tier_2", "Tier-2", reasons)

    if data.get("confirmatory_runs_allowed") is not True:
        reasons.append("confirmatory_runs_allowed is false.")
    return not reasons, reasons


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate",
        type=Path,
        default=root / "open_science/confirmatory_gate_v0.8.0.yaml",
    )
    args = parser.parse_args()
    ok, reasons = check_gate(root, args.gate)
    print(f"Confirmatory gate: {'PASS' if ok else 'BLOCKED'}")
    try:
        gate_data = yaml.safe_load(args.gate.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        gate_data = {}
    resolved_sha, _ = validate_source_tag(root, gate_data.get("source_git_tag"))
    if resolved_sha:
        print(f"Source Git tag resolved SHA: {resolved_sha}")
    for reason in reasons:
        print(f"- {reason}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
