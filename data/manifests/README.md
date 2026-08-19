# Ground-motion manifest contract

## Four distinct provenance stages

1. **Event-candidate queue.** `scripts/build_afad_tadas_event_queue.py` reads a
   user-supplied local TADAS Event Search CSV, excludes blank identifiers, and orders
   known event candidates by the frozen event hash. Its CSV and audit metadata default
   to `results/local/afad_tadas/`; neither the source export nor a real generated queue
   belongs in Git.
2. **Station-summary necessary-condition prescreen.**
   `scripts/screen_afad_tadas_station_summaries.py` follows the frozen event queue,
   retrieves local station-summary CSVs through an authenticated headed browser session,
   hashes and validates them, and rejects events that cannot possibly yield four
   threshold-passing horizontal components. Because one station can contribute at most
   HNE and HNN, at least two distinct station summaries must have PGA >= `0.15 g` before
   the event advances. This is only a necessary-condition screen: station-summary PGA
   may be controlled by HNZ or by only one horizontal component.
3. **Raw component staging audit.** `scripts/audit_afad_tadas_raw_zip.py` reads a local
   ZIP without extracting or copying waveform files, audits HNE, HNN, and HNZ component
   provenance against explicitly supplied canonical identifiers, and writes a separate
   local JSON report under `results/local/afad_tadas/raw_audits/`. This stage does not
   create processed hashes and must never write the final manifest.
4. **Final frozen ground-motion manifest.** `ground_motion_manifest.csv` is produced
   only by the later processing and freeze workflow after eligible horizontal records
   have complete raw and processed provenance. Raw staging records are not manifest
   records.

Candidate queues, station-summary screens, and raw audits are provenance/data-selection
infrastructure and are **not confirmatory seismic-performance results**. They do not
unblock the confirmatory gate, establish the final event/record set, or authorize
publication of raw waveforms.

The frozen target is **40 known physical earthquake events and 160 real horizontal
acceleration records**: exactly four retained records per event. Splitting occurs at the
event level; an event may never leak between partitions. The allocation is 18 training
events (72 records), 6 validation events (24), 4 pilot events (16), and 12 confirmatory
events (48). Pilot events are permanently excluded from confirmatory inference because
they may inform feasibility decisions before the confirmatory analysis.

Eligibility requires a known physical event identity, horizontal acceleration, units
that convert deterministically to SI, `dt <= 0.020 s`, usable duration of at least 10 s,
absolute PGA of at least `0.15 g`, and complete provenance. The builder orders events
and records by SHA-256 using the frozen `SeismicShield-RL-v0.8.0-OSF-2026` salt, rather
than inspecting motion outcomes. It fails closed if the exact target cannot be met.

Source licensing and redistribution terms must be honored. The manifest records a URL
or durable access reference and cryptographic hashes; restricted raw data must remain
at its licensed source rather than being republished. Blank, placeholder, invented, or
synthetic earthquake records are forbidden. Synthetic metadata may exist only in
temporary test directories as explicitly labeled software-validation fixtures and must
never be written to this directory as a real manifest.

## AFAD/TADAS identity and raw validation

`AFAD_TADAS` is the exact canonical source string used in both selection hashes. The
canonical `event_id` is the TADAS Event Search/Event Detail identifier, not an ASCII
header `EVENT_ID` when that value is zero, blank, missing, or inconsistent. The header
value remains in `raw_header_event_id`. Component identity is
`{waveform_detail_id}:{stream}` (for example, `327925:HNE`); `HNE` and `HNN` are
horizontal, while `HNZ` is vertical and ineligible. The manifest also retains the
waveform detail ID, stream, raw filename, `NDATA`, duration derivation, original
component PGA in cm/s², UTC event time, and both raw and processed SHA-256 hashes.

A trustworthy explicit usable duration is preserved. If it is absent, duration may
only be computed as `(NDATA - 1) * SAMPLING_INTERVAL_S` when `NDATA >= 2`, the interval
is finite and positive, and the parsed sample count equals `NDATA`; otherwise processing
fails closed. Thus `NDATA = 10501` and `SAMPLING_INTERVAL_S = 0.01` produce
`usable_duration_s = 105.0 s`. This is a provenance/software-format validation example,
not confirmatory evidence. T90 is never substituted for usable duration.

For each raw component, `abs(max parsed acceleration)` (implemented as the maximum
absolute parsed sample) must agree with `PGA_CM/S^2` within `0.01 cm/s²`; larger
disagreement fails closed for provenance review. Original cm/s² PGA and derived `pga_g`
are retained. Standard gravity is exactly `g0 = 9.80665 m/s²`, so `0.15 g = 147.09975
cm/s²`. Station summaries are not final component-eligibility evidence.

The exact `DATA_LICENSE` text is retained. The real literal `U (unknown license)` is not
a placeholder identity and does not trigger the generic placeholder filter, but it sets
`raw_redistribution_allowed` to false. No permissive AFAD/TADAS license allowlist is
currently frozen, so blank, unknown, unrecognized, and restrictive license states all
fail closed to false; public metadata, hashes, acquisition instructions, provenance,
and processing code remain publishable, but automatic public redistribution of waveform
bytes is disabled. Canonical time comes only from source event metadata or the raw UTC
event header, is retained machine-readably in `event_time_utc`, and never comes from
browser-local table rendering. Validation parses a real ISO-8601 instant and accepts
only explicit UTC (`Z` or `+00:00`), rather than trusting a string suffix.
