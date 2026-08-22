# Confirmatory runtime runbook — v0.8.2

Scientific source tag: `confirmatory-v0.8.2-final`  
OSF preregistration: `10.17605/OSF.IO/64DTX`

## Current boundary

The immutable confirmatory gate is open, but no confirmatory structural-response outcome has yet been generated or inspected. The first runtime action is deliberately restricted to a **pilot-only preflight**. It must not train, tune, select, or evaluate any method on the confirmatory partition.

The public manifest contains 136 explicit-CC ESM record identities and exact raw/processed SHA-256 evidence. Waveform bytes are not committed to this repository. Runtime hydration may temporarily reconstruct those private files from the recorded ESM access references, but the files remain under `data/private/` and must never be uploaded as GitHub artifacts.

## Immutable-source rule

Scientific execution must use the exact commit resolved by:

```text
confirmatory-v0.8.2-final
```

Before any runtime data operation, the runner must verify:

1. the checked-out commit equals the annotated tag target;
2. `python scripts/check_confirmatory_gate.py` returns `PASS`;
3. the ground-motion manifest SHA-256 is `0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b`;
4. all 136 reconstructed processed records match the `processed_sha256` values frozen in the manifest.

A processed waveform mismatch is a hard stop. No substitute record, resampling, repair, silent fallback, or post-hoc data replacement is allowed.

## Live-source raw-byte drift

The historical `raw_sha256` records the exact source-member bytes observed when the manifest was frozen. A public upstream service can later alter non-numerical ASCII header bytes while serving the same acceleration series. Such upstream byte drift is **not** silently treated as an exact raw match.

If the live `raw_sha256` differs from the historical value, hydration may proceed only when all of the following hold:

- `EVENT_ID`, stream, network, station and location still match the frozen manifest;
- source units, `NDATA`, sampling interval and usable duration match the frozen values;
- parsed PGA and source-header PGA remain consistent with the frozen evidence;
- the explicit accepted CC license family is unchanged;
- deterministic cm/s² → m/s² normalization reproduces the frozen `processed_sha256` exactly.

The expected and observed raw SHA-256 values are then recorded as provenance drift in the non-waveform hydration audit. If any identity, numerical-header, license, sample, timing or processed-hash check fails, hydration remains `BLOCKED`. This rule does not modify the frozen manifest or scientific source tag.

## Pilot-only runtime preflight

The preflight performs no confirmatory simulation. It uses one frozen `pilot` waveform and the smallest/largest nominal structural fixtures (3 and 20 stories), evaluating no-damper and uniform designs on both Tier-1 and Tier-2 backends.

The preflight records only runtime/integrity evidence:

- whether all 136 frozen processed waveform hashes were reproduced exactly;
- any live-source raw-byte provenance drift that passed the stricter identity/header checks above;
- whether Tier-1 and Tier-2 were available and converged on the pilot fixtures;
- mean wall-clock time per fixture call;
- projected sequential runtime for the preregistered Tier-1/Tier-2 call counts;
- Python/platform/NumPy environment metadata.

It must not emit pilot response vectors, MIDR, PFA, displacement, energy, or any confirmatory-response metric.

## Ephemeral data hydration

`scripts/hydrate_frozen_esm_manifest_v0_8_2.py` is an orchestration utility added after the immutable scientific tag. It is not part of the estimator, optimizer, simulator, objective, selection rule, or statistical analysis. Its numerical output is accepted only if the bytes reproduce the exact `processed_sha256` already frozen at the scientific tag.

The workflow checks out two worktrees:

- `orchestrator/` from current `main`, containing only the transport utility/workflow;
- `frozen/` from `confirmatory-v0.8.2-final`, containing all scientific execution code and contracts.

Only the two JSON audit/preflight files may be uploaded. The hydrated waveform directory is explicitly excluded.

## Stop/go rule after preflight

A full confirmatory execution plan may be launched only when the pilot preflight status is `PASS` and the evidence shows a usable Tier-2 backend. If the preflight is `BLOCKED`, the failure may be corrected only as infrastructure/runtime work. No confirmatory record may be simulated to diagnose or tune the failure.

The next phase after a passing preflight is to freeze an execution-shard ledger that deterministically enumerates training, validation, checkpoint-selection and Tier-2 confirmatory workloads without changing any preregistered budget, seed, record partition, objective or tie-break rule.
