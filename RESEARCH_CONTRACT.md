# Research Contract — SeismicShield-RL v0.1

## 1. Primary research question

Can a multi-agent co-design policy optimize friction-damper count, story allocation and slip-force parameters while improving the held-out cost–MIDR–PFA Pareto frontier against equal-budget transparent and learned baselines?

## 2. Unit of evaluation

The primary evaluation unit is an **earthquake world**: a ground-motion record plus a structural-parameter draw. All candidate algorithms are compared on the same frozen worlds.

## 3. Primary estimands

- held-out MIDR ratio relative to the no-damper response
- held-out PFA ratio relative to the no-damper response
- normalized retrofit cost
- Pareto hypervolume over cost/MIDR/PFA
- tail-risk degradation under structural and ground-motion shift

## 4. Baselines required before a MARL claim

- no damper
- uniform allocation
- drift-proportional allocation
- equal-budget random search
- multi-objective evolutionary search (planned v0.3)
- single-agent PPO (planned v0.3)

A MARL claim is blocked until every required baseline uses the same simulator fidelity, data split, objective normalization and evaluation budget.

## 5. Train / validation / test discipline

Ground motions are assigned once to immutable train, validation and test manifests. Hyperparameters and reward weights may use train/validation only. The test manifest is opened for confirmatory evaluation after analysis code and primary metrics are frozen.

## 6. Pairing

All methods are evaluated on identical record IDs, structural draws and evaluation seeds. Report paired differences, not only independent group averages.

## 7. Statistics

The confirmatory plan will use earthquake-world bootstrap confidence intervals and paired randomization/permutation tests for prespecified primary contrasts. Family-wise multiplicity will be controlled for the primary contrast family. Exact procedures and alpha are frozen before the confirmatory run.

## 8. Uncertainty and robustness

Required stress tests:

- unseen ground motions
- building-height shift
- mass/stiffness/damping perturbations
- sensor/observation ablation for adaptive-control task
- reward-weight sensitivity
- damper-capacity discretization sensitivity
- solver non-convergence and invalid-design accounting

Parameter ranges are configuration values, not assumed physical truths; calibrated ranges must cite an engineering source or dataset.

## 9. Ablation matrix

At minimum:

- shared reward vs local+global reward
- centralized critic vs decentralized critic
- parameter sharing vs independent policies
- global context in observations on/off
- structural randomization on/off
- cost term on/off
- PFA term on/off
- damper count decision fixed vs learned

## 10. Claim gate

A result is paper-eligible only when `paper/EVIDENCE_LEDGER.csv` contains a verified claim ID with source artifacts and checksums. Smoke results, dashboard outputs and exploratory notebooks are not paper evidence.

## 11. No paid AI dependency

The research stack must run without OpenAI or any paid AI inference API. Core dependencies are local/open research software. External data services may be used only when their access and provenance are documented and a reproducible fallback fixture exists.

## 12. Release discipline

- `v0.x`: exploratory/research-development releases; no final claims
- `v0.8`: frozen confirmatory code + manifests
- `v0.9`: final statistical analysis + manuscript candidate
- `v1.0`: citable research release, DOI, archived evidence and final technical paper

## 13. Preregistration gate

The v0.1 smoke benchmark predates preregistration and is disclosed as exploratory software validation. No high-fidelity confirmatory benchmark may run until a public OSF preregistration DOI is recorded and the automated gate passes.

## 14. Multi-fidelity claim boundary

Tier-0/Tier-1 simulators may support development and training, but primary engineering claims must be recomputed on the validated OpenSees reference backend. Surrogate-only results cannot verify a primary evidence-ledger claim.

## 15. Persistent-identifier separation

The OSF registration, Zenodo software/evidence release and engrXiv manuscript are separate scholarly objects and must receive/cite separate persistent identifiers with explicit cross-relations.
