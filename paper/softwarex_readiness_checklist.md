# SoftwareX Readiness Checklist

This checklist tracks the SoftwareX Original Software Publication requirements and the repository-specific tasks required before submission.

## A. Repository identity and release

- [x] Public GitHub repository available.
- [x] Open-source MIT license present.
- [x] Source code lives under `src/`.
- [x] README and public researcher documentation available.
- [x] Package metadata aligned for the submission package.
- [x] Runtime package version aligned with `pyproject.toml`.
- [x] Publication package version **v0.8.3** separated from frozen scientific v0.8.2.
- [x] Reviewed SoftwareX finalization changes merged after CI passed.
- [x] GitHub release/tag `v0.8.3-softwarex` published.
- [x] Zenodo exact v0.8.3 DOI minted: `10.5281/zenodo.22144346`.
- [x] Exact v0.8.3 DOI inserted in manuscript/submission metadata.
- [x] Frozen scientific v0.8.2 DOI retained separately: `10.5281/zenodo.22067278`.

## B. Manuscript compliance

- [x] Article type set to **Original Software Publication**.
- [x] Title follows `Software name: short descriptive title` convention.
- [x] Abstract is approximately 100 words.
- [x] Six keywords supplied.
- [x] Mandatory C1–C9 code metadata table prepared.
- [x] Main text follows the five-part SoftwareX structure.
- [x] Main text remains below the 3000-word maximum.
- [x] Exact limitations stated; no algorithm-superiority claim.
- [x] Frozen scientific source distinguished from v0.8.3 publication packaging.
- [x] Software DOI, OSF preregistration, and repository identified separately.
- [x] Funding statement prepared.
- [x] Competing-interest statement prepared.
- [x] CRediT statement prepared.
- [x] Generative-AI declaration prepared and aligned with Figure 1 disclosure.
- [x] Author affiliation confirmed as **Independent Researcher**.
- [x] Corresponding-author email confirmed as **faramarzkowsari@gmail.com**.
- [x] Template-compatible Word manuscript generated and visually QA-checked.
- [ ] Transfer into the current official SoftwareX Word template only if Editorial Manager requires that exact template at initial submission.

## C. Highlights and figures

- [x] Separate editable highlights upload file prepared: `paper/softwarex_highlights.txt`.
- [x] Four highlights supplied; each is below the 85-character maximum.
- [x] Figure 1 produced as a publication-grade architecture schematic.
- [x] Figure 1 labels, counts, fidelity ladder, and fail-closed gate verified against repository architecture.
- [x] Editable vector Figure 1 stored at `paper/figures/Figure_1_SeismicShield_RL_Architecture.svg`.
- [x] Figure caption contains AI-assistance disclosure and states that no research data were generated or altered.
- [x] Figure 1 embedded in the template-compatible Word manuscript.
- [x] Total figure count remains below the six-figure limit.

## D. Illustrative example and software validation

- [x] Public example implemented in `scripts/run_softwarex_example.py`.
- [x] Example uses only the public synthetic fixture.
- [x] Example marks itself `software-validation-only`.
- [x] Example records `confirmatory_data_used=false`.
- [x] Example records `paper_level_efficacy_claim=false`.
- [x] Example hashes inputs and output artifacts.
- [x] Automated test protects the evidence boundary.
- [x] Standard CI passes on Python 3.11 and 3.12.
- [x] Example re-run from a clean GitHub Actions Ubuntu 24.04 / CPython 3.12.14 environment after DOI metadata synchronization.
- [x] Clean run completed successfully with all methods converged.
- [x] Frozen outputs preserved at `results/softwarex_example_submission_v0.8.3/`.
- [x] Clean-run provenance and SHA-256 hashes preserved in `results/softwarex_example_submission_v0.8.3/PROVENANCE.md`.
- [x] GitHub Actions clean-run ID recorded: `33172848644`.

## E. Literature and claims

- [x] Related friction-damper reinforcement-learning paper included.
- [x] Deep-RL reproducibility reference included.
- [x] OpenSeesPy SoftwareX paper included.
- [x] PettingZoo reference included.
- [x] NSGA-II and pymoo references included.
- [x] Computational reproducibility references included.
- [x] Existing scientific claims checked against the repository evidence ledger and preflight artifact.
- [x] Final bibliographic audit completed against publisher/proceedings/DOI metadata on 2026-08-28.
- [x] DOI/title/year/volume/page or article-number fields verified for all DOI-bearing references.

## F. Submission package

- [x] Cover letter finalized with v0.8.3 DOI and clean-run statement.
- [x] Submission metadata prepared.
- [x] CRediT roles prepared.
- [x] Data/code availability statement prepared.
- [x] Funding, competing-interest, and AI declarations prepared.
- [x] Final editable Figure 1 source prepared.
- [x] Template-compatible `.docx` manuscript generated with Figure 1, affiliation, email, and exact v0.8.3 DOI.
- [x] Separate editable highlights file prepared.
- [x] Exact v0.8.3 Zenodo DOI resolved: `10.5281/zenodo.22144346`.
- [x] Clean illustrative-example freeze prepared.
- [ ] Complete Elsevier declarations tool in Editorial Manager.
- [ ] Enter/confirm author and contact details in Editorial Manager.
- [ ] Upload files and inspect the system-generated submission PDF before clicking **Submit**.

## Submission gate

The repository-side, manuscript-side, DOI, authorship-contact, reference-audit, and clean-example requirements are complete. Remaining tasks are portal-only submission actions and, if explicitly required by Editorial Manager, transfer into Elsevier's exact current Word template. The scientific source remains `confirmatory-v0.8.2-final` at commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`; publication packaging and the synthetic illustrative example are not confirmatory efficacy evidence.
