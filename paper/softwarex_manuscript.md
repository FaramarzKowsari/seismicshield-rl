# SeismicShield-RL: Preregistered and Reproducible Research Software for Auditable Seismic Friction-Damper Co-Design Benchmarking

**Article type:** Original Software Publication  
**Target journal:** SoftwareX  
**Author:** Faramarz Kowsari  
**ORCID:** https://orcid.org/0000-0003-1692-0453

## Highlights

- Preregistered benchmark infrastructure separates exploration, selection, and confirmatory evaluation.
- Frozen data partitions, seeds, budgets, and immutable source make computational decisions auditable.
- Tier-1 and OpenSeesPy Tier-2 runtime paths were verified on pilot fixtures without inspecting confirmatory outcomes.
- Deterministic execution planning exposes the full computational workload before expensive experiment execution.

## Abstract

SeismicShield-RL is open-source research software for preregistered and reproducible benchmarking of reinforcement learning, multi-agent reinforcement learning, and multi-objective optimization in seismic friction-damper co-design. The software treats data partitions, algorithm budgets, random seeds, source identity, checkpoint-selection rules, and confirmatory access as explicit computational contracts rather than informal experimental conventions. Its architecture combines deterministic execution planning, cryptographic provenance, earthquake-record partitioning, structural-uncertainty models, a fast Tier-1 research simulator, and an OpenSeesPy Tier-2 verification backend. The v0.8.2 infrastructure freezes 136 processed earthquake records from 34 events into training, validation, pilot, and confirmatory partitions and represents 16 structural states across four building heights. Runtime preflight reproduced all frozen processed-record hashes and successfully exercised four Tier-1 and four Tier-2 pilot fixtures. The registered computation is deterministically represented by 475 atomic shards comprising 2,820,160 structural-response calls. The full Stage-A and confirmatory Tier-2 campaigns were deliberately deferred when measured compute requirements exceeded the intended no-cost execution envelope. Accordingly, this release makes no claim about algorithm superiority; instead, it provides a reusable software pattern for preserving a clean confirmatory boundary in expensive simulation-based machine-learning studies.

**Keywords:** Seismic engineering; Reinforcement learning; Friction dampers; OpenSeesPy; Reproducible research; Multi-objective optimization

## Code metadata

| Nr. | Code metadata description | SeismicShield-RL |
|---|---|---|
| C1 | Current code version | v0.8.2 |
| C2 | Permanent link to code/repository used for this code version | https://github.com/FaramarzKowsari/seismicshield-rl |
| C3 | Permanent archive / reproducible software record | Zenodo version DOI: https://doi.org/10.5281/zenodo.22067278; concept DOI: https://doi.org/10.5281/zenodo.22067277 |
| C4 | Legal Code License | MIT License |
| C5 | Code versioning system used | Git |
| C6 | Software code languages, tools, and services used | Python; NumPy; PyYAML; OpenSeesPy; Gymnasium; PettingZoo; TorchRL/PyTorch; pymoo; FastAPI; pytest; GitHub Actions |
| C7 | Compilation requirements, operating environments & dependencies | Python >=3.11. OpenSeesPy optional backend is pinned to 3.8.0.0 for Python >=3.12. Optional dependency groups are declared in `pyproject.toml`. Pilot preflight was recorded on Linux with Python 3.12.14. |
| C8 | Developer documentation/manual | https://faramarzkowsari.github.io/seismicshield-rl/researcher-guide.html |
| C9 | Support | GitHub Issues: https://github.com/FaramarzKowsari/seismicshield-rl/issues; corresponding-author email should be entered in the journal submission system. |

## 1. Motivation and significance

Seismic retrofit optimization with friction dampers is a computational design problem in which decisions at individual stories interact through nonlinear structural response. Recent work has shown that reinforcement-learning methods can be used to search damper distributions for earthquake protection [1]. The scientific difficulty, however, is broader than implementing a learning algorithm. A convincing comparison must control which earthquake records are available during tuning, how computational budgets are allocated, how stochastic seeds are handled, when checkpoints are selected, what structural uncertainty is exposed to each method, and whether final evaluation data remain unseen while experimental choices are still being made.

These concerns are especially acute in reinforcement learning. Henderson et al. [2] documented substantial reproducibility and comparison problems arising from implementation details, stochasticity, evaluation choices, and inconsistent reporting. In simulation-based engineering, the same weaknesses can be amplified by costly numerical solvers and by the temptation to change experiments after partial results reveal which choices are promising. A benchmark can therefore be technically executable while still being scientifically difficult to audit.

SeismicShield-RL was developed around a different premise: the experimental boundary itself should be software. The project represents data identities, partitions, objective definitions, algorithm identities, budgets, seeds, model-selection behavior, inferential rules, and source provenance as frozen machine-readable or version-controlled contracts. Confirmatory execution is guarded by fail-closed checks. Scientific source is identified by an immutable Git tag and commit. Execution is planned as atomic shards whose meaning is fixed before expensive computation begins. An evidence ledger distinguishes verified infrastructure claims from blocked efficacy claims.

This design does not attempt to claim novelty for reinforcement learning, PPO, MARL, NSGA-II, or friction dampers in isolation. Rather, the software contribution is an auditable benchmark architecture for comparing those methods under a preregistered information boundary. The current release is intentionally an infrastructure result. It preserves the possibility of a later clean confirmatory study instead of weakening the protocol to fit a convenient compute budget.

## 2. Software description

### 2.1 Architecture

SeismicShield-RL is organized as a layered research system. Ground motions enter through data contracts carrying stable identifiers and provenance metadata. Synthetic fixtures are explicitly tagged so they cannot be confused with real records. Structural response is exposed through a common simulation contract. A fast nonlinear shear-building simulator provides the Tier-1 path for software validation and large-scale algorithm engineering, while an OpenSeesPy backend provides the higher-fidelity Tier-2 path. OpenSeesPy itself is a Python interface to the OpenSees finite-element framework and is widely used for structural and earthquake-engineering simulation [3].

The objective layer converts a candidate design into damper counts, slip-force assignments, a normalized retrofit-cost proxy, maximum inter-story drift ratio (MIDR), and peak floor acceleration (PFA). Physics code is intentionally separated from reinforcement-learning reward weights. Single-agent and multi-agent environments share the same evaluator and may not bypass objective normalization, invalid-design checks, data partitions, or budget accounting. PettingZoo-style multi-agent interfaces support story-decomposed MARL while retaining an interoperable environment abstraction [4].

Above the numerical layer, SeismicShield-RL adds research-governance components: frozen manifests, seed ledgers, confirmatory gates, deterministic planning, selection-only workspaces, provenance checks, CI workflows, and an evidence ledger. These components are not presentation utilities. They determine which scientific computations are authorized and which claims are eligible to move from blocked to verified status.

### 2.2 Frozen benchmark objects

The v0.8.2 earthquake manifest contains 136 records from 34 events. The frozen partition contains 52 training records, 20 validation records, 16 pilot records, and 48 confirmatory records. Restricted waveform bytes are not redistributed by the repository. Instead, the benchmark stores source provenance and processed-waveform hashes so record identity can be re-established without publishing restricted source files.

Four building heights are represented: 3, 6, 10, and 20 stories. Each height has one nominal model and three frozen structural perturbations, producing 16 structural states. At each story, a candidate design may choose a damper count from zero through four and a slip-force level from a fixed grid. The principal objective vector retains retrofit cost, MIDR, and PFA. Where scalarization is required by a training or baseline method, its weights are fixed by the registered contract rather than selected after observing confirmatory results.

The registered algorithm ladder contains random search, a scalar genetic algorithm, NSGA-II, PPO, IPPO, and MAPPO. NSGA-II provides a standard elitist multi-objective evolutionary baseline [5], and the implementation can use the pymoo ecosystem for multi-objective optimization [6]. Eight algorithm seeds are frozen in the protocol. Learned-policy checkpoint schedules and validation-selection behavior are also specified before confirmatory execution.

### 2.3 Immutable source and fail-closed execution

The scientific implementation is frozen at tag `confirmatory-v0.8.2-final` and commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`. This separation between immutable scientific source and later operational tooling allows transport, documentation, or crash-safety utilities to evolve without silently redefining the registered computation.

Before confirmatory work can run, the gate checks the expected source identity, manifests, numerical settings, algorithm bundle, seeds, and analysis contract. Failure to authenticate the expected state stops execution rather than substituting a newer working tree. This fail-closed behavior matters because a successful numerical result generated from the wrong code or wrong partition is not a valid instance of the preregistered study.

### 2.4 Deterministic execution planning

The registered computation is expanded into an auditable ledger of atomic work units before full execution. The final plan contains 475 shards and 2,820,160 structural-response calls. Stage A contains 424 shards and 2,780,992 Tier-1 calls; the subsequent Tier-2 campaign contains 51 shards and 39,168 calls.

A learned Stage-A shard couples training and validation behavior through the frozen implementation. Because checkpoint selection occurs within that scientific unit, splitting the shard merely to satisfy an external hosted-CI wall-clock limit would alter registered semantics. SeismicShield-RL therefore distinguishes an infrastructure interruption from a scientific solver failure. Infrastructure interruption calls for whole-shard restart. A solver or numerical failure produced by the simulator is retained as a scientific outcome and is not silently retried until success.

## 3. Software functionalities

The public release supports five practical research functions.

First, it creates reproducible benchmark identities. Earthquake manifests, processed hashes, structural worlds, seeds, algorithms, and analysis rules are versioned and cross-checked. This makes it possible to ask whether two reported runs are instances of the same experiment rather than merely similar scripts.

Second, it separates software testing from scientific evidence. Pilot records and synthetic fixtures can be used to debug environments, numerical convergence, APIs, and orchestration. Outputs from these paths are labeled exploratory or runtime-validation evidence. They cannot automatically become paper-level claims.

Third, it supports multiple optimization families behind common evaluation rules. Heuristics, evolutionary methods, single-agent RL, and MARL share objective definitions and budget accounting. This reduces the risk that one method receives hidden advantages through different preprocessing or evaluation logic.

Fourth, the project provides a fidelity ladder. The Tier-1 simulator is suitable for rapid engineering of algorithms and execution infrastructure. The Tier-2 OpenSeesPy path supplies a higher-fidelity backend under the same conceptual simulation contract. The distinction is explicit so surrogate convenience is not mistaken for engineering validation.

Fifth, the evidence ledger encodes the epistemic status of claims. For example, the v0.8.2 ledger marks the runtime-preflight claim as verified but keeps algorithm-superiority and generalization claims blocked. This makes the absence of a result visible and machine-checkable rather than leaving it to prose qualifiers in a paper.

## 4. Illustrative example: an auditable preflight without confirmatory leakage

The v0.8.2 runtime preflight illustrates the intended workflow. The process authenticated the immutable scientific source, materialized or checked records against the frozen manifest, reproduced processed-waveform SHA-256 values for all 136 records, and reproduced the expected partition counts. It then exercised four Tier-1 and four Tier-2 pilot fixtures. All eight fixture calls converged in the tested environment.

The preserved preflight artifact reports a mean Tier-1 wall-clock time of approximately 1.329 s per call and a mean Tier-2 time of approximately 1.989 s per call on the recorded Linux/Python 3.12 environment. Applying these measured rates to the registered call ledger projected approximately 1,026.68 sequential Tier-1 simulation hours for Stage A and 21.64 sequential hours for the Tier-2 campaign. These figures are workload projections from the tested environment, not promises of calendar completion on other hardware.

Crucially, the preflight records that no confirmatory structural-response simulations were run, no confirmatory response metrics were emitted, and no confirmatory outcome was inspected. One pilot record was used for runtime testing; the confirmatory boundary remained closed. The outcome of the preflight was therefore not a statement about seismic performance. It was evidence that the data-integrity and runtime paths were ready and that the registered study had a computational scale that could be quantified before committing resources.

This result caused a scientifically meaningful stopping decision. The project had been designed around a no-cost execution envelope, while the measured workload—especially the atomic learned Stage-A shards—exceeded what standard hosted CI could execute without changing the registered semantics. Instead of shrinking budgets after preregistration or presenting a reduced convenience study as the registered experiment, the full Stage-A and Tier-2 campaigns were deferred. The uninspected confirmatory boundary was preserved for a future continuation with suitable compute.

## 5. Impact

SeismicShield-RL contributes a reusable pattern for high-integrity computational experimentation rather than a new claim about which optimization algorithm is best. Its immediate domain is seismic friction-damper co-design, where recent research already demonstrates the relevance of intelligent optimization and reinforcement learning [1]. The software adds the missing experimental-governance layer needed to compare such methods under fixed information and computational budgets.

For researchers, the main practical benefit is traceability. A reported result can be tied to a source commit, data manifest, processed hashes, structural world, seed set, algorithm contract, execution shard, and analysis rule. This structure is useful when numerical experiments are expensive enough that failures, restarts, partial execution, and hardware constraints become part of the scientific process rather than incidental engineering details.

The architecture is also transferable. The same pattern can be applied to other simulation-based optimization problems in which researchers tune models on relatively inexpensive approximations and reserve expensive high-fidelity solvers for later confirmation. Examples include structural control, retrofit optimization, design under uncertainty, and other reinforcement-learning studies coupled to finite-element or multiphysics simulators. The key reusable elements are not earthquake-specific: immutable scientific source, frozen partitions, equal-budget algorithm contracts, fail-closed gates, atomic execution planning, and evidence-status tracking.

The project further demonstrates a useful negative capability for research software: it can encode when *not* to claim a result. In the current evidence ledger, the statement that the runtime preflight verified all 136 processed hashes and converged on four Tier-1 plus four Tier-2 pilot fixtures is verified. Claims that MARL improves held-out Pareto performance, generalizes to unseen earthquakes, or remains competitive under structural uncertainty are explicitly blocked. This distinction reduces pressure to turn infrastructure readiness into efficacy rhetoric.

## 6. Limitations and intended use

SeismicShield-RL is research software, not a building-design certification tool. The Tier-1 surrogate and Tier-2 OpenSeesPy backend are components of a benchmark and require problem-specific validation before any real-building engineering use. The software does not certify code compliance, life safety, retrofit approval, or damper suitability for a particular structure.

The principal scientific limitation of v0.8.2 is deliberate and substantial: the full registered Stage-A optimization/selection campaign and the confirmatory Tier-2 experiment have not been executed. The software therefore provides no evidence that MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search is superior on the frozen benchmark. It also does not establish out-of-distribution generalization or robustness to the frozen structural uncertainties.

The earthquake-record workflow depends on external source access and does not redistribute restricted waveform bytes. Reproduction therefore requires continued availability of the source material or equivalent authorized access. Runtime estimates are hardware-dependent and do not include every orchestration, training, I/O, or scheduling cost.

A future continuation should preserve the immutable v0.8.2 scientific contracts, execute the 424 Stage-A shards, freeze the selected designs and learned checkpoints, and only then authorize the 51 confirmatory Tier-2 shards. Any modified protocol should be identified as a new study rather than retrospectively presented as the original preregistration.

## 7. Conclusions

SeismicShield-RL turns several normally informal choices in simulation-based machine-learning research into explicit software objects: source identity, data partitions, seeds, budgets, checkpoint selection, evidence status, and confirmatory access. The v0.8.2 release verifies the integrity and runtime pathways needed to execute its registered benchmark and exposes the full computational workload through a deterministic execution ledger. When that workload exceeded the intended resource envelope, the project stopped before confirmatory outcome inspection rather than altering the protocol to manufacture a convenient result.

The contribution is therefore infrastructural but scientifically consequential. A benchmark is useful not only when it produces rankings; it is also useful when it makes clear which rankings have not yet been earned. By preserving an auditable path from source data to future evidence, SeismicShield-RL provides a reusable research-software architecture for expensive reinforcement-learning and optimization studies coupled to engineering simulation.

## Data and code availability

The source code is available at https://github.com/FaramarzKowsari/seismicshield-rl under the MIT License. The exact v0.8.2 software release is archived at Zenodo, DOI https://doi.org/10.5281/zenodo.22067278, with concept DOI https://doi.org/10.5281/zenodo.22067277. The preregistered protocol is identified separately by OSF DOI https://doi.org/10.17605/OSF.IO/64DTX. The repository does not redistribute restricted earthquake waveform bytes; provenance and frozen processed-waveform hashes are provided instead.

## Declaration of competing interest

The author declares no competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## Acknowledgements

No external funding is claimed in this manuscript. Computational experiments reported here are limited to the preserved runtime/integrity preflight and pilot fixtures described above.

## References

[1] M.C. Kurucu, E. Atam, M. Guzelkaya, I. Eksin, Intelligent Computational Methods for Optimal Distribution of Friction Dampers in Seismic Protection of Buildings, IEEE Transactions on Emerging Topics in Computational Intelligence 8(4) (2024) 3055–3066. https://doi.org/10.1109/TETCI.2024.3369909.

[2] P. Henderson, R. Islam, P. Bachman, J. Pineau, D. Precup, D. Meger, Deep Reinforcement Learning That Matters, Proceedings of the AAAI Conference on Artificial Intelligence 32(1) (2018). https://doi.org/10.1609/aaai.v32i1.11694.

[3] M. Zhu, F. McKenna, M.H. Scott, OpenSeesPy: Python library for the OpenSees finite element framework, SoftwareX 7 (2018) 6–11. https://doi.org/10.1016/j.softx.2017.10.009.

[4] J.K. Terry, B. Black, N. Grammel, M. Jayakumar, A. Hari, R. Sullivan, L.S. Santos, C. Dieffendahl, C. Horsch, R. Perez-Vicente, N. Williams, Y. Lokesh, P. Ravi, PettingZoo: Gym for Multi-Agent Reinforcement Learning, Advances in Neural Information Processing Systems 34 (2021).

[5] K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, A fast and elitist multiobjective genetic algorithm: NSGA-II, IEEE Transactions on Evolutionary Computation 6(2) (2002) 182–197. https://doi.org/10.1109/4235.996017.

[6] J. Blank, K. Deb, pymoo: Multi-Objective Optimization in Python, IEEE Access 8 (2020) 89497–89509. https://doi.org/10.1109/ACCESS.2020.2990567.

[7] F. Kowsari, SeismicShield-RL: Preregistered Reproducible Infrastructure for Seismic Damper Co-Design Benchmarking, version 0.8.2, Zenodo (2026). https://doi.org/10.5281/zenodo.22067278.
