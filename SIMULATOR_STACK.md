# Multi-fidelity simulator stack

## Why a simulator hierarchy is necessary

A research-grade MARL study needs far more environment interactions than a detailed nonlinear structural model can economically provide. SeismicShield-RL therefore separates **training throughput** from **confirmatory physical fidelity** instead of pretending one simulator is ideal for every stage.

## Tier 0 — software-validation surrogate

Purpose:

- deterministic unit tests;
- API/environment checks;
- artifact and seed validation.

Never used for seismic-performance claims.

## Tier 1 — calibrated fast nonlinear MDOF engine

Purpose:

- vectorized/high-throughput RL training;
- rapid optimizer screening;
- domain randomization;
- algorithm debugging.

Required capabilities:

- story mass/stiffness/damping matrices;
- nonlinear restoring force option;
- friction-damper hysteretic abstraction;
- adaptive time stepping or explicit convergence monitoring;
- batch execution;
- deterministic seeds;
- response histories and energy accounting.

Its scientific value depends on measured agreement with Tier 2, not on convenience.

## Tier 2 — OpenSeesPy nonlinear reference

Purpose:

- reference structural response;
- damper-model validation;
- all primary confirmatory metrics;
- final benchmark evidence.

Planned modeling layers:

1. canonical shear-building reference cases;
2. nonlinear multi-story frame archetypes;
3. friction-damper link elements with explicit force/velocity/displacement recorders;
4. configurable damping and integration algorithms;
5. convergence recovery policy that is logged, deterministic and identical across methods.

## Tier 3 — detailed external-validity models

Optional high-fidelity 2D/3D archetypes for external validity and stress testing. Tier 3 is exploratory unless its exact models are frozen into the preregistration.

## Cross-tier validation matrix

Every validated case records:

- natural periods/modes;
- peak and time-history displacement;
- MIDR;
- PFA;
- damper force;
- damper deformation/velocity;
- dissipated energy;
- numerical convergence;
- runtime.

Report absolute and normalized errors by response quantity and by intensity range. A single aggregate correlation is not sufficient.

## Emulator/surrogate extension

A learned response surrogate may later be trained on OpenSees runs to accelerate search, but it must be treated as a separate model with:

- train/calibration/test split;
- predictive uncertainty;
- OOD diagnostics;
- error-conditioned rejection/fallback to OpenSees;
- no confirmatory claim computed solely from surrogate predictions.
