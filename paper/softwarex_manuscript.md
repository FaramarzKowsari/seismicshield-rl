# SeismicShield-RL: Preregistered and Reproducible Research Software for Auditable Seismic Friction-Damper Co-Design Benchmarking

**Article type:** Original Software Publication  
**Target journal:** SoftwareX  
**Author:** Faramarz Kowsari  
**ORCID:** https://orcid.org/0000-0003-1692-0453  
**Affiliation:** [confirm before submission]  
**Corresponding-author email:** [confirm before submission]

## Abstract

SeismicShield-RL is open-source research software for auditable benchmarking of reinforcement learning, multi-agent reinforcement learning, and multi-objective optimization in seismic friction-damper co-design. It converts experimental choices—data partitions, seeds, budgets, source identity, selection rules, and confirmatory access—into explicit software contracts. The frozen scientific infrastructure contains 136 processed earthquake records, 16 structural states, Tier-1 and OpenSeesPy Tier-2 simulation paths, cryptographic provenance, and a deterministic execution ledger. Pilot preflight verified record hashes and exercised both simulation tiers without inspecting confirmatory outcomes. The software therefore supports reproducible future comparisons while explicitly preventing infrastructure-validation results from being misrepresented as algorithm-efficacy evidence.

**Keywords:** Seismic engineering; Reinforcement learning; Friction dampers; OpenSeesPy; Reproducible research; Multi-objective optimization

## Code metadata

| Nr. | Code metadata description | Metadata |
|---|---|---|
| C1 | Current code version | v0.8.3 |
| C2 | Permanent link to code/repository used for this code version | https://github.com/FaramarzKowsari/seismicshield-rl/tree/267e4abcb376faf07d0ca8b2cda827de30a43bdf |
| C3 | Permanent link to Reproducible Capsule | Exact v0.8.3 SoftwareX archive DOI to be inserted after release; frozen v0.8.2 scientific archive: https://doi.org/10.5281/zenodo.22067278; software concept DOI: https://doi.org/10.5281/zenodo.22067277 |
| C4 | Legal Code License | MIT License |
| C5 | Code versioning system used | Git |
| C6 | Software code languages, tools, and services used | Python; NumPy; PyYAML; OpenSeesPy; Gymnasium; PettingZoo; TorchRL/PyTorch; pymoo; FastAPI; pytest; GitHub Actions |
| C7 | Compilation requirements, operating environments & dependencies | Python >=3.11; optional OpenSeesPy backend pinned to 3.8.0.0 for Python >=3.12; dependency groups declared in `pyproject.toml`; CI covers Python 3.11 and 3.12 on Ubuntu |
| C8 | If available, link to developer documentation/manual | https://faramarzkowsari.github.io/seismicshield-rl/researcher-guide.html |
| C9 | Support email for questions | [confirm corresponding-author email before submission] |

## 1. Motivation and significance

Optimizing friction-damper layouts is a coupled structural-design problem: changing the number, location, or slip-force level of dampers on one story changes the dynamic response of the whole building. Reinforcement-learning methods have already been investigated for friction-damper placement, demonstrating that learned decision policies can be relevant to this design space [1]. The harder scientific question is how to compare such methods fairly when the evaluation itself is expensive, stochastic, and sensitive to implementation choices.

Deep reinforcement-learning results can vary with random seeds, environment details, evaluation procedures, and reporting choices [2]. More generally, reproducible computational research requires exact tracking of software versions, parameters, intermediate artifacts, random seeds, and the path by which a result was produced [3,4]. Research-software and MLOps work has likewise emphasized provenance, configuration management, automated testing, and experiment traceability [5,6]. These practices are necessary, but they do not by themselves enforce a boundary between exploratory development and a later confirmatory evaluation.

SeismicShield-RL addresses that boundary as a software problem. Its central design choice is to represent experiment identity explicitly: earthquake partitions, structural worlds, objective definitions, algorithm budgets, seeds, selection behavior, analysis rules, and source identity are frozen as machine-readable or version-controlled contracts. Confirmatory execution is fail-closed. If the expected source, manifest, or contract cannot be authenticated, the run stops rather than silently substituting a convenient current state.

The software contribution is therefore not a new reinforcement-learning algorithm or a new finite-element solver. It is a reusable experimental-governance layer for simulation-based optimization. The current release deliberately separates two software identities. Version 0.8.3 is the publication and usability package. The scientific experiment remains frozen at v0.8.2, tag `confirmatory-v0.8.2-final`, commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`, with its exact archive preserved on Zenodo [7]. This separation permits documentation, examples, and submission support to improve without redefining the registered scientific computation.

## 2. Software functionalities

### 2.1 Architecture and frozen benchmark contracts

SeismicShield-RL is organized around a common evaluation path for heuristic optimization, evolutionary optimization, single-agent reinforcement learning, and multi-agent reinforcement learning. Figure 1 summarizes the intended architecture: data and provenance enter frozen experimental contracts; contracts feed a deterministic execution planner; optimization methods interact with common simulation and objective interfaces; simulation outputs are recorded through an evidence and provenance layer.

The frozen v0.8.2 scientific infrastructure identifies 136 processed earthquake records from 34 events. The records are partitioned at the event level into 52 training, 20 validation, 16 pilot, and 48 confirmatory records. Restricted waveform bytes are not redistributed. Instead, the repository preserves source provenance and processed-waveform SHA-256 values so authorized users can re-establish record identity without the project republishing restricted source data.

Structural uncertainty is represented by 16 states across 3-, 6-, 10-, and 20-story buildings. For each building height, one nominal state and three frozen perturbations are defined. Candidate friction-damper designs encode story-level damper counts and slip-force levels. The shared objective layer evaluates retrofit cost, maximum inter-story drift ratio (MIDR), and peak floor acceleration (PFA). Scalar reward or objective combinations used by particular algorithms are kept separate from the underlying physical response calculation.

The registered algorithm ladder contains random search, scalar genetic optimization, NSGA-II, PPO, IPPO, and MAPPO. NSGA-II supplies an established multi-objective evolutionary baseline [8], while the software can use the pymoo framework for multi-objective optimization [9]. Single-agent and multi-agent interfaces share the same evaluator and budget accounting. PettingZoo-compatible multi-agent abstractions support story-decomposed MARL without permitting an agent implementation to bypass the frozen objective or data contracts [10].

### 2.2 Multi-fidelity simulation and research boundaries

The project provides two simulation paths. Tier-1 is a fast research surrogate intended for software development, algorithm engineering, and large-scale preliminary evaluation. Tier-2 uses OpenSeesPy, the Python interface to the OpenSees finite-element framework [11], as a higher-fidelity verification backend. The fidelity distinction is explicit in the evidence model: a Tier-1 result is not automatically treated as engineering validation, and a pilot Tier-2 convergence check is not treated as confirmatory evidence.

Above the numerical layer, the repository contains seed ledgers, frozen manifests, source-authentication checks, confirmatory gates, selection-only workspaces, continuous-integration workflows, and an evidence ledger. The evidence ledger records claim status rather than merely storing output files. A claim may be verified as infrastructure evidence, exploratory, or blocked. This allows the repository to encode a scientifically important state that ordinary result folders often obscure: a calculation may be technically successful while still being ineligible to support a paper-level efficacy claim.

Execution is expanded before full computation into deterministic atomic shards. The frozen plan contains 475 shards and 2,820,160 structural-response calls: 424 Stage-A Tier-1 shards comprising 2,780,992 calls, followed by 51 Tier-2 confirmatory shards comprising 39,168 calls. Learned Stage-A shards couple training and validation selection under the frozen implementation. Arbitrarily splitting such a shard to fit an external CI time limit would change the registered computational semantics, so infrastructure interruption is handled differently from a scientific solver failure.

### 2.3 Sample code and public validation example

Version 0.8.3 adds a small public example designed specifically for software validation. It uses a synthetic fixture and never reads the frozen confirmatory earthquake partition. After installation, the example can be run with:

```bash
pip install -e ".[dev,api]"
python scripts/run_softwarex_example.py --output-dir results/softwarex_example
```

The runner writes benchmark artifacts plus `audit_summary.json`. The summary records the software version, configuration hash, synthetic-fixture hash, output hashes, convergence status, and two explicit evidence-boundary fields:

```text
confirmatory_data_used = false
paper_level_efficacy_claim = false
```

These fields are also protected by automated tests. The example is therefore useful for checking installation, configuration, artifact generation, hashing, and evidence labeling, but it cannot be mistaken for a reduced confirmatory experiment.

### 2.4 Illustrative example: auditable runtime preflight

The preserved v0.8.2 runtime preflight provides a larger illustrative example. It authenticated the frozen scientific source, checked the earthquake manifest, independently reproduced SHA-256 values for all 136 processed records, reproduced the frozen partition counts, and exercised four Tier-1 and four Tier-2 pilot fixtures. All eight pilot fixture calls converged in the tested environment.

Measured mean wall-clock times were approximately 1.329 s per Tier-1 call and 1.989 s per Tier-2 call in the recorded Linux/Python 3.12 environment. Applying those measured rates to the deterministic call ledger projected approximately 1,026.68 sequential simulation hours for Stage A and 21.64 sequential hours for the Tier-2 campaign. These values are workload projections for the tested environment, not hardware-independent performance guarantees.

The preflight did not execute confirmatory structural-response simulations, emit confirmatory response metrics, or inspect confirmatory outcomes. That distinction changed the project decision. The measured workload exceeded the intended no-cost execution envelope, while splitting atomic learned shards merely to satisfy hosted-CI limits would have altered the registered semantics. Rather than shrink the protocol after preregistration, the full Stage-A and Tier-2 campaigns were deferred. The software thus demonstrated a second function beyond running experiments: it made the cost of the registered experiment visible early enough to stop without contaminating the confirmatory boundary.

## 3. Impact

SeismicShield-RL enables research questions that are difficult to pose cleanly with ad hoc experiment scripts. A future user can ask whether MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search differs in held-out Pareto performance under identical earthquake partitions, structural uncertainty, budgets, seeds, selection rules, and objective definitions. Because those conditions are explicit software objects, a later comparison can distinguish an algorithmic difference from a hidden change in experimental protocol.

The software also improves existing simulation-based research by making provenance and eligibility of evidence inspectable. Prior work on reproducible computation emphasizes versioning, seeds, intermediate results, and public scripts [3,4], while MLOps-oriented research software emphasizes traceability and automated workflow structure [5]. Provenance-focused SoftwareX work shows the continuing need to connect outputs with the code and context that generated them [6]. SeismicShield-RL extends these concerns to a confirmatory boundary: it records not only how an output was produced, but whether the output was authorized to answer the scientific question being claimed.

The architecture is transferable beyond friction dampers. The same pattern can be adapted to structural control, retrofit optimization, design under uncertainty, or other machine-learning studies that use a cheap simulator for development and reserve an expensive solver for final evaluation. The reusable elements are domain-independent: immutable scientific source, frozen partitions, equal-budget algorithm contracts, deterministic execution plans, restart semantics, cryptographic provenance, and evidence-status tracking.

Current impact should nevertheless be stated conservatively. The repository is a recent research-software release; no claim is made here about widespread adoption, commercial use, or changes in users' daily practice. The full registered Stage-A and confirmatory Tier-2 campaigns have not been executed, so the software provides no evidence that any included optimization method is superior, no demonstrated out-of-distribution generalization result, and no certification of real-building safety. The Tier-1 surrogate and Tier-2 OpenSeesPy backend remain research components that require problem-specific engineering validation before real-world design use.

This limitation is part of the software's intended value. In the evidence ledger, infrastructure facts—such as successful pilot convergence and verified processed-record hashes—can be marked verified while efficacy statements remain blocked. The system therefore reduces the risk that readiness evidence is rhetorically upgraded into performance evidence simply because a manuscript needs a result.

## 4. Conclusions

SeismicShield-RL turns normally informal choices in simulation-based machine-learning research into explicit software contracts. Data partitions, seeds, algorithm budgets, source identity, checkpoint-selection behavior, simulation fidelity, execution units, and evidence status can all be inspected before expensive computation begins. The frozen v0.8.2 infrastructure establishes the scientific boundary, while v0.8.3 provides publication-oriented metadata, documentation, tests, and a synthetic validation example without changing that frozen experiment.

The runtime preflight verified the integrity and execution pathways needed for the registered study and exposed its computational scale before confirmatory outcomes were inspected. When the projected workload exceeded the intended resource envelope, the project preserved the protocol and deferred execution rather than modifying the experiment after registration. The resulting software is therefore useful both for running future comparisons and for defining when a comparison has not yet earned a scientific claim.

## Acknowledgements

No external funding is claimed for the work described in this manuscript.

## Data and code availability

The source code is publicly available at https://github.com/FaramarzKowsari/seismicshield-rl under the MIT License. The frozen v0.8.2 scientific release is archived at Zenodo, DOI https://doi.org/10.5281/zenodo.22067278, with software concept DOI https://doi.org/10.5281/zenodo.22067277. The preregistered protocol is identified separately by OSF DOI https://doi.org/10.17605/OSF.IO/64DTX. Restricted earthquake waveform bytes are not redistributed; provenance metadata and processed-waveform hashes are preserved instead. The exact v0.8.3 SoftwareX archive DOI will be inserted after the submission release is minted.

## Declaration of competing interest

The author declares no competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## References

[1] M.C. Kurucu, E. Atam, M. Guzelkaya, I. Eksin, Intelligent Computational Methods for Optimal Distribution of Friction Dampers in Seismic Protection of Buildings, IEEE Transactions on Emerging Topics in Computational Intelligence 8(4) (2024) 3055–3066. https://doi.org/10.1109/TETCI.2024.3369909.

[2] P. Henderson, R. Islam, P. Bachman, J. Pineau, D. Precup, D. Meger, Deep Reinforcement Learning That Matters, Proceedings of the AAAI Conference on Artificial Intelligence 32(1) (2018). https://doi.org/10.1609/aaai.v32i1.11694.

[3] G.K. Sandve, A. Nekrutenko, J. Taylor, E. Hovig, Ten Simple Rules for Reproducible Computational Research, PLOS Computational Biology 9(10) (2013) e1003285. https://doi.org/10.1371/journal.pcbi.1003285.

[4] G. Wilson, J. Bryan, K. Cranston, J. Kitzes, L. Nederbragt, T.K. Teal, Good enough practices in scientific computing, PLOS Computational Biology 13(6) (2017) e1005510. https://doi.org/10.1371/journal.pcbi.1005510.

[5] R. Godwin, R.L. Melvin, Toward efficient data science: A comprehensive MLOps template for collaborative code development and automation, SoftwareX 26 (2024) 101723. https://doi.org/10.1016/j.softx.2024.101723.

[6] G. Padovani, S. Fiore, yProv4DV: Filling the visualization gap in reproducible research workflows, SoftwareX 35 (2026) 102821. https://doi.org/10.1016/j.softx.2026.102821.

[7] F. Kowsari, SeismicShield-RL: Preregistered Reproducible Infrastructure for Seismic Damper Co-Design Benchmarking, version 0.8.2, Zenodo (2026). https://doi.org/10.5281/zenodo.22067278.

[8] K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, A fast and elitist multiobjective genetic algorithm: NSGA-II, IEEE Transactions on Evolutionary Computation 6(2) (2002) 182–197. https://doi.org/10.1109/4235.996017.

[9] J. Blank, K. Deb, pymoo: Multi-Objective Optimization in Python, IEEE Access 8 (2020) 89497–89509. https://doi.org/10.1109/ACCESS.2020.2990567.

[10] J.K. Terry, B. Black, N. Grammel, M. Jayakumar, A. Hari, R. Sullivan, L.S. Santos, C. Dieffendahl, C. Horsch, R. Perez-Vicente, N. Williams, Y. Lokesh, P. Ravi, PettingZoo: Gym for Multi-Agent Reinforcement Learning, Advances in Neural Information Processing Systems 34 (2021).

[11] M. Zhu, F. McKenna, M.H. Scott, OpenSeesPy: Python library for the OpenSees finite element framework, SoftwareX 7 (2018) 6–11. https://doi.org/10.1016/j.softx.2017.10.009.
