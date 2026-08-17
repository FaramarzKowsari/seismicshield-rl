# Project Manifest

**Project:** SeismicShield-RL  
**Version:** 0.1.0  
**Author:** Faramarz Kowsari  
**Research domain:** structural control, multi-agent reinforcement learning, multi-objective optimization  
**Primary structural engine target:** OpenSeesPy  
**Development backend:** deterministic N-story research surrogate  
**Paid AI APIs:** none required  

## Non-negotiable rules

1. No result enters README/paper as evidence without a frozen artifact trail.
2. No learned method is compared against a baseline with a different evaluation budget.
3. Test earthquakes are not used for reward/hyperparameter selection.
4. Simulator convergence failures are counted and reported, not silently dropped.
5. Public demo output is exploratory unless linked to a verified evidence ID.
6. Synthetic data are always labeled synthetic.
7. Engineering and safety limits are stated beside the relevant result.

## Open-science control files

- `open_science/preregistration.json` — machine-readable registration gate state
- `open_science/OSF_PREREGISTRATION_DRAFT.md` — ADEMP-aligned confirmatory protocol draft
- `open_science/PREREGISTRATION_DISCLOSURE.md` — disclosure of v0.1 pilot work
- `open_science/DOI_RELATIONSHIP_GRAPH.md` — persistent identifier roles
- `open_science/PUBLICATION_RELEASE_PLAN.md` — OSF → GitHub/Zenodo → engrXiv sequence
- `SIMULATOR_STACK.md` — multi-fidelity simulator specification
- `BENCHMARK_SPEC.md` — expanded benchmark matrix
