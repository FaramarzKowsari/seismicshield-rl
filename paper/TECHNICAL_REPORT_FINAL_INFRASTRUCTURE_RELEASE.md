# SeismicShield-RL v0.8.2 — Final Infrastructure Technical Report

**Release classification:** Final Infrastructure Release  
**Scientific experiment status:** Full-scale confirmatory experiment deferred  
**Date:** 2026-08-23  
**Author:** Faramarz Kowsari  
**Preregistered protocol:** OSF DOI `10.17605/OSF.IO/64DTX`  
**Immutable scientific source:** `confirmatory-v0.8.2-final`  
**Scientific source commit:** `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`

## Abstract

SeismicShield-RL is a preregistered research-software platform for benchmarking reinforcement-learning and multi-objective optimization methods for friction-damper co-design under earthquake and structural uncertainty. The project was developed with a strict separation between exploratory software validation, training/validation model selection, and confirmatory evaluation. Its principal contribution at this release boundary is the completed reproducible research infrastructure rather than a completed algorithm-efficacy comparison.

The project freezes the earthquake manifest, structural worlds, objective definitions, algorithm identities, computational budgets, random seeds, checkpoint-selection rules, and inferential analysis before confirmatory response evaluation. A runtime preflight independently reproduced the frozen processed-waveform hashes for all 136 ESM records and successfully exercised four Tier-1 and four Tier-2 pilot fixtures without inspecting confirmatory structural-response outcomes. Deterministic execution planning decomposed the registered experiment into 475 atomic shards comprising 2,820,160 structural-response calls. Of these, Stage A alone requires 2,780,992 Tier-1 calls, with measured preflight throughput projecting approximately 1,026.68 hours of sequential Tier-1 simulation. The subsequent Tier-2 campaign contains 39,168 calls with a projected sequential simulation time of approximately 21.64 hours.

Because the full registered computation exceeded the intended no-cost compute envelope, the project is closed at this point as a **Final Infrastructure Release**. The full Stage-A selection campaign, the 768-design selection freeze, and the confirmatory Tier-2 campaign were not executed. Consequently, this release makes no claim about whether MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search performs best on the preregistered confirmatory benchmark. The uninspected confirmatory boundary is deliberately preserved so that the study could be resumed in the future without contaminating the original preregistration.

## 1. Purpose of the project

The research question motivating SeismicShield-RL is whether reinforcement-learning methods, particularly multi-agent reinforcement learning, can discover friction-damper retrofit designs with stronger out-of-sample trade-offs among cost, maximum inter-story drift ratio (MIDR), and peak floor acceleration (PFA) than transparent heuristic and evolutionary optimization methods.

The project was designed to address several recurring reproducibility problems in computational structural-control research:

1. earthquake splits may change while algorithms are tuned;
2. optimizer budgets may differ across methods;
3. validation and confirmatory data can be inadvertently mixed;
4. model-selection rules can be chosen after results are known;
5. scientific source code can drift after a protocol is registered;
6. large compute jobs can be resumed or retried in ways that subtly alter stochastic semantics;
7. reported results may become difficult to trace back to exact source, data, seeds, and numerical settings.

SeismicShield-RL therefore treats the execution contract, information boundary, and evidence lineage as first-class research objects.

## 2. Scientific design frozen before confirmatory evaluation

### 2.1 Earthquake records

The frozen ESM manifest contains 136 records from 34 events. The registered partitions are:

| Partition | Record count | Intended role |
|---|---:|---|
| Training | 52 | optimizer/policy learning |
| Validation | 20 | candidate/checkpoint selection |
| Pilot | 16 | software/runtime validation only |
| Confirmatory | 48 | final out-of-sample evaluation |
| **Total** | **136** | — |

The repository does not redistribute restricted waveform bytes. Instead, source provenance and frozen processed-waveform hashes establish record identity.

### 2.2 Structural states

Four building heights are represented: 3, 6, 10, and 20 stories. Each height has one nominal model and three frozen structural perturbations. This produces 16 structural states.

### 2.3 Retrofit design variables

For each story, the design may select a damper count from 0 through 4 and a slip-force level from the frozen grid:

`0, 50,000, 100,000, 200,000, 350,000 N`.

The representation is canonicalized so that a story with zero dampers does not acquire a scientifically distinct design identity merely because an irrelevant non-zero slip-force value was encoded.

### 2.4 Objectives

The registered optimization evaluates three principal objectives:

- retrofit cost proxy;
- maximum inter-story drift ratio (MIDR);
- peak floor acceleration (PFA).

The frozen scalar objective uses prespecified weights where scalarization is required. Multi-objective analyses retain Pareto information rather than converting all comparisons into a single post-hoc score.

### 2.5 Algorithms

The registered stochastic algorithm ladder contains:

- random search;
- scalar genetic algorithm;
- NSGA-II;
- PPO;
- IPPO;
- MAPPO.

Eight frozen algorithm seeds are used:

`1103, 2207, 3313, 4421, 5521, 6637, 7753, 8861`.

The learned-policy checkpoint schedule and validation-selection behavior were fixed before confirmatory evaluation.

## 3. Reproducibility architecture completed

### 3.1 Immutable scientific source

The scientific implementation is frozen at tag `confirmatory-v0.8.2-final`, commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`. Scientific execution is required to resolve the relevant package code and contracts from this immutable source rather than from a mutable working tree.

This distinction permits later operational utilities to improve transport, verification, or crash safety without changing the registered scientific computation.

### 3.2 Fail-closed confirmatory gate

The confirmatory gate verifies the frozen source, manifests, numerical settings, algorithm bundle, seed ledger, and analysis contract. If the expected scientific state cannot be authenticated, execution must stop rather than silently substitute a new state.

### 3.3 Data-integrity preflight

The preserved preflight artifact is:

`results/validation/confirmatory_runtime_preflight_v0.8.2.json`

The preflight independently verified the frozen processed-waveform hashes for all 136 records. Partition counts reproduced the expected 52 training, 20 validation, 16 pilot, and 48 confirmatory records.

The preflight did not perform the registered confirmatory structural-response experiment and did not inspect confirmatory performance outcomes.

### 3.4 Pilot runtime checks

Four Tier-1 and four Tier-2 pilot fixtures were successfully exercised. These checks establish that the numerical/runtime stack is operational in the tested environment. They are not evidence that any optimization method is seismically superior.

### 3.5 Deterministic execution planner

The complete registered computation was transformed into an auditable atomic execution ledger. The final plan contains:

| Component | Shards | Calls per shard / structure | Total calls |
|---|---:|---:|---:|
| Tier-1 feature precompute | 16 | 52 | 832 |
| Tier-1 non-policy train + validate | 384 | 3,840 | 1,474,560 |
| Tier-1 learned train + validate | 24 | 54,400 | 1,305,600 |
| **Stage A total** | **424** | — | **2,780,992** |
| Tier-2 seeded confirmatory | 48 | 768 | 36,864 |
| Tier-2 support | 3 | 768 | 2,304 |
| **Tier-2 total** | **51** | — | **39,168** |
| **Grand total** | **475** | — | **2,820,160** |

The planner is deterministic and binds execution to the frozen scientific contract.

### 3.6 Atomicity and restart semantics

A learned Stage-A shard contains training and validation behavior that is scientifically coupled by the frozen implementation. Validation is performed during the learned training loop and only the selected checkpoint is returned. Splitting such a shard solely to satisfy an external CI wall-clock limit would alter the execution semantics.

For infrastructure interruption, the intended policy is whole-shard restart rather than scientific mid-shard continuation. By contrast, solver or numerical failure returned by the simulator is a scientific outcome and must not be silently retried as though it were an infrastructure failure.

### 3.7 Selection-only workspace

The merged selection-only workspace preparation layer exposes the 424 Stage-A shards while keeping the 51 confirmatory Tier-2 shards locked. At this release boundary:

- confirmatory data hydration is not authorized;
- confirmatory execution is not authorized;
- confirmatory outcomes have not been inspected.

The workspace is published atomically and binds its execution ledger to reviewed source bytes and Git object provenance.

## 4. Measured compute requirement and stopping rationale

The runtime preflight measured approximately:

- Tier-1 mean wall-clock time: `1.32904380175 s/call`;
- Tier-2 mean wall-clock time: `1.98916977725 s/call`.

Applying these measured values to the registered call counts gives the following sequential simulation projections:

- Tier-1 Stage A: approximately `1,026.68 hours`;
- Tier-2 campaign: approximately `21.64 hours`.

These figures describe simulation-call time projected from the tested preflight environment. They do not promise wall-clock completion under arbitrary parallel hardware; orchestration overhead, policy optimization, I/O, scheduling, and hardware variation can change calendar time.

The main practical constraint is Stage A. The 24 learned shards each contain 54,400 calls and are intentionally atomic under the frozen scientific implementation. Standard hosted CI wall-clock limits cannot accommodate such a shard without altering the registered scientific execution semantics. A suitable persistent local or self-hosted compute target could execute the study, but acquiring and operating such a target was outside the project's no-cost resource objective.

The project was therefore stopped before the expensive scientific run rather than reducing budgets after preregistration, modifying algorithms to fit infrastructure limits, or presenting a smaller convenience experiment as though it were the registered confirmatory study.

## 5. What this release establishes

This release supports the following infrastructure-level conclusions:

1. the confirmatory protocol is publicly preregistered;
2. the scientific source and contracts are immutably identified;
3. the 136-record processed-waveform manifest can be independently reproduced at the hash level;
4. the tested Tier-1 and Tier-2 runtime paths execute successfully on pilot fixtures;
5. the full registered workload has a deterministic 475-shard execution plan;
6. the information boundary can keep confirmatory execution locked while Stage-A selection infrastructure is prepared;
7. the computational scale of the registered experiment is quantified by measured preflight evidence.

These are reproducibility and infrastructure findings, not seismic-efficacy findings.

## 6. What this release does not establish

The following claims remain unsupported and must not be inferred from the release:

- MAPPO is better than PPO;
- MAPPO is better than IPPO;
- MAPPO is better than NSGA-II;
- any learned method is better than random search or scalar GA;
- the selected policies generalize to unseen earthquakes;
- any method is robust to the frozen structural uncertainties;
- the proposed dampers are suitable for a real building;
- the benchmark demonstrates code compliance, life-safety performance, or retrofit approval.

The corresponding efficacy claims remain blocked in `paper/EVIDENCE_LEDGER.csv`.

## 7. Deferred scientific sequence

If suitable compute becomes available in the future and the original registered study is resumed, the scientifically valid continuation is:

1. retain the immutable scientific source and contracts;
2. prepare the selection-only workspace;
3. hydrate training and validation data only;
4. execute all 424 Stage-A shards;
5. verify the exact Stage-A call count of 2,780,992;
6. freeze the 768 selected method/seed/state designs and learned checkpoints;
7. publish that selection freeze at an immutable reference;
8. only then authorize confirmatory data hydration;
9. execute the 51 Tier-2 shards totaling 39,168 calls;
10. apply the preregistered event-level inferential analysis.

No retrospective modification of the frozen protocol should be presented as the original preregistered confirmatory study.

## 8. Preservation of scientific optionality

Stopping before confirmatory response evaluation preserves a valuable property: the confirmatory data boundary remains uncontaminated by outcome inspection. The project can therefore be resumed later without first having to explain away confirmatory-driven tuning that occurred during the deferred period.

Experimental Stage-A executor work that had not completed the same review and hardening standard as the merged infrastructure is intentionally excluded from this Final Infrastructure Release. This keeps the release boundary conservative and auditable.

## 9. Research-software contribution

Even without the final algorithm-ranking experiment, SeismicShield-RL provides a reusable example of how to construct a high-integrity computational benchmark with:

- preregistration before confirmatory response analysis;
- immutable scientific code;
- data partitions with explicit information boundaries;
- cryptographic provenance for processed records;
- equal-budget algorithm contracts;
- deterministic atomic execution planning;
- explicit handling of infrastructure versus scientific failures;
- selection freeze before confirmatory data access;
- evidence-ledger discipline;
- separation between research demonstration and paper-level evidence.

These design patterns are applicable beyond seismic control to other expensive simulation-based optimization and reinforcement-learning studies.

## 10. Safety and engineering scope

The software is a research platform. It does not certify buildings, prescribe construction, predict earthquakes, replace a licensed structural engineer, or provide regulatory approval. The fast Tier-1 surrogate and the Tier-2 OpenSeesPy backend are components of a computational benchmark and require domain-specific validation before any real-building engineering use.

## 11. Persistent identifiers and citation boundary

The OSF DOI `10.17605/OSF.IO/64DTX` identifies the preregistered protocol.

The Final Infrastructure Release should be cited as software using its GitHub release metadata and, if minted through the repository's Zenodo integration, its software release DOI. The OSF DOI must not be relabeled as the software DOI.

## 12. Final status statement

**Phase I — Reproducible Experimental Infrastructure: COMPLETE.**

**Phase II — Full-scale Stage-A computational experiment: DEFERRED DUE TO COMPUTATIONAL-RESOURCE REQUIREMENTS.**

**Phase III — Confirmatory Tier-2 evaluation and inferential analysis: NOT RUN.**

No confirmatory structural-response result has been generated or inspected for the purpose of algorithm selection or final efficacy reporting.

This is the terminal status of SeismicShield-RL v0.8.2 unless a future project explicitly resumes the preregistered computation.
