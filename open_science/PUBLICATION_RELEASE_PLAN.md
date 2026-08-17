# Open-science publication and release plan

## Stage 1 — public preregistration

- create an OSF project for the continuing workspace;
- complete the OSF **Simulation Studies** registration template;
- attach/freeze the detailed protocol and planned benchmark manifest schema;
- disclose all v0.1 pilot/smoke work;
- make the registration public;
- record the issued OSF DOI in this repository;
- tag the source state used for preregistration.

**No confirmatory benchmark may run before this gate.**

## Stage 2 — simulator and benchmark validation

- OpenSeesPy reference backend;
- device-level parity tests;
- structural modal/time-history validation;
- calibrated fast simulator with quantified fidelity error;
- immutable data provenance and event-grouped splits;
- compute-feasibility pilot using worlds excluded from confirmatory test data.

## Stage 3 — exploratory development

- train/tune all required baseline and MARL methods on train/validation strata;
- complete ablations and robustness engineering;
- freeze primary metrics, reference points, normalization and analysis scripts;
- create the final confirmatory manifest without inspecting test outcomes.

## Stage 4 — confirmatory freeze and execution

Create a signed/frozen research state containing:

- Git commit SHA;
- environment lock/container digest;
- ground-motion manifest hashes;
- structural-world manifest hashes;
- seed ledger;
- algorithm configurations;
- statistical-analysis source hash;
- preregistration DOI.

Then run the confirmatory benchmark once under the registered rules. Any infrastructure rerun must preserve inputs and be logged.

## Stage 5 — evidence release

- raw confirmatory tables;
- derived tables;
- plots generated only from frozen evidence;
- solver/failure ledger;
- bootstrap/permutation artifacts;
- SHA-256 manifest;
- reproduction command and expected outputs.

## Stage 6 — GitHub v1.0 + Zenodo

- finalize `CITATION.cff` and/or `.zenodo.json` metadata;
- link OSF preregistration DOI;
- create GitHub v1.0 release;
- archive through Zenodo GitHub integration;
- obtain version DOI and concept DOI;
- update README, citation files and website with the identifiers.

## Stage 7 — preprint

Prepare a human-reviewed engineering manuscript whose results are generated directly from frozen artifacts. Submit the PDF and permitted supplements to **engrXiv**. After posting, record the engrXiv DOI and cross-link it to the OSF and Zenodo records.

## Stage 8 — post-preprint maintenance

- new software features go to v1.x/v2.x and receive new Zenodo version DOIs;
- corrections to the paper use engrXiv versioning with explicit justification;
- confirmatory claims remain traceable to the original frozen evidence release;
- future journal DOI, if any, is added as the published relation in engrXiv and repository metadata.
