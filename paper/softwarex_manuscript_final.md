# SeismicShield-RL: Preregistered and Reproducible Research Software for Auditable Seismic Friction-Damper Co-Design Benchmarking

**Article type:** Original Software Publication  
**Target journal:** SoftwareX  
**Author:** Faramarz Kowsari  
**ORCID:** https://orcid.org/0000-0003-1692-0453  
**Affiliation and corresponding-author email:** to be confirmed before journal submission.

## Highlights

- Preregistration separates exploration, selection, and confirmation.
- Frozen partitions, seeds, budgets, and source make runs auditable.
- Tier-1 and OpenSeesPy Tier-2 pilot paths pass runtime preflight.
- Deterministic planning exposes 2,820,160 response calls before execution.

## Abstract

SeismicShield-RL is open-source research software for preregistered, auditable benchmarking of reinforcement learning and multi-objective optimization in seismic friction-damper co-design. It freezes data partitions, algorithm budgets, random seeds, source identity, selection rules, and confirmatory access as explicit computational contracts. Version 0.8.3 packages the finalized v0.8.2 scientific infrastructure with publication-support utilities. The benchmark defines 136 processed earthquake records, 16 structural states, Tier-1 and OpenSeesPy Tier-2 simulation paths, and a deterministic 475-shard execution plan. Runtime preflight verified all processed-record hashes and eight pilot fixtures without inspecting confirmatory outcomes. The full registered experiment remains deferred, so no algorithm-superiority claim is made.

**Keywords:** Seismic engineering; Reinforcement learning; Friction dampers; OpenSeesPy; Reproducible research; Multi-objective optimization

## Metadata

| Nr. | Code metadata description | Metadata |
|---|---|---|
| C1 | Current code version | v0.8.3 (SoftwareX submission release; planned tag `v0.8.3-softwarex`) |
| C2 | Permanent link to code/repository used for this code version | https://github.com/FaramarzKowsari/seismicshield-rl |
| C3 | Permanent link to reproducible capsule | **To be replaced with the exact Zenodo v0.8.3 DOI after the release is minted.** Existing concept DOI: https://doi.org/10.5281/zenodo.22067277 |
| C4 | Legal Code License | MIT License |
| C5 | Code versioning system used | Git |
| C6 | Software code languages, tools, and services used | Python; NumPy; PyYAML; OpenSeesPy; Gymnasium; PettingZoo; PyTorch/TorchRL; pymoo; FastAPI; pytest; GitHub Actions |
| C7 | Compilation requirements, operating environments & dependencies | Python >=3.11; optional dependencies declared in `pyproject.toml`; OpenSeesPy 3.8.0.0 for Python >=3.12. Preserved runtime preflight used Linux and Python 3.12.14. |
| C8 | Link to developer documentation/manual | https://faramarzkowsari.github.io/seismicshield-rl/researcher-guide.html |
| C9 | Support email for questions | **To be filled with the corresponding-author email before submission.** GitHub Issues: https://github.com/FaramarzKowsari/seismicshield-rl/issues |

## 1. Motivation and significance

Friction-damper retrofit design is a coupled optimization problem: the number, location, and slip-force choices at individual stories alter nonlinear structural response under earthquake excitation. Intelligent optimization and reinforcement learning are already being studied for this class of problem [1]. The unresolved methodological issue is how to compare competing algorithms without allowing experimental choices to drift as results accumulate.

That issue matters because a benchmark can be executable yet still be difficult to audit. Which earthquake records were available during tuning? Did every method receive the same evaluation budget? Were random seeds fixed in advance? Were checkpoints selected on validation data or after examining the final test set? Was source code changed after a protocol was registered? Deep reinforcement-learning research has documented sensitivity to implementation details, stochasticity, and evaluation practice [2]. More broadly, computational reproducibility depends on making code, workflows, and data provenance inspectable [8,9].

SeismicShield-RL treats those choices as software objects rather than prose promises. The project freezes record identities and partitions, structural worlds, objective definitions, algorithm identities, computational budgets, seeds, checkpoint-selection rules, and inferential rules before confirmatory evaluation. Scientific source is bound to an immutable Git tag and commit. A fail-closed gate rejects execution when expected contracts cannot be authenticated. A deterministic planner expands the registered workload into atomic execution units, and an evidence ledger separates verified infrastructure claims from efficacy claims that remain blocked.

The contribution is therefore not “using PPO,” “using MARL,” or “using NSGA-II” for dampers. Those algorithmic directions pre-exist this software. The contribution is a reusable research-software architecture for keeping exploratory development, model selection, and confirmatory evaluation separated in an expensive simulation-based study. The current release deliberately stops at infrastructure readiness rather than converting an incomplete computation into a performance claim.

## 2. Software description

### 2.1 Software functionalities

SeismicShield-RL is organized around a common simulation-and-evaluation contract. Ground motions carry stable identifiers and provenance metadata. Synthetic fixtures are explicitly tagged and cannot be confused with real earthquake records. Structural response can be evaluated through a fast nonlinear Tier-1 shear-building simulator or through a higher-fidelity Tier-2 OpenSeesPy backend. OpenSeesPy provides Python access to the OpenSees finite-element framework and is established in structural and earthquake-engineering simulation [3].

The objective layer maps a candidate retrofit to damper counts, slip-force assignments, a normalized cost proxy, maximum inter-story drift ratio (MIDR), and peak floor acceleration (PFA). Physics code is separated from reinforcement-learning reward weights. Single-agent and multi-agent environments share the same evaluator and cannot bypass invalid-design checks, partitions, normalization, or budget accounting. PettingZoo-style interfaces support multi-agent experimentation through a standardized API [4].

The frozen v0.8.2 scientific benchmark contains 136 processed records from 34 earthquake events: 52 training, 20 validation, 16 pilot, and 48 confirmatory records. The repository does not redistribute restricted waveform bytes; instead it preserves source provenance and processed SHA-256 identities. Four building heights—3, 6, 10, and 20 stories—are represented. Each height has a nominal model and three frozen perturbations, giving 16 structural states.

The registered optimization ladder contains random search, scalar genetic optimization, NSGA-II, PPO, IPPO, and MAPPO. NSGA-II supplies a standard multi-objective evolutionary baseline [5], and the project can use pymoo for multi-objective optimization [6]. Eight stochastic seeds are frozen. Selection rules and learned-policy checkpoint behavior are specified before confirmatory evaluation.

Scientific execution is anchored to immutable tag `confirmatory-v0.8.2-final` and commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`. The newer v0.8.3 submission release does not alter that scientific source or unlock confirmatory results; it aligns package metadata and adds publication-support utilities. This distinction prevents manuscript preparation from silently redefining the preregistered experiment.

A deterministic execution planner converts the complete registered study into 475 atomic shards totaling 2,820,160 structural-response calls. Stage A contains 424 shards and 2,780,992 Tier-1 calls. The later Tier-2 campaign contains 51 shards and 39,168 calls. Learned Stage-A shards couple training and validation behavior under the frozen implementation, so splitting them merely to satisfy hosted-CI wall-clock limits would change registered semantics.

The evidence ledger is a final functional layer. Infrastructure-level claims can be marked verified only when linked artifacts exist; efficacy claims remain blocked until their required experiment is complete. In the current ledger, the runtime/integrity preflight is verified, whereas statements about MARL superiority, unseen-earthquake generalization, and robustness to structural uncertainty remain blocked.

For the SoftwareX submission package, `scripts/run_softwarex_example.py` and its automated test provide a public synthetic demonstration that is explicitly labeled `software-validation-only`. These publication-support utilities were prepared with assistance from OpenAI ChatGPT and then reviewed and tested by the author. They do not modify the immutable v0.8.2 scientific implementation and do not generate confirmatory evidence.

### 2.2 Reproducibility and provenance controls

The confirmatory gate checks expected source identity, manifests, numerical settings, algorithm definitions, seeds, and analysis contracts. Authentication failure stops execution. This fail-closed design is important because a numerically successful run from the wrong source tree or partition is not a valid instance of the preregistered study.

The project also distinguishes scientific failure from infrastructure failure. A solver or numerical failure returned by a simulator is retained as a scientific outcome. An infrastructure interruption instead requires restart of the whole atomic shard. This prevents retry policies from quietly converting difficult cases into successful ones.

A selection-only workspace exposes Stage-A work while keeping confirmatory Tier-2 shards locked. Confirmatory data hydration and outcome inspection are not authorized until Stage-A selection is complete and frozen. The software therefore makes information access itself part of the reproducibility architecture.

## 3. Illustrative examples

The preserved v0.8.2 runtime preflight demonstrates the intended workflow without crossing the confirmatory boundary. It authenticated the immutable scientific source, verified the frozen record manifest, independently reproduced processed-waveform hashes for all 136 records, and reproduced the expected partition counts. It then exercised four Tier-1 and four Tier-2 pilot fixtures. All eight pilot calls converged in the recorded environment.

The preflight measured approximately 1.329 s per Tier-1 call and 1.989 s per Tier-2 call. Applying those measured rates to the registered call ledger projected about 1,026.68 sequential Tier-1 simulation hours for Stage A and 21.64 sequential hours for Tier-2. These are workload projections from the tested environment, not hardware-independent completion guarantees.

The same artifact records three negative facts that are scientifically important: no confirmatory structural-response simulation was run, no confirmatory response metric was emitted, and no confirmatory outcome was inspected. The preflight therefore supports a readiness claim, not an efficacy claim.

A second, fully public example is provided by `scripts/run_softwarex_example.py`. It uses the repository's synthetic fixture and smoke configuration, executes the common evaluator against simple baseline designs, writes CSV/JSON/manifest artifacts, computes SHA-256 hashes, and produces an `audit_summary.json`. The summary records the package version, input hashes, generated-artifact hashes, convergence status, and the explicit flags `confirmatory_data_used=false` and `paper_level_efficacy_claim=false`. The accompanying automated test protects those evidence-boundary assertions.

**Figure 1.** Planned architecture schematic: data contracts and frozen partitions feed the simulation/evaluation layer; algorithm families share budget and objective contracts; deterministic planning and provenance controls govern execution; the evidence ledger receives only authorized artifacts; the confirmatory gate remains closed until selection is frozen.

## 4. Impact

SoftwareX emphasizes potential scientific impact and reuse. SeismicShield-RL addresses both by making experimental governance reusable. In its immediate domain, the software supports fair comparison of heuristic, evolutionary, single-agent RL, and multi-agent RL approaches to friction-damper co-design while preserving common objectives, budgets, data roles, and provenance. This enables a future question that is scientifically sharper than “does RL work?”: under equal budgets and frozen information boundaries, do story-decomposed MARL policies improve the held-out cost–MIDR–PFA trade-off, and does any advantage persist under unseen earthquakes and structural perturbations?

The architecture also improves existing computational practice. A result can be traced to an immutable source identifier, record manifest, processed hashes, structural world, seed, method contract, execution shard, and analysis rule. This becomes valuable when numerical studies are expensive enough that restarts, partial execution, solver failures, and hardware constraints are part of the scientific process rather than incidental software engineering.

The design is transferable beyond seismic dampers. Any study that uses inexpensive models for development and reserves expensive high-fidelity simulation for confirmation can reuse the same patterns: preregistered partitions, immutable source, equal-budget algorithm contracts, fail-closed access, atomic execution planning, and explicit evidence status. Candidate domains include structural control, retrofit design, engineering optimization under uncertainty, and reinforcement learning coupled to finite-element or multiphysics solvers.

A further contribution is the software's ability to represent the absence of evidence. The v0.8.2 ledger verifies that all 136 processed hashes were reproduced and that four Tier-1 plus four Tier-2 pilot fixtures converged. It does not promote those checks into a claim that any optimizer performs better. The blocked status of efficacy claims is visible in the repository. That separation reduces a common pressure in computational work: turning infrastructure readiness into scientific success because the expensive final experiment has not yet run.

The present impact is therefore primarily methodological and infrastructural rather than measured by a large external user base. The repository is a recent research-software release, and no unsupported claim of widespread adoption or commercial use is made. Its value for SoftwareX lies in the reusable design pattern, the open implementation, and the preserved path to a future confirmatory experiment.

## 5. Conclusions

SeismicShield-RL makes source identity, data partitions, stochastic seeds, computational budgets, checkpoint selection, execution units, evidence status, and confirmatory access explicit parts of research software. The frozen scientific infrastructure has passed record-integrity and pilot-runtime preflight, and its complete computational workload is exposed before large-scale execution.

Measured resource requirements exceeded the project's intended no-cost execution envelope. Rather than shrink budgets after preregistration or inspect confirmatory outcomes while redesigning the experiment, the project deferred Stage A and Tier-2. No ranking of MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search is claimed.

That stopping point is itself part of the software's purpose. A reproducible benchmark should make it difficult to claim more than its evidence supports. SeismicShield-RL provides an open, auditable architecture for preserving that discipline in simulation-based reinforcement-learning and optimization studies.

## Data and code availability

Source code is publicly available at https://github.com/FaramarzKowsari/seismicshield-rl under the MIT License. The exact frozen v0.8.2 infrastructure release is archived at https://doi.org/10.5281/zenodo.22067278, with software concept DOI https://doi.org/10.5281/zenodo.22067277. The preregistered protocol is separately identified by https://doi.org/10.17605/OSF.IO/64DTX. Before submission, the v0.8.3 SoftwareX packaging release will be archived and its exact Zenodo DOI inserted in metadata item C3. Restricted earthquake waveform bytes are not redistributed.

## Funding

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

## Declaration of competing interest

The author declares no competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## Acknowledgements

No external funding or institutional sponsorship is claimed for the work reported in this manuscript.

## Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

During the preparation of this work, the author used OpenAI ChatGPT (GPT-5.6 Sol) to assist with literature organization, manuscript structuring, language refinement, and preparation of publication-support code and documentation. The author reviewed and edited the resulting material, independently checked factual claims and references, and takes full responsibility for the content of the publication. AI-assisted publication-support utilities do not alter the immutable v0.8.2 scientific source or supply confirmatory research outcomes.

## References

[1] M.C. Kurucu, E. Atam, M. Guzelkaya, I. Eksin, Intelligent Computational Methods for Optimal Distribution of Friction Dampers in Seismic Protection of Buildings, IEEE Transactions on Emerging Topics in Computational Intelligence 8(4) (2024) 3055–3066. https://doi.org/10.1109/TETCI.2024.3369909.

[2] P. Henderson, R. Islam, P. Bachman, J. Pineau, D. Precup, D. Meger, Deep Reinforcement Learning That Matters, Proceedings of the AAAI Conference on Artificial Intelligence 32(1) (2018). https://doi.org/10.1609/aaai.v32i1.11694.

[3] M. Zhu, F. McKenna, M.H. Scott, OpenSeesPy: Python library for the OpenSees finite element framework, SoftwareX 7 (2018) 6–11. https://doi.org/10.1016/j.softx.2017.10.009.

[4] J.K. Terry, B. Black, N. Grammel, M. Jayakumar, A. Hari, R. Sullivan, L.S. Santos, C. Dieffendahl, C. Horsch, R. Perez-Vicente, N. Williams, Y. Lokesh, P. Ravi, PettingZoo: Gym for Multi-Agent Reinforcement Learning, Advances in Neural Information Processing Systems 34 (2021).

[5] K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, A fast and elitist multiobjective genetic algorithm: NSGA-II, IEEE Transactions on Evolutionary Computation 6(2) (2002) 182–197. https://doi.org/10.1109/4235.996017.

[6] J. Blank, K. Deb, pymoo: Multi-Objective Optimization in Python, IEEE Access 8 (2020) 89497–89509. https://doi.org/10.1109/ACCESS.2020.2990567.

[7] F. Kowsari, SeismicShield-RL: Preregistered Reproducible Infrastructure for Seismic Damper Co-Design Benchmarking, version 0.8.2, Zenodo (2026). https://doi.org/10.5281/zenodo.22067278.

[8] B.A. Nosek, C.R. Ebersole, A.C. DeHaven, D.T. Mellor, The preregistration revolution, Proceedings of the National Academy of Sciences 115(11) (2018) 2600–2606. https://doi.org/10.1073/pnas.1708274114.

[9] V. Stodden, M. McNutt, D.H. Bailey, E. Deelman, Y. Gil, B. Hanson, M.A. Heroux, J.P.A. Ioannidis, M. Taufer, Enhancing reproducibility for computational methods, Science 354(6317) (2016) 1240–1241. https://doi.org/10.1126/science.aah6168.
