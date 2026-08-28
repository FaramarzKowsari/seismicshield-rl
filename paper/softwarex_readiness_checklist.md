# SoftwareX Readiness Checklist

This checklist tracks the SoftwareX Original Software Publication requirements and the repository-specific tasks still required before submission.

## A. Repository identity and release

- [x] Public GitHub repository available.
- [x] Open-source MIT license present.
- [x] Source code lives under `src/`.
- [x] README and public researcher documentation available.
- [x] Package metadata aligned for the submission branch.
- [x] Runtime package version aligned with `pyproject.toml`.
- [x] New submission version reserved as **v0.8.3** to avoid silently changing archived v0.8.2.
- [x] Reviewed SoftwareX finalization changes merged after CI passed.
- [x] GitHub release/tag `v0.8.3-softwarex` published.
- [x] Zenodo archived the release and minted exact v0.8.3 DOI `10.5281/zenodo.22144346`.
- [x] Exact v0.8.3 DOI inserted in manuscript metadata C3 and submission metadata.
- [x] Citation metadata updated for the v0.8.3 version DOI without changing the frozen v0.8.2 scientific-source identity.

## B. Manuscript compliance

- [x] Article type set to **Original Software Publication**.
- [x] Title follows `Software name: short descriptive title` convention.
- [x] Abstract reduced to approximately 100 words.
- [x] Six keywords supplied.
- [x] Mandatory C1–C9 code metadata table drafted.
- [x] Main text follows the five-part SoftwareX structure: Motivation and significance; Software description; Illustrative examples; Impact; Conclusions.
- [x] Main text is comfortably below the 3000-word maximum.
- [x] Exact limitations stated; no algorithm-superiority claim.
- [x] Frozen scientific source distinguished from v0.8.3 publication packaging.
- [x] Software DOI, OSF preregistration, and repository cited separately.
- [x] Funding statement drafted.
- [x] Competing-interest statement drafted.
- [x] CRediT statement drafted for author verification.
- [x] Generative-AI declaration drafted and aligned with Figure 1 disclosure.
- [x] Author affiliation confirmed as **Independent Researcher**.
- [x] Corresponding-author email confirmed as **faramarzkowsari@gmail.com**.
- [ ] Transfer the final text into the current official SoftwareX Word template without changing template formatting, if the journal requires the official template at initial submission.

## C. Highlights and figures

- [x] Separate highlights file prepared.
- [x] Four highlights supplied; each is below the 85-character maximum.
- [x] Figure 1 produced as a clean publication-grade architecture schematic.
- [x] Figure 1 labels, counts, arrows, fidelity ladder, and fail-closed gate verified against repository architecture.
- [x] Editable vector Figure 1 source stored at `paper/figures/Figure_1_SeismicShield_RL_Architecture.svg`.
- [x] Figure caption contains AI-assistance disclosure and states that no research data were generated or altered.
- [x] Figure 1 embedded in the template-compatible Word manuscript.
- [x] Total figure count remains below the six-figure limit.
- [x] Figure 1 is an explanatory architecture schematic, not a graphical abstract.

## D. Illustrative example and software validation

- [x] Add `scripts/run_softwarex_example.py`.
- [x] Example uses only the public synthetic fixture.
- [x] Example marks itself `software-validation-only`.
- [x] Example records `confirmatory_data_used=false`.
- [x] Example records `paper_level_efficacy_claim=false`.
- [x] Example hashes inputs and output artifacts.
- [x] Automated test added for the evidence boundary.
- [x] CI passed for the SoftwareX manuscript/finalization changes on Python 3.11 and 3.12.
- [ ] Run the example from a clean environment after final DOI metadata sync and preserve the output used for the submission package.

## E. Literature and claims

- [x] Related friction-damper optimization paper included.
- [x] Deep-RL reproducibility reference included.
- [x] OpenSeesPy SoftwareX paper included.
- [x] PettingZoo reference included.
- [x] NSGA-II and pymoo references included.
- [x] Computational reproducibility references included.
- [x] Existing scientific claims checked against the repository evidence ledger and preflight artifact.
- [ ] Final reference cross-check after final Word rendering.

## F. Submission package

- [x] Cover-letter draft prepared.
- [x] Submission metadata file prepared.
- [x] Proposed CRediT roles prepared for author verification.
- [x] Data/code availability statement prepared.
- [x] Funding, competing-interest, and AI declarations prepared.
- [x] Final editable Figure 1 source prepared.
- [x] Template-compatible `.docx` manuscript generated with Figure 1, author affiliation, email, and exact v0.8.3 DOI.
- [ ] Separate editable highlights file for upload.
- [x] Exact v0.8.3 Zenodo DOI: `10.5281/zenodo.22144346`.
- [ ] Complete Elsevier declarations tool at submission.
- [ ] Enter verified author affiliation, email, and contact details in Editorial Manager.

## Submission gate

The DOI, affiliation, and corresponding-author email are resolved. Before clicking **Submit**, complete the remaining submission-system tasks, run the public illustrative example from a clean environment, and perform the final Word/reference check. The scientific source remains `confirmatory-v0.8.2-final` at commit `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`; publication packaging must not be interpreted as confirmatory evidence.
