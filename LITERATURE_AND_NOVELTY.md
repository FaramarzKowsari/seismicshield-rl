# Literature map and novelty boundary

## Direct Boğaziçi / Ercan Atam research line

This repository is intentionally adjacent to, but must not merely duplicate, the ongoing work led by Assoc. Prof. Ercan Atam at Boğaziçi University's Institute for Data Science and Artificial Intelligence.

### Ongoing projects

1. **A Multi-Agent Deep Reinforcement Learning Approach to Optimization of Friction Damper Systems for Seismically Excited Buildings** — Boğaziçi BAP, 2024–2026. The institute describes the problem as large-scale, non-convex and multi-objective, with multi-agent deep RL for optimal friction-damper placement.
   - https://dsai.bogazici.edu.tr/en/pages/research-projects/2815

2. **Simultaneous Reinforcement Learning-based Optimization of the Number, Distribution, and Adaptive Slip Forces of Friction Dampers for Earthquake-Resistant Buildings** — TÜBİTAK BİLGEM, 2025–2026. The project explicitly targets simultaneous optimization of damper number, inter-story distribution and adaptive slip force.
   - https://dsai.bogazici.edu.tr/en/pages/research-projects/2815

### Closely related publications

- M. C. Kurucu, E. Atam, M. Guzelkaya, I. Eksin, **“Intelligent Computational Methods for Optimal Distribution of Friction Dampers in Seismic Protection of Buildings,”** IEEE Transactions on Emerging Topics in Computational Intelligence, 2024.
  - DOI: https://doi.org/10.1109/TETCI.2024.3369909

- Boğaziçi DSAI announced a 2026 paper using PPO for adaptive control of semi-active friction dampers and benchmarking it against constant-force and rule-based strategies.
  - https://dsai.bogazici.edu.tr/en/news/academic/1/a-new-paper-co-authored-by-ercan-atam-present/3517

## Novelty rule for SeismicShield-RL

The project must **not** claim novelty for “using PPO,” “using RL for dampers,” or “using multi-agent RL for friction-damper placement.” Those directions already exist in the target research line.

The intended contribution is instead the combination of:

1. **Open benchmark contract.** Fixed building tasks, earthquake manifests, cost definition, evaluation budgets, metrics, seeds and statistical protocol.
2. **Scale ladder.** 3-, 6-, 10- and 20-story task families using the same interface.
3. **Generalization first.** Held-out earthquakes, building-height transfer and structural-parameter shift are primary evaluation axes rather than optional demonstrations.
4. **Multi-objective reporting.** Cost, MIDR and PFA are preserved as a Pareto problem; scalar reward is treated as one training mechanism, not the scientific conclusion.
5. **Equal-budget comparisons.** Heuristics, evolutionary search, single-agent RL and MARL receive auditable optimization/evaluation budgets.
6. **Uncertainty and tail risk.** World-level bootstrap intervals, paired tests, solver-failure accounting and risk-sensitive/CVaR experiments.
7. **Backend fidelity ladder.** Fast surrogate for algorithm engineering, then validated OpenSees parity, then confirmatory runs.
8. **Research software contribution.** PettingZoo/Gym interfaces, REST API, frozen benchmark artifacts, Docker, CI, evidence ledger and interactive demonstrator.

## Falsifiable contribution statement

A paper is worthwhile only if the benchmark can answer at least one nontrivial question such as:

> Under equal optimization budgets, does story-decomposed centralized-training/decentralized-execution MARL produce a statistically and practically better held-out cost–MIDR–PFA Pareto frontier than single-agent PPO and non-learning optimizers, and does any advantage persist under unseen earthquake records and structural uncertainty?

A negative answer is scientifically acceptable. The benchmark remains useful if it shows where MARL does **not** help.
