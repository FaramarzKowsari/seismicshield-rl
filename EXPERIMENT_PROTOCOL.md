# Experiment protocol

**Confirmatory execution gate:** phases that inspect frozen high-fidelity test outcomes are prohibited until the public OSF preregistration DOI is recorded in `open_science/preregistration.json`.

## Phase 0 — software validity

Purpose: determinism, interfaces, units, artifact creation. Uses only synthetic fixtures. No seismic-performance claim.

## Phase 1 — backend parity

Matched canonical cases are run in the surrogate and OpenSees:

- free vibration
- undamped base excitation
- viscous-equivalent damping sanity cases
- friction-device canonical response

Parity tolerances are defined before examining the full benchmark.

## Phase 2 — baseline benchmark

Every optimizer receives an explicit budget expressed in simulator evaluations and wall-clock/GPU metadata. Report both final quality and sample efficiency.

Required methods:

- no damper
- uniform allocation
- drift-proportional heuristic
- random search
- NSGA-II
- single-agent PPO
- IPPO
- MAPPO

## Phase 3 — data split

Create immutable manifests for training, validation and confirmatory test records. Record selection criteria and preprocessing are versioned. Test record identities are not used for model or reward selection.

## Phase 4 — scale matrix

At minimum, evaluate separate building families at 3, 6, 10 and 20 stories. Any cross-height transfer experiment distinguishes interpolation from extrapolation.

## Phase 5 — uncertainty matrix

For each held-out earthquake, pair methods on identical structural draws. Preserve the world ID so uncertainty intervals can cluster at the earthquake/world level.

## Primary comparisons

The exact family will be frozen at v0.8. Candidate primary contrasts:

- MAPPO vs single-agent PPO
- MAPPO vs NSGA-II
- MAPPO vs IPPO

for Pareto hypervolume and prespecified safety-related response metrics at comparable cost.

## Statistical outputs

- paired point differences
- earthquake-world bootstrap 95% intervals
- paired permutation/randomization p-values for frozen primary contrasts
- multiplicity adjustment for the primary family
- effect sizes and raw paired distributions

## Error analysis

Always report:

- solver non-convergence count
- invalid/projection count
- NaN/overflow count
- extreme-response worlds
- policy constraint violations
- compute budget actually consumed

No failed world may be silently deleted from one algorithm while retained for another.

## Phase 6 — confirmatory release graph

After confirmatory analysis, freeze the exact code/evidence as a GitHub release and archive it in Zenodo. The preprint must cite both the preregistration DOI and exact Zenodo version DOI.
