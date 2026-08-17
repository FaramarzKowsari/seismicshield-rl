# Roadmap and stage gates

> Confirmatory science is blocked until the public OSF preregistration DOI is recorded and `scripts/check_preregistration_gate.py` passes.

## v0.1 — Research foundation (this package)

- research contract
- deterministic surrogate
- metrics/cost model
- transparent baselines
- single-agent + parallel multi-agent environment contracts
- smoke benchmark
- REST API, Docker, CI and Pages scaffold
- evidence ledger

**Exit gate:** all core tests pass; smoke benchmark is deterministic; no performance claim is made.

## v0.1.1 — Open-science/preregistration foundation

- OSF Simulation Studies preregistration draft
- explicit prior-pilot disclosure
- preregistration software gate
- DOI relationship graph
- multi-fidelity simulator plan
- expanded benchmark specification
- engrXiv release checklist

**Exit gate:** public OSF preregistration DOI recorded; confirmatory execution remains blocked until simulator/data protocol fields are fully frozen.

## v0.2 — OpenSees parity

- implement N-story OpenSees model generator
- add friction-damper representation with documented modeling assumptions
- compare undamped and damped canonical cases against surrogate
- regression tests for recorder parsing and solver failures
- containerized Python 3.12 OpenSees workflow

**Exit gate:** parity tolerances and solver-failure policy are frozen and passed.

## v0.3 — Benchmark baseline release

- curate train/validation/test ground-motion manifests
- AFAD/TADAS acquisition adapter and provenance cache
- optional user-supplied PEER/NGA adapter without making restricted downloads a mandatory dependency
- NSGA-II baseline
- single-agent PPO
- IPPO and MAPPO implementations
- compute-budget accounting

**Exit gate:** all methods can reproduce one small equal-budget benchmark from a clean checkout.

## v0.4 — Scale and generalization

- 3-, 6-, 10- and 20-story task families
- structural domain randomization
- building-height transfer
- unseen-earthquake evaluation
- parallel evaluation workers and result cache

## v0.5 — Multi-objective and risk-sensitive study

- Pareto policies / weight-conditioned policies
- hypervolume reporting
- CVaR objective variants
- constrained design policies

## v0.6 — Ablation and error analysis

- critic/parameter-sharing/reward/observation ablations
- invalid-design and solver-failure taxonomy
- sensitivity to discretization and reward scaling

## v0.7 — Interactive research simulator

- scenario explorer
- design comparison plots
- response time histories
- Pareto explorer
- downloadable run manifest
- clear exploratory/verified evidence labels

## v0.8 — Confirmatory freeze

- preregistration DOI already public before this stage
- preregistered/frozen hypotheses and primary contrasts
- locked test manifests
- source commit + environment lock
- confirmatory GitHub Actions/manual compute artifacts
- SHA-256 manifests

## v0.9 — Technical paper

- final tables/figures generated from frozen artifacts only
- methods, ablations, uncertainty and limitations
- reproducibility appendix

## v1.0 — Citable research release

- tagged source release
- Zenodo version DOI + concept DOI
- archival evidence bundle
- OSF record/registration as appropriate
- preprint submission
- final GitHub Pages research presentation
