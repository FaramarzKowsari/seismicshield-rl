# Technical paper outline

## Working title

**SeismicShield-RL: A Reproducible Multi-Agent Reinforcement Learning Benchmark for Multi-Objective Seismic Damper Co-Design**

## Abstract structure

Problem → reproducibility gap → benchmark/task definition → methods → frozen held-out results → uncertainty/ablations → limitations. Numerical claims remain blank until the evidence ledger marks them verified.

## 1. Introduction

- seismic damper placement is combinatorial, nonlinear and multi-objective
- RL can amortize repeated optimization, but fair comparison requires a shared benchmark
- contribution is not “PPO exists”; contribution is a reproducible co-design benchmark and robust generalization study

## 2. Related work

- friction-damper placement optimization
- deep RL for seismic structural control
- MARL / centralized training decentralized execution
- multi-objective and robust structural optimization
- reproducibility in computational structural engineering

## 3. Problem formulation

- building model and state variables
- damper design vector
- story-level agent decomposition
- objective vector: cost, MIDR, PFA
- constraints and invalid designs

## 4. Benchmark design

- building families
- earthquake manifests and preprocessing
- train/validation/test split
- equal-budget evaluation
- pairing and seed policy

## 5. Methods

- heuristics and random search
- NSGA-II
- single-agent PPO
- IPPO
- MAPPO
- robust/risk-sensitive candidate

## 6. Experiments

- in-distribution performance
- unseen earthquakes
- unseen building heights
- domain randomization
- compute/sample efficiency

## 7. Ablations

- critic, parameter sharing, rewards, observations, randomization

## 8. Uncertainty and error analysis

- bootstrap intervals
- paired tests and multiplicity
- solver failures
- sensitivity analysis
- tail risk

## 9. Interactive simulator and software architecture

Demonstrator is documented as a reproducibility aid, not evidence generation.

## 10. Limitations

- model fidelity
- device model assumptions
- record representativeness
- code/retrofit design boundaries
- sim-to-real gap

## 11. Reproducibility statement

- commit SHA
- container digest
- artifact hashes
- frozen manifests
- DOI/archive
