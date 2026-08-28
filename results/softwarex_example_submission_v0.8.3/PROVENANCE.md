# SoftwareX illustrative-example freeze provenance

This directory freezes the clean-environment execution used to validate the public illustrative example for the SoftwareX submission package.

## Execution identity

- Workflow: `SoftwareX Submission Example`
- GitHub Actions run: `33172848644`
- Job: `freeze-example` (`98853998323`)
- Checkout commit: `f60c418652af29ce57a4919d9da1d50af10bf45d`
- Runner OS: Ubuntu 24.04.4 LTS (`ubuntu-24.04` image `20260823.283.1`)
- Python: CPython 3.12.14
- Installed project version: `seismicshield-rl 0.8.3`
- Run status: success
- Evidence status: `software-validation-only`
- Confirmatory data used: `false`
- Paper-level efficacy claim: `false`
- All example methods converged: `true`

The v0.8.3 SoftwareX release is archived at DOI `10.5281/zenodo.22144346` and tag `v0.8.3-softwarex`. The clean run occurred after publication-support metadata synchronization; the scientific files used by this example are byte-identical to the release tag for the example runner (`scripts/run_softwarex_example.py`, blob `40d6a063804f0c276969929cf9275415c49d457e`), smoke configuration (`configs/experiments/smoke.yaml`, blob `38ff372338cbcd413cbe04645d4bb061daba2c85`), benchmark runner (`src/seismicshield_rl/benchmark.py`, blob `e01c337ee63c00d2a615a7afdc56e88db5831618`), and synthetic fixture (`data/fixtures/synthetic_pulse.csv`, blob `fc9fc0bacebbdf349f1e2d6b8685a4b47dc9ba7d`).

## Frozen SHA-256 hashes

- `benchmark.csv`: `69327816136fbf707171c5c11ee2609d8b54c920d53b0790c0c75a9eb10ffa44`
- `benchmark.json`: `d088a52d529ee6c6e364bda4d670f5e54b0d82322fcda8f20dffbd375c192b09`
- `manifest.json`: `94c4fd5d2babfd987b5b575950feb4d894aa1f4410efc50ef56ba9ecaf571b22`
- `audit_summary.json`: `866d7c2a7a1af81b04c2a110ef8d2efb63b404181389f145b71cd072d11d550d`
- GitHub Actions uploaded artifact ZIP: `db0efa4751cfa81f71bbb9f85190f042b9e1715694fe3ab03e5e08bdfc994696`

## Input hashes recorded by the example

- `configs/experiments/smoke.yaml`: `b9aa12fbc90bac769be104e5dc022e39eb7726ef135493a1b085337884dffe12`
- `data/fixtures/synthetic_pulse.csv`: `8017e381fb38d11cf17c0cfb403ae7909a6ff07df3a1f919e962709f04d2e956`

These artifacts validate installation, deterministic synthetic execution, hashing, convergence reporting, and the evidence boundary only. They do not use the frozen confirmatory earthquake partition and are not seismic-efficacy evidence.
