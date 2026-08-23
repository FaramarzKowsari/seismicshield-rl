<p align="center">
  <img src="https://avatars.githubusercontent.com/u/105053743?v=4&s=512" width="142" height="142" alt="Faramarz Kowsari">
</p>

<h1 align="center">SeismicShield-RL</h1>
<p align="center"><strong>Preregistered, reproducible infrastructure for benchmarking reinforcement learning and multi-objective optimization in seismic friction-damper co-design</strong></p>
<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-Final%20Infrastructure%20Release-168D73.svg">
  <img alt="Scientific study" src="https://img.shields.io/badge/full%20confirmatory%20run-deferred-B7791F.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-3670A0.svg">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-168D73.svg">
</p>

## Final project status

**SeismicShield-RL v0.8.2 is closed as a Final Infrastructure Release.** The software, preregistration, immutable scientific source, data-provenance checks, runtime preflight, deterministic execution planning, and selection-only workspace safeguards have been completed and preserved. The resource-intensive full Stage-A training/selection campaign and the subsequent confirmatory Tier-2 campaign were **not executed**.

This is an intentional, transparent stopping point based on measured computational requirements, not a positive or negative seismic-performance result.

> **No paper-level confirmatory performance result has been generated or inspected. No claim is made that MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search is superior on the preregistered confirmatory benchmark.**

The preregistered protocol remains preserved at OSF DOI [`10.17605/OSF.IO/64DTX`](https://doi.org/10.17605/OSF.IO/64DTX). The immutable scientific source remains Git tag `confirmatory-v0.8.2-final` at commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`.

## What was completed

The final infrastructure release includes:

- a frozen preregistered confirmatory protocol;
- an immutable scientific source tag and fail-closed gate;
- an explicit-CC ESM manifest containing 136 records from 34 events;
- frozen training, validation, pilot, and confirmatory partitions;
- a frozen 16-state structural-world design;
- fixed objective definitions, algorithm identities, budgets, seeds, checkpoint rules, and statistical analysis rules;
- deterministic Tier-1 and OpenSeesPy Tier-2 structural backends;
- validation-safe information boundaries that prevent confirmatory leakage into model selection;
- independent runtime preflight evidence verifying all 136 processed waveform hashes;
- successful pilot runtime convergence for four Tier-1 and four Tier-2 fixtures;
- a deterministic execution planner containing 475 atomic shards;
- a selection-only execution workspace that keeps all 51 confirmatory Tier-2 shards locked;
- audit/evidence infrastructure, SHA-256 provenance, CI, tests, and reproducibility contracts.

## What was deliberately not completed

The following work was deferred because the measured compute requirement exceeded the intended no-cost execution envelope:

- Stage-A full-scale training and validation selection;
- generation and freezing of the 768 final selected designs;
- confirmatory waveform hydration for scientific response evaluation;
- the 39,168 Tier-2 confirmatory structural-response calls;
- final event-level inferential analysis and algorithm-ranking claims.

The stopping decision preserves the confirmatory boundary: no confirmatory structural-response outcome was used for training, tuning, checkpoint selection, or retrospective protocol modification.

## Measured computational boundary

The frozen execution plan contains:

| Stage | Atomic shards | Structural-response calls | Measured/projected sequential runtime |
|---|---:|---:|---:|
| Tier-1 feature precompute | 16 | 832 | included below |
| Tier-1 non-policy train + validation | 384 | 1,474,560 | included below |
| Tier-1 learned train + validation | 24 | 1,305,600 | included below |
| **Stage A Tier-1 total** | **424** | **2,780,992** | **~1,026.68 h** |
| Tier-2 confirmatory seeded | 48 | 36,864 | included below |
| Tier-2 support | 3 | 2,304 | included below |
| **Tier-2 total** | **51** | **39,168** | **~21.64 h** |
| **Grand total** | **475** | **2,820,160** | — |

The runtime preflight measured approximately **1.329 s per Tier-1 call** and **1.989 s per Tier-2 call** on the tested environment. A learned Stage-A shard contains 54,400 Tier-1 calls and is intentionally atomic under the frozen scientific implementation; splitting it merely to fit a hosted-CI wall-clock limit would change the registered execution semantics.

The preserved runtime evidence is available at [`results/validation/confirmatory_runtime_preflight_v0.8.2.json`](results/validation/confirmatory_runtime_preflight_v0.8.2.json).

## Research question retained by the preregistration

The deferred confirmatory study asks whether multi-agent reinforcement learning can jointly optimize the number, inter-story distribution, and slip-force parameters of friction dampers while producing a better out-of-sample Pareto trade-off among retrofit cost, maximum inter-story drift ratio (MIDR), and peak floor acceleration (PFA) than transparent heuristic, evolutionary, and single-agent RL baselines under unseen earthquake records and structural uncertainty.

The infrastructure release **does not answer that question**. It preserves a reproducible and auditable way to answer it if suitable compute becomes available in the future.

## Benchmark design

### Structural states

The frozen benchmark spans four building heights — 3, 6, 10, and 20 stories — with a nominal state and three structural perturbations for each height, producing **16 structural states**.

### Design variables

For each story, the optimization policy selects:

- damper count: 0 to 4;
- slip-force level: 0, 50,000, 100,000, 200,000, or 350,000 N.

### Primary objectives

The registered multi-objective problem evaluates:

- retrofit cost proxy;
- maximum inter-story drift ratio (MIDR);
- peak floor acceleration (PFA).

### Algorithm ladder

The frozen confirmatory implementations include:

1. random search;
2. scalar genetic algorithm;
3. NSGA-II;
4. PPO;
5. IPPO;
6. MAPPO.

Additional transparent baseline components remain in the research platform, but no confirmatory ranking is reported in this release.

## Data partitions

The ESM manifest contains 136 records:

| Partition | Records |
|---|---:|
| Training | 52 |
| Validation | 20 |
| Pilot | 16 |
| Confirmatory | 48 |
| **Total** | **136** |

The runtime preflight independently reproduced the frozen processed-waveform SHA-256 values for all 136 records. Waveform bytes are not redistributed by the repository.

## Reproducibility and leakage controls

Scientific execution is bound to the immutable source tag `confirmatory-v0.8.2-final`. Post-freeze orchestration may move, verify, or hash-check data, but it cannot silently replace scientific code or contracts.

The selection-only workspace created by [`scripts/prepare_confirmatory_workspace_v0_8_2.py`](scripts/prepare_confirmatory_workspace_v0_8_2.py) exposes 424 Stage-A selection shards as planned while keeping all 51 Tier-2 confirmatory shards locked. Confirmatory hydration and confirmatory execution remain disabled at this release boundary.

Relevant frozen documents include:

- [`open_science/confirmatory_execution_v0.8.2.yaml`](open_science/confirmatory_execution_v0.8.2.yaml)
- [`open_science/confirmatory_analysis_v0.8.2.yaml`](open_science/confirmatory_analysis_v0.8.2.yaml)
- [`open_science/CONFIRMATORY_EXECUTION_OPERATIONS_v0.8.2.md`](open_science/CONFIRMATORY_EXECUTION_OPERATIONS_v0.8.2.md)
- [`SIMULATOR_STACK.md`](SIMULATOR_STACK.md)
- [`paper/EVIDENCE_LEDGER.csv`](paper/EVIDENCE_LEDGER.csv)

## Technical report

The closure rationale, completed evidence, limitations, reproducibility status, and deferred-study boundary are documented in:

[`paper/TECHNICAL_REPORT_FINAL_INFRASTRUCTURE_RELEASE.md`](paper/TECHNICAL_REPORT_FINAL_INFRASTRUCTURE_RELEASE.md)

## Repository map

```text
configs/                    Building and experiment contracts
data/                       Data policy + synthetic test fixture
docs/                       Research demonstrator documentation
open_science/               Frozen preregistration/execution/analysis contracts
paper/                      Evidence ledger + final infrastructure technical report
results/validation/         Preserved preflight evidence
scripts/                    Reproducible checks and execution-planning utilities
src/seismicshield_rl/       Research software package
tests/                      Unit and contract tests
.github/workflows/          CI and release automation
```

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,api]"
pytest -q
python scripts/run_smoke_benchmark.py
uvicorn seismicshield_rl.api.app:app --reload
```

Optional stacks:

```bash
pip install -e ".[marl]"
pip install -e ".[opensees]"
```

OpenSeesPy remains an optional research backend. The project does not certify a real building or replace professional structural-engineering analysis.

## Evidence policy

A seismic-performance statement is admissible only when supported by the frozen experiment configuration, source commit, preserved raw/derived artifacts, deterministic seed ledger, SHA-256 checksums, statistical-analysis record, and a verified evidence-ledger entry.

Accordingly, the blocked efficacy claims in `paper/EVIDENCE_LEDGER.csv` remain blocked in this Final Infrastructure Release.

## How to cite

For the preregistered protocol, cite OSF DOI [`10.17605/OSF.IO/64DTX`](https://doi.org/10.17605/OSF.IO/64DTX).

For the software/infrastructure release, use `CITATION.cff` and the GitHub/Zenodo release metadata when the release DOI is available. The OSF DOI identifies the preregistration and must not be represented as the software DOI.

## Scope and safety

SeismicShield-RL is a research and reproducibility platform. It does not certify a building, prescribe retrofit construction, predict an earthquake, replace a structural engineer, or provide code-compliance approval. Pilot convergence and software validation establish infrastructure readiness only; they do not establish real-world seismic efficacy.

## Author

**Faramarz Kowsari** — author, Software Engineer and AI researcher based in Istanbul.

- ORCID: https://orcid.org/0000-0003-1692-0453
- GitHub: https://github.com/FaramarzKowsari
- Project: https://github.com/FaramarzKowsari/seismicshield-rl

## License

Project code is MIT licensed. Third-party engines and datasets retain their own licenses and terms. ESM waveform redistribution is not performed by repository artifacts.
