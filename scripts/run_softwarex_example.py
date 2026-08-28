from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from seismicshield_rl import __version__
from seismicshield_rl.benchmark import run_benchmark


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "smoke.yaml"
DEFAULT_OUTPUT = ROOT / "results" / "softwarex_example"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_example(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    """Run the public, synthetic, software-validation-only example used by the SoftwareX paper.

    This example never reads the frozen confirmatory earthquake partition and must not be
    interpreted as seismic-efficacy evidence.
    """
    output_dir = output_dir.resolve()
    rows = run_benchmark(DEFAULT_CONFIG, output_dir)

    summary = {
        "example": "softwarex-public-synthetic-validation",
        "seismicshield_rl_version": __version__,
        "status": "software-validation-only",
        "confirmatory_data_used": False,
        "paper_level_efficacy_claim": False,
        "config": str(DEFAULT_CONFIG.relative_to(ROOT)),
        "config_sha256": sha256(DEFAULT_CONFIG),
        "synthetic_fixture": "data/fixtures/synthetic_pulse.csv",
        "synthetic_fixture_sha256": sha256(ROOT / "data" / "fixtures" / "synthetic_pulse.csv"),
        "methods": [row["method"] for row in rows],
        "all_converged": all(bool(row["converged"]) for row in rows),
        "artifacts": {
            name: sha256(output_dir / name)
            for name in ("benchmark.csv", "benchmark.json", "manifest.json")
        },
    }
    (output_dir / "audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the public synthetic validation example accompanying the SoftwareX manuscript."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Directory for generated validation artifacts.",
    )
    args = parser.parse_args()
    summary = run_example(args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
