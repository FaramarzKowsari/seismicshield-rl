# SeismicShield Benchmark specification

## Scope

The benchmark is designed to test **optimization quality, robustness, sample efficiency and transfer**, not merely whether an RL training curve rises.

## Building axis

Primary planned story families:

| Family | Role |
|---|---|
| 3 story | low-dimensional reference and literature comparability |
| 6 story | medium-scale design |
| 10 story | larger combinatorial allocation |
| 20 story | scalability and transfer stress test |

## Earthquake axis

Evaluation is grouped by earthquake event to prevent leakage. Planned strata include:

- training events;
- validation events;
- held-out confirmatory events;
- intensity-shift subset;
- spectral/temporal characteristic shift subset where metadata supports defensible grouping.

## Structural uncertainty axis

- mass variation;
- stiffness variation;
- damping variation;
- selected nonlinear-model parameters;
- damper tolerance;
- optional modeling uncertainty across archetypes.

## Method axis

### Transparent

- no damper
- uniform allocation
- drift-proportional allocation
- random search

### Evolutionary / black-box

- GA
- NSGA-II
- optional CMA-ES / Bayesian optimization

### Learned

- PPO
- IPPO
- MAPPO/CTDE primary method
- optional risk-sensitive/conditioned extension

## Objective axis

Primary:

- normalized retrofit cost
- MIDR
- PFA

Secondary:

- residual drift
- maximum displacement
- damper force/stroke demand
- dissipated energy
- CVaR tail metrics
- invalid/failure rate
- compute cost

## Generalization matrix

Each method is separately evaluated for:

1. seen building family + unseen earthquake;
2. unseen structural draw;
3. unseen earthquake + structural shift;
4. cross-height transfer;
5. optional cross-archetype transfer.

## Algorithm-budget accounting

Every result row records:

- simulator backend;
- number of simulator calls;
- training environment steps;
- wall time;
- CPU model/core count;
- GPU model when used;
- peak memory where measurable;
- seed;
- source commit;
- configuration hash.

## Benchmark artifacts

Each frozen benchmark release contains:

```text
benchmark/
  manifests/
    ground_motions.csv
    structural_worlds.parquet
    seeds.csv
    algorithms.yaml
  raw/
  derived/
  figures/
  stats/
  failures/
  checksums/
```

The public benchmark must be runnable at a small scale on commodity hardware and reproducible at full scale on larger compute without paid AI APIs.
