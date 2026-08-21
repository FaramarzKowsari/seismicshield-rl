# SeismicShield-RL — OSF Preregistration Draft

## Intended OSF registration type

**Simulation Studies** registration template (ADEMP-aligned), submitted publicly before any confirmatory benchmark is executed.

## Proposed registration title

**SeismicShield-RL: Preregistered Multi-Fidelity Benchmark of Multi-Agent Reinforcement Learning for Friction-Damper Co-Design Under Earthquake Uncertainty**

## Registration status and prior work disclosure

This preregistration governs the **confirmatory research phase** of SeismicShield-RL. Before preregistration, the project completed software scaffolding, deterministic synthetic fixtures, interface tests, a small smoke benchmark using a simplified research surrogate, and source-side ground-motion discovery/audit/freeze work that did not inspect confirmatory performance outcomes. Those activities are exploratory software validation and preregistration infrastructure only. They are not confirmatory evidence and will not be used to select, accept, or reject the preregistered primary hypotheses.

The final pre-registration source-side amendment is v0.8.1. It preserves the pre-existing v0.8.0 salted event and record ordering while applying an explicit per-waveform license rule. The completed 63-event ESM queue contains 34 events with at least four eligible source-reported Creative Commons records. The source-side sample is therefore frozen at **34 events × 4 records = 136 records** before OSF submission. No confirmatory simulation outcome was inspected before this amendment.

The following must occur **after** the public OSF registration and DOI are issued:

1. freezing the confirmatory ground-motion test manifest and event-to-partition identities under the preregistered rules;
2. running the preregistered high-fidelity confirmatory benchmark;
3. computing the preregistered primary inferential statistics;
4. changing primary claim IDs in the evidence ledger from `blocked` to `verified` only when the evidence contract is satisfied.

## A — Aims

### Primary research question

Under equal simulation and optimization budgets, does a story-decomposed multi-agent reinforcement-learning co-design policy improve the held-out cost–drift–acceleration trade-off for friction-damper retrofit design compared with strong transparent, evolutionary, and single-agent learning baselines?

### Primary hypotheses

**H1 — Pareto performance.** On preregistered held-out earthquake worlds, the primary MARL method will achieve higher Pareto hypervolume than single-agent PPO and NSGA-II under equal-budget evaluation.

**H2 — Structural-response trade-off.** At prespecified normalized retrofit-cost slices, the primary MARL method will reduce median maximum inter-story drift ratio (MIDR) without a compensating deterioration in peak floor acceleration (PFA) large enough to dominate the same Pareto region.

**H3 — Out-of-distribution generalization.** The relative Pareto advantage, if present in-distribution, will be evaluated under unseen earthquake events, structural-parameter perturbations, and building-height transfer. OOD performance is a prespecified robustness estimand, not a post-hoc showcase.

**H4 — Multi-agent contribution.** MAPPO with centralized training/decentralized execution will outperform a parameter-matched decentralized IPPO ablation on at least one prespecified primary performance measure without receiving a larger simulator-evaluation budget.

### Secondary questions

- How much performance is attributable to centralized critic information versus parameter sharing?
- What is the value of explicit cost and PFA objectives in the reward/conditioning design?
- Does risk-sensitive training improve CVaR tail response at an acceptable mean-performance cost?
- How does simulator fidelity affect optimizer ranking?
- How sensitive are conclusions to damper force discretization, structural uncertainty and solver failures?

## D — Data-generating mechanism and study worlds

### Ground motions

The benchmark will use versioned, provenance-preserving strong-motion records from the **European Strong-Motion Database (ESM)**. Record identity, source request references, raw/source hashes, preprocessing steps, unit conversions and derived hashes are preserved in deterministic local artifacts and public lock metadata. Raw/source waveform bytes are not assumed redistributable.

For the confirmatory preregistration, a waveform is source-license eligible only when its source-reported `DATA_LICENSE` begins with `CC-BY3_0-IT` or `CC-BY4_0`. `D (network default license)` and `U (unknown license)` are excluded without reinterpretation, substitution, or network-level license inference. This rule was finalized before OSF registration and before any confirmatory outcome was inspected.

The v0.8.0 salt `SeismicShield-RL-v0.8.0-OSF-2026` and the pre-existing salted event/record order are preserved. The frozen source queue contains 63 physically/component-eligible events. Events are traversed in the pre-existing salted event-hash order and retained only if their exhaustive inventory contains at least four explicit-CC records. The first 34 retained events form the v0.8.1 source-side sample; within each event, the first four explicit-CC records in the pre-existing salted record-hash order are retained. The resulting sample is **34 earthquake events and 136 records**.

The preregistered partition counts are:

- training: **13 events / 52 records**;
- validation: **5 events / 20 records**;
- pilot: **4 events / 16 records**, permanently excluded from confirmatory inference;
- confirmatory: **12 events / 48 records**.

Ground motions are grouped by **earthquake event** before splitting. Records from the same event may not be divided across train, validation, pilot, or confirmatory strata. This prevents event leakage. The actual event-to-partition identities will be frozen under the registered deterministic contract after public OSF registration and before confirmatory execution.

### Building families

The planned benchmark contains four canonical story-count families:

- 3-story
- 6-story
- 10-story
- 20-story

The confirmatory benchmark will include at least two nonlinear structural archetype parameterizations where technically validated. If the second archetype is not validated before the preregistration freeze, the primary confirmatory study will be restricted to one archetype and the second will be labeled exploratory; this contingency must be decided before OSF submission.

### Structural uncertainty

Each earthquake world combines one ground-motion record with a frozen draw of structural parameters. Planned uncertainty dimensions include mass, stiffness, damping, selected material/model parameters and damper-property tolerance. Distributions and bounds must be justified from engineering references or calibration data before the confirmatory manifest is frozen.

### Damper design variables

Primary Task A is offline co-design. For each story, the decision representation contains:

- integer damper count or a bounded discrete allocation variable;
- slip-force/capacity parameter;
- optional device family parameter only if validated before preregistration freeze.

Total count/cost, per-story capacity and feasibility constraints are explicit and identical across algorithms.

### Adaptive control extension

Task B, semi-active adaptive slip-force control through time, is a **secondary extension** and is not mixed with the primary co-design hypothesis unless separately preregistered.

## E — Estimands and targets

### Primary estimand 1: Pareto hypervolume difference

For each held-out benchmark stratum, compute the paired difference in normalized Pareto hypervolume between the primary MARL method and each preregistered comparator. Objective directions are minimization for normalized retrofit cost, MIDR and PFA. Normalization constants and the hypervolume reference point must be frozen before confirmatory evaluation.

### Primary estimand 2: response at cost slices

At prespecified normalized-cost slices, compare paired MIDR and PFA values using identical earthquake worlds. Interpolation rules on Pareto fronts must be frozen before the test manifest is evaluated.

### Primary estimand 3: OOD degradation

Measure the change in Pareto hypervolume and safety-response metrics from in-distribution validation to preregistered OOD test strata. Building-height extrapolation and unseen-event evaluation must be reported separately.

### Secondary estimands

- residual drift, when the structural model supports a meaningful residual state;
- maximum displacement;
- damper energy dissipation;
- maximum damper force and stroke demand;
- CVaR of MIDR/PFA under uncertainty;
- invalid-design rate;
- solver non-convergence rate;
- wall-clock and simulator-call efficiency.

## M — Methods

### Simulator hierarchy

**Tier 0 — deterministic unit-test surrogate.** Used only for interfaces, smoke tests and software validation.

**Tier 1 — calibrated fast nonlinear MDOF simulator.** Used for high-throughput RL training and screening. Its error against Tier 2 is quantified on a frozen calibration/validation design.

**Tier 2 — OpenSeesPy nonlinear reference simulator.** Used for backend validation and all primary confirmatory performance claims.

**Tier 3 — optional detailed frame extension.** Higher-fidelity 2D/3D frame models may be used for external validity. Unless frozen into the preregistration, Tier 3 findings are exploratory.

### Required baselines

All confirmatory comparisons receive the same design constraints and explicit simulator-call budget.

1. no damper;
2. uniform allocation;
3. drift-proportional heuristic;
4. equal-budget random search;
5. genetic/evolutionary baseline;
6. NSGA-II multi-objective optimization;
7. single-agent PPO;
8. decentralized IPPO;
9. primary MAPPO/CTDE method.

Optional additional algorithms such as CMA-ES, Bayesian optimization or SAC may be reported as secondary baselines but cannot replace the required comparator set after preregistration.

### Equal-budget rule

The primary fairness unit is the number of **Tier-2-equivalent structural simulation calls**. Training on a faster simulator must be accounted for using a preregistered conversion/reporting rule and accompanied by raw wall-clock, CPU and GPU metadata. No method receives hidden extra confirmatory evaluations for tuning.

### Hyperparameter selection

All hyperparameter selection, reward shaping, architecture selection and stopping rules use training and validation strata only. Confirmatory test outcomes cannot be inspected until the analysis code, metrics, normalization constants and primary figure/table scripts are frozen.

### Seeds

The primary algorithm-training seed ledger is frozen at eight seeds: `1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861`. Structural-draw seeds, optimization initializations and bootstrap/permutation seeds are preserved in their corresponding frozen manifests. Confirmatory test outcomes may not be used to alter the seed set.

## P — Performance measures and inference

### Primary performance measures

- normalized Pareto hypervolume;
- MIDR at prespecified cost slices;
- PFA at prespecified cost slices;
- OOD hypervolume degradation.

### Confirmatory statistical plan

- paired comparisons on identical earthquake worlds;
- 95% confidence intervals using cluster bootstrap at the earthquake-event/world level as appropriate;
- paired permutation/randomization tests for the frozen primary contrast family;
- family-wise multiplicity control using Holm correction for the primary contrast family;
- raw paired distributions and effect sizes reported alongside p-values;
- bootstrap/permutation seeds preserved in the evidence manifest.

The exact clustering unit will be frozen based on the final record/event hierarchy before OSF submission. No method-specific failed world may be silently omitted.

## Failure, exclusion and convergence rules

A run is never deleted solely because it produces an unfavorable result. Every world receives one of the following statuses:

- valid converged response;
- invalid design before simulation;
- solver non-convergence;
- numerical overflow/NaN;
- hard response/collapse proxy exceeded;
- infrastructure failure unrelated to the algorithm.

Rules for penalization, paired exclusion and rerun of infrastructure failures must be frozen before confirmatory evaluation. Algorithmic or solver failures remain part of method performance.

## Ablation study

Prespecified ablations:

- MAPPO vs IPPO;
- centralized critic on/off;
- parameter sharing on/off;
- local-only vs local+global observation context;
- structural domain randomization on/off;
- cost term on/off;
- PFA term on/off;
- fixed vs learned damper count;
- risk-neutral vs CVaR-conditioned objective.

Ablations are secondary unless explicitly promoted into the primary contrast family before registration.

## Simulator validation

Before confirmatory optimization, Tier 1 and Tier 2 must pass a frozen validation suite covering:

- modal periods/frequencies;
- undamped and damped free response;
- linear base-excitation sanity cases;
- device force–displacement/force–velocity response;
- energy balance checks where applicable;
- recorder units/sign conventions;
- time-step convergence;
- integration algorithm sensitivity;
- known benchmark comparison where a public reference case exists.

Validation tolerances will be frozen before confirmatory results are viewed.

## Confirmatory sample-size/compute feasibility decision

The source-side ground-motion sample is fixed before OSF submission at **34 earthquake events, four records per event, and 136 records total**. The partition counts are fixed at **13 training, 5 validation, 4 pilot, and 12 confirmatory events**. The four pilot events are permanently excluded from confirmatory inference. The reduction from the earlier 40-event target to 34 events is solely the consequence of the explicit per-waveform license eligibility rule applied to the already-frozen 63-event salted ESM queue; it was made before registration and before confirmatory outcomes were inspected.

The v0.8.0 primary compute budgets, structural families, objective definitions, analysis thresholds and eight primary algorithm seeds remain unchanged by the v0.8.1 license amendment. The post-registration manifest freeze may instantiate identities and partitions only under these registered counts and deterministic rules; it may not change the sample size or license policy based on confirmatory performance.

## Deviations

Any deviation from this preregistration will be documented in `open_science/DEVIATIONS.md` with:

- date;
- reason;
- whether test outcomes had been inspected;
- affected hypotheses/estimands;
- whether the changed analysis is confirmatory or exploratory.

## Open-science outputs

The project intends to publish distinct, cross-linked research objects:

1. public OSF preregistration DOI — study protocol;
2. GitHub repository — living development record;
3. Zenodo concept DOI + version DOI — frozen software/evidence release;
4. engrXiv DOI — preprint/manuscript;
5. optional dataset DOI — large benchmark/evidence bundle if separated from the software record.

Each object must declare its relation to the others rather than using one DOI for multiple scholarly objects.