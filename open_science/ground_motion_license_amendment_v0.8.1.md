# Ground-motion license amendment — v0.8.1

This amendment was made **before OSF registration submission** and **before any confirmatory simulation result was inspected**.

The v0.8.0 design targeted 40 ESM earthquake events with four horizontal records per event. A completed pre-registration source audit then exposed a licensing constraint that was not safely resolvable by inference: source-reported ESM waveform licenses included explicit Creative Commons licenses as well as `D (network default license)` and `U (unknown license)` states.

For the confirmatory preregistration, SeismicShield-RL therefore adopts a stricter rule: only waveforms whose source-reported `DATA_LICENSE` begins with `CC-BY3_0-IT` or `CC-BY4_0` are eligible. `D` and `U` are excluded without reinterpretation, license substitution, or network-level inference.

The already-frozen 63-event salted ESM queue is preserved. Event ordering and the v0.8.0 salt are not changed after the license audit. An event is retained only if its exhaustive inventory contains at least four explicit-CC records. The first 34 such events in the pre-existing salted event order form the v0.8.1 source-side selection. Within each retained event, the first four explicit-CC records are selected by the pre-existing salted record-hash order.

This yields **34 events × 4 records = 136 records**. The preregistered partition counts become:

- training: 13 events / 52 records;
- validation: 5 events / 20 records;
- pilot: 4 events / 16 records;
- confirmatory: 12 events / 48 records.

The confirmatory event count remains 12. Physical eligibility thresholds, structural families, algorithm seeds, optimization budgets, primary estimands, and the inferential plan are unchanged from v0.8.0.

This amendment does not authorize confirmatory execution. The confirmatory gate remains blocked until the public OSF registration persistent identifier is recorded according to the existing gate contract.
