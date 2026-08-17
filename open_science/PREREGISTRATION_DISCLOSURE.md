# Prior-work disclosure before preregistration

SeismicShield-RL already contains a v0.1 software foundation and a tiny deterministic smoke benchmark. To preserve scientific integrity, the future OSF record must not imply that no work occurred before preregistration.

The preregistration will state that the following were completed before registration:

- repository architecture and packaging;
- synthetic ground-motion fixture;
- simplified deterministic shear-building surrogate;
- environment/API contracts;
- transparent toy baselines;
- software unit tests;
- a smoke benchmark used only to verify determinism and artifact generation.

These outputs are permanently classified **exploratory / software-validation-only**.

The confirmatory claim gate begins only after:

1. the OSF registration is public;
2. its DOI is recorded in `open_science/preregistration.json`;
3. high-fidelity simulator validation is frozen;
4. the confirmatory test manifest and analysis plan are frozen;
5. the preregistration gate script passes.
