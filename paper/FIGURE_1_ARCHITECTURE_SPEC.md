# Figure 1 — SeismicShield-RL Architecture Specification

## Purpose

Create one clean, publication-grade schematic that explains how SeismicShield-RL separates exploratory/software-validation work from selection and confirmatory evidence generation.

## Required visual flow

Left-to-right primary flow:

1. **Data contracts**
   - Synthetic fixtures
   - Frozen ESM manifest
   - SHA-256 provenance
   - Partitions: Train 52 / Validation 20 / Pilot 16 / Confirmatory 48

2. **Structural worlds & design contract**
   - 3 / 6 / 10 / 20 stories
   - 16 structural states
   - Damper count + slip-force design
   - Objectives: Cost / MIDR / PFA

3. **Algorithms under common rules**
   - Random Search
   - Scalar GA
   - NSGA-II
   - PPO
   - IPPO
   - MAPPO
   - Equal/frozen budgets and seeds

4. **Simulation fidelity ladder**
   - Tier-1 research simulator
   - Tier-2 OpenSeesPy backend
   - Common evaluator

5. **Reproducibility control plane**
   - Immutable scientific source
   - Fail-closed confirmatory gate
   - Deterministic execution planner
   - Atomic shard ledger
   - Selection-only workspace

6. **Evidence boundary**
   - Evidence ledger
   - Verified: integrity/runtime preflight
   - Blocked: efficacy/generalization/robustness claims

## Critical gate relationship

Show a visually explicit closed gate between **Selection freeze** and **Confirmatory Tier-2**. The figure must make clear that confirmatory access remains locked until Stage-A selection is completed and frozen.

## Numbers that may appear

- 136 processed records / 34 events
- 16 structural states
- 475 atomic shards
- 2,820,160 structural-response calls
- Stage A: 424 shards / 2,780,992 Tier-1 calls
- Tier-2: 51 shards / 39,168 calls
- Runtime preflight: 4 Tier-1 + 4 Tier-2 pilot fixtures converged

Do not include algorithm-performance rankings because none exist for the confirmatory benchmark.

## Visual style

- Scientific journal schematic, not marketing artwork.
- White background.
- Strong hierarchy and generous whitespace.
- Simple geometric boxes, arrows, and one gate/lock motif.
- High legibility when reduced to a single journal column or page width.
- No decorative earthquake photography.
- No pseudo-data charts.
- Avoid gradients, shadows, 3D effects, and unnecessary icons.

## Caption

**Figure 1. SeismicShield-RL research-software architecture and evidence boundary.** Frozen data, structural-world, objective, algorithm, seed, and budget contracts feed a common simulation/evaluation layer. Immutable scientific source, deterministic planning, and provenance controls govern execution. Stage-A selection is separated from confirmatory Tier-2 evaluation by a fail-closed gate, and the evidence ledger distinguishes verified infrastructure claims from efficacy claims that remain blocked.

## Accuracy rules

- The figure is an explanatory architecture schematic, not a report of scientific outcomes.
- Do not imply that MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search is superior.
- Do not imply that the full Stage-A or Tier-2 campaigns have run.
- Do not imply code compliance, life-safety certification, or real-building approval.
