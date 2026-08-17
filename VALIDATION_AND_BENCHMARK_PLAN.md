# Validation and confirmatory benchmark plan

## Validation before optimization claims

The project must establish three kinds of validity before presenting RL results as engineering evidence.

### 1. Numerical validity

- time-step convergence;
- integration-algorithm sensitivity;
- tolerances and convergence-test sensitivity;
- deterministic replay where technically expected;
- recorder/unit/sign audits.

### 2. Structural-model validity

- modal properties;
- canonical free response;
- reference base-excitation response;
- damper hysteresis and energy dissipation;
- comparison with a public benchmark or independently derived case where available.

### 3. Decision-system validity

- identical feasibility constraints across optimizers;
- equal-budget accounting;
- action projection audited rather than hidden;
- every failed simulation retained in a failure ledger;
- train/validation/test leakage tests.

## Confirmatory claim requirements

No primary statement may enter the abstract, README headline or preprint conclusions unless all are true:

1. preregistration DOI exists;
2. confirmatory gate passes;
3. Tier-2 reference simulator validation has passed;
4. test manifest was frozen before outcome inspection;
5. required baselines completed equal-budget runs;
6. primary statistics were produced by frozen scripts;
7. evidence ledger contains artifact paths and checksums;
8. limitations and failure rates are reported.

## Stronger-than-prior-work dimensions

The intended contribution is not "another PPO controller." The benchmark is designed to exceed narrow case-study evidence along several independent dimensions:

- multi-building scale rather than one small case study;
- co-design of count, placement and force parameters;
- MARL vs single-agent and evolutionary baselines;
- real-record event-held-out evaluation;
- explicit OOD building/earthquake transfer;
- multi-objective Pareto evaluation instead of one reward scalar;
- uncertainty and tail-risk analysis;
- simulator-fidelity audit;
- failure/non-convergence accounting;
- open interactive simulator and REST interface;
- preregistered confirmatory analysis;
- frozen DOI-linked evidence package.

Claims of superiority over any particular published work must be limited to dimensions that are actually measured and supported by the final evidence.
