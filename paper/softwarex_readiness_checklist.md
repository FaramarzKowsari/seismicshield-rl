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
- [ ] Merge the reviewed `softwarex-submission-prep` branch after CI passes.
- [ ] Create GitHub release/tag `v0.8.3-softwarex`.
- [ ] Allow Zenodo to archive that release and mint the exact v0.8.3 DOI.
- [ ] Insert the new exact DOI in manuscript metadata C3 and final submission files.
- [ ] Update citation metadata if needed after Zenodo minting, without changing the frozen v0.8.2 scientific-source identity.

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
- [x] Generative-AI declaration drafted for current Elsevier policy.
- [ ] Confirm author affiliation exactly as it should appear in publication.
- [ ] Confirm corresponding-author email for title page and C9.
- [ ] Transfer the final text into the current official SoftwareX Word template without changing template formatting.

## C. Highlights and figures

- [x] Separate highlights file prepared.
- [x] Four highlights supplied; each is below the 85-character maximum.
- [ ] Produce Figure 1 as a clean architecture schematic.
- [ ] Verify every label and arrow against repository architecture.
- [ ] Embed Figure 1 directly in the Word manuscript.
- [ ] Keep total figure count at or below six.
- [ ] If any generative-AI image assistance is used, include the disclosure required by Elsevier in the figure caption; do not use generative AI for a graphical abstract.

## D. Illustrative example and software validation

- [x] Add `scripts/run_softwarex_example.py`.
- [x] Example uses only the public synthetic fixture.
- [x] Example marks itself `software-validation-only`.
- [x] Example records `confirmatory_data_used=false`.
- [x] Example records `paper_level_efficacy_claim=false`.
- [x] Example hashes inputs and output artifacts.
- [x] Automated test added for the evidence boundary.
- [ ] Confirm CI passes on the submission branch / pull request.
- [ ] Run the example from a clean environment after merge and preserve the output used for the submission package.

## E. Literature and claims

- [x] Related friction-damper optimization paper included.
- [x] Deep-RL reproducibility reference included.
- [x] OpenSeesPy SoftwareX paper included.
- [x] PettingZoo reference included.
- [x] NSGA-II and pymoo references included.
- [x] Preregistration and computational reproducibility references included.
- [x] Existing scientific claims checked against the repository evidence ledger and preflight artifact.
- [ ] Final reference cross-check after Word-template conversion.

## F. Submission package

- [x] Cover-letter draft prepared.
- [x] Submission metadata file prepared.
- [x] Proposed CRediT roles prepared for author verification.
- [x] Data/code availability statement prepared.
- [x] Funding, competing-interest, and AI declarations prepared.
- [ ] Final `.docx` in official SoftwareX template.
- [ ] Separate editable highlights file.
- [ ] Final figure source and embedded manuscript figure.
- [ ] Exact v0.8.3 Zenodo DOI.
- [ ] Complete Elsevier declarations tool at submission.
- [ ] Enter verified author affiliation, email, and contact details in Editorial Manager.

## Submission gate

Do **not** submit until all unchecked items in sections A, B, C, D, and F that are required for first submission are resolved. In particular, do not submit with a mutable code-version identity or with the C3 DOI placeholder still present.
