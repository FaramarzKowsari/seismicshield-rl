# SeismicShield-RL v0.8.3 — SoftwareX Submission Packaging

## Scope

Version 0.8.3 is a publication-packaging release prepared for a SoftwareX Original Software Publication submission.

It **does not change the immutable scientific implementation** frozen at:

- tag: `confirmatory-v0.8.2-final`
- commit: `cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`

It **does not execute** the deferred Stage-A campaign or the confirmatory Tier-2 campaign, and it makes **no algorithm-superiority claim**.

## Changes relative to the v0.8.2 infrastructure release

- align package/runtime metadata under version `0.8.3` so the publication package has a unique software identity;
- expand package metadata and persistent project links;
- add a public synthetic SoftwareX illustrative-example runner;
- add an automated test that protects the example's evidence boundary;
- add the SoftwareX manuscript, highlights, cover letter, submission metadata, readiness checklist, and Figure 1 specification;
- update `CITATION.cff` to distinguish the software concept DOI, frozen v0.8.2 scientific archive, and the v0.8.3 publication package.

## Evidence boundary

The submission-support example is explicitly `software-validation-only`. It records:

- `confirmatory_data_used = false`
- `paper_level_efficacy_claim = false`

The verified v0.8.2 runtime/integrity preflight remains the source for statements about 136 processed-record hash checks and the four Tier-1 plus four Tier-2 pilot fixtures.

## Planned archival sequence

After the submission-preparation pull request passes CI and is merged:

1. create GitHub tag/release `v0.8.3-softwarex`;
2. allow the existing Zenodo integration to archive the release;
3. obtain the exact version DOI;
4. insert that DOI into the final SoftwareX C3 metadata field and submission files.

The Zenodo concept DOI remains `10.5281/zenodo.22067277`.
