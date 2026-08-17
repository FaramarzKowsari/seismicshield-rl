# Architecture

## Layer 1 — Data contracts

Ground motions are represented as time/acceleration arrays with stable IDs and provenance metadata. Synthetic fixtures are explicitly tagged and never confused with real earthquake records.

## Layer 2 — Structural backends

`ShearBuildingSimulator` is a fast nonlinear research surrogate used for environment development and software testing. A future `OpenSeesBackend` must implement the same `simulate(design, ground_motion)` contract.

Backend parity is a stage gate: metrics from matched linear/no-damper cases must agree within prespecified tolerances before OpenSees becomes the primary benchmark backend.

## Layer 3 — Objective model

Every design is converted to:

- count per story
- slip force per damper
- total story slip force
- normalized cost

The simulator emits MIDR, PFA and dissipated energy. The objective layer turns those metrics into either scalar rewards or Pareto vectors; the physics layer never knows RL reward weights.

## Layer 4 — Environments

- `SingleAgentDesignEnv`: flattened building-wide action, used for single-agent PPO and environment debugging.
- `ParallelDamperDesignEnv`: one story agent per story, simultaneous one-shot design action, shared reward.
- adaptive control environment: deliberately deferred until offline co-design is validated.

## Layer 5 — Algorithms

Baselines and learned policies share a common evaluator. Algorithm-specific code may not bypass objective normalization, invalid-design checks, data splits or budget accounting.

## Layer 6 — Evidence

Experiment configurations, raw metrics, derived statistics, manifests and hashes are versioned separately from UI artifacts.

## Layer 7 — Demonstrator

The API/dashboard can replay verified scenarios or execute exploratory simulations. Its outputs are tagged `exploratory` unless they originate from frozen evidence artifacts.
