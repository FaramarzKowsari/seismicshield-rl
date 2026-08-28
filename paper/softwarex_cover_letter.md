# Cover Letter — SoftwareX

**Manuscript:** *SeismicShield-RL: Preregistered and Reproducible Research Software for Auditable Seismic Friction-Damper Co-Design Benchmarking*  
**Article type:** Original Software Publication

Dear Editors of SoftwareX,

Please consider the manuscript, “SeismicShield-RL: Preregistered and Reproducible Research Software for Auditable Seismic Friction-Damper Co-Design Benchmarking,” for publication as an Original Software Publication in SoftwareX.

SeismicShield-RL is open-source research software designed to make reinforcement-learning and multi-objective optimization studies in seismic friction-damper co-design reproducible and auditable. The software treats earthquake-data partitions, algorithm budgets, random seeds, source identity, checkpoint-selection rules, provenance, and confirmatory access as explicit computational contracts. It combines a fast Tier-1 research simulator, an OpenSeesPy Tier-2 path, deterministic execution planning, cryptographic record provenance, a fail-closed confirmatory gate, and an evidence ledger that distinguishes verified infrastructure claims from efficacy claims that have not yet been earned.

The frozen scientific infrastructure defines 136 processed earthquake records, 16 structural states, and a deterministic registered workload of 475 atomic shards comprising 2,820,160 structural-response calls. Runtime preflight independently reproduced all processed-record hashes and successfully exercised four Tier-1 and four Tier-2 pilot fixtures. Importantly, no confirmatory structural-response outcome was inspected. When measured computational requirements exceeded the intended no-cost execution envelope, the full Stage-A and Tier-2 campaigns were deferred rather than modifying the preregistered protocol after the fact.

Accordingly, the manuscript does not claim that MAPPO, PPO, IPPO, NSGA-II, scalar genetic optimization, or random search is superior. Its contribution is the reusable research-software architecture itself: a system for separating exploration, selection, and confirmation while preserving traceable evidence lineage in expensive simulation-based machine-learning research.

The public illustrative example accompanying the manuscript was re-executed in a clean GitHub Actions environment using CPython 3.12.14. All example methods converged; the run used only the synthetic fixture, explicitly recorded `confirmatory_data_used=false` and `paper_level_efficacy_claim=false`, and its output hashes are frozen in the repository for auditability.

The project is publicly available under the MIT License, with Git version control, public documentation, automated tests, an OSF preregistration, and permanent Zenodo archives. The exact SoftwareX submission release, v0.8.3, is archived at DOI 10.5281/zenodo.22144346. The immutable v0.8.2 scientific infrastructure remains separately archived at DOI 10.5281/zenodo.22067278, and the preregistered protocol is identified by DOI 10.17605/OSF.IO/64DTX. Publication-support changes in v0.8.3 do not modify the frozen v0.8.2 scientific computation.

We believe this work fits SoftwareX because the primary contribution is reusable, inspectable research software intended to improve reproducibility, auditability, and scientific reuse across computational engineering and related simulation-based optimization studies.

The manuscript is not under consideration elsewhere. The author takes responsibility for the integrity and accuracy of the submission and will complete all required declarations in the Editorial Manager system.

Sincerely,

**Faramarz Kowsari**  
Independent Researcher  
ORCID: https://orcid.org/0000-0003-1692-0453  
Email: faramarzkowsari@gmail.com
