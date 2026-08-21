# Ground-Motion Source Amendment — v0.8.0

## Status

This amendment is made **before OSF registration submission, before a public preregistration persistent identifier is issued, and before any confirmatory simulation result is inspected**. The confirmatory gate remains blocked.

## Amendment

The primary confirmatory ground-motion source is changed from an AFAD/TADAS-only design to an **ESM-only** design using the Engineering Strong Motion Database (ESM) Dataset Selection service for deterministic source discovery and the ESM Event-Data service for authoritative source-distributed ASCII acceleration records.

The target sample size and all response-analysis rules remain unchanged:

- exactly 40 physical events;
- exactly 4 retained horizontal records per event;
- exactly 160 retained records total;
- event-level partition counts remain 18 train / 6 validation / 4 pilot / 12 confirmatory;
- eligibility thresholds remain `dt <= 0.020 s`, usable duration `>= 10 s`, and `|PGA| >= 0.15 g`;
- standard gravity remains `9.80665 m/s^2`;
- source-member PGA validation tolerance remains `0.01 cm/s^2`;
- the deterministic SHA-256 salt remains `SeismicShield-RL-v0.8.0-OSF-2026`;
- the event- and record-key formulas remain unchanged apart from the canonical source literal now being `ESM`.

## ESM source-native identity and audit contract

- Canonical source literal: `ESM`.
- Canonical event ID: the ESM Event-Data ASCII `EVENT_ID`, required to match the Dataset Selection `event_id` used to retrieve the record.
- Canonical record ID: the exact basename of the source-distributed ESM ASCII member.
- Accelerometric channel families considered: `HN`, `HG`, and `HL`.
- Horizontal orientation is determined from the stream axis suffix (`E`, `N`, `1`, `2`, `X`, or `Y`) and the stream family must match the requested accelerometric family.
- Vertical components are not eligible.
- Source-distributed ASCII acceleration units must be deterministically convertible to SI; validated ESM records use `cm/s^2`.
- Parsed sample count must equal `NDATA` exactly.
- Component PGA is recomputed as the maximum absolute parsed acceleration sample and must agree with the source header within `0.01 cm/s^2`.
- Usable duration is `DURATION_S` when present; otherwise the deterministic fallback is `(NDATA - 1) * SAMPLING_INTERVAL_S` after exact sample-count validation.
- Event time authority is Event-Data ASCII `EVENT_DATE_YYYYMMDD` plus `EVENT_TIME_HHMMSS`.
- Provenance requires source identity plus `DATA_LICENSE` and `DATA_CITATION`.
- Source quality class and source processing type are preserved as metadata but are not post-hoc eligibility filters.
- Raw waveform bytes remain private by default and are not redistributed unless the source license explicitly permits redistribution.

## Why the amendment was made

The source change was motivated by source-access, provenance, and reproducibility considerations discovered during preregistration infrastructure work, not by confirmatory outcome inspection. ESM provides a reproducible machine-readable discovery path and authoritative source-distributed ASCII records with event/station identity, component headers, sample interval, duration, PGA, license, and citation metadata. An ESM-only primary source also removes cross-source deduplication and processing-heterogeneity decisions that would otherwise arise from mixing AFAD/TADAS and ESM in the primary confirmatory dataset.

AFAD/TADAS work completed before this amendment remains documented as source-format/provenance validation and is not silently incorporated into the primary confirmatory 40-event sample.

## Pre-registration requirement

The OSF draft must be amended to match this ESM-only contract before registration submission. This repository amendment does not itself authorize confirmatory runs. The gate remains blocked until the final 160-record manifest and hashes, structural-world manifest and hashes, frozen configuration hash, backend validation, source tag, public OSF registration, and persistent identifier requirements are all satisfied.
