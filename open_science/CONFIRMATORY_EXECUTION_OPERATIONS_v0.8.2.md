# Confirmatory execution operations — v0.8.2

Scientific source: `confirmatory-v0.8.2-final` (`cecd3b6c27b5deb6cb6be7ddc478cfc407a45644`)  
OSF registration: `10.17605/OSF.IO/64DTX`

## Safety boundary

The passing pilot preflight establishes runtime readiness only. It does not authorize an orchestration layer to expose confirmatory waveforms to training code or to start Tier-2 confirmatory simulations before selection artifacts are frozen.

The execution sequence is therefore split into two irreversible stages.

### Stage A — selection only

1. Generate the reviewed execution ledger and require the authoritative immutable gate to pass.
2. Prepare a local workspace with `scripts/prepare_confirmatory_workspace_v0_8_2.py`.
3. Hydrate **training and validation only**. The allowed partitions are 52 training + 20 validation records. Pilot and confirmatory partitions remain unavailable to selection workers.
4. Compute the 16 training-only undamped feature aggregates.
5. Execute the 384 nonpolicy `method × seed × structural-state` train+validate shards. Each shard is 3,200 training calls plus 640 validation calls and keeps the frozen candidate archive in the same process.
6. Execute the 24 learned `method × seed` train+validate shards. Each shard is 51,200 training calls plus 3,200 checkpoint-validation calls. Validation stays inline at the ten frozen checkpoints exactly as implemented at the immutable source tag.
7. Preserve selected-design/checkpoint artifacts, per-call audit logs, environment metadata and SHA-256 evidence.
8. Freeze a complete selection manifest before any confirmatory data is hydrated.

The current workspace preparer stops at step 2. It contains no command capable of starting a shard or unlocking confirmatory data.

## Restart discipline

The immutable optimizer implementations do not expose a complete mid-shard serialization contract for RNG, optimizer state, population/archive state and learned-policy optimizer state. Orchestration must not invent one after preregistration.

- An infrastructure-interrupted Stage-A shard restarts from call zero with the same method, seed, state and frozen inputs.
- A partial attempt is retained separately for audit and is never concatenated with a replacement attempt.
- A solver/numerical failure returned by the simulator is a scientific call outcome, consumes its frozen call, and is not treated as an infrastructure retry.
- A completed shard is immutable; replacement requires an explicit deviation record rather than silent overwrite.

This makes restart semantics conservative but reproducible.

## Stage B — confirmatory Tier-2

Stage B is intentionally **not authorized by the current workspace tooling**. A future authorization change may be considered only after every Stage-A selection artifact has been completed and hash-frozen.

Before Stage B can begin, the operations layer must prove all of the following:

- the immutable scientific tag and authoritative gate still pass;
- all 424 Stage-A shards are complete;
- selected designs/checkpoints are complete and SHA-256 frozen;
- no selection artifact was produced using pilot or confirmatory records;
- the confirmatory manifest is still the frozen 48-record partition across 16 structural states;
- the execution ledger is unchanged;
- an environment snapshot and OpenSeesPy runtime check are recorded.

Only after that boundary may the 48 seeded-method Tier-2 shards and 3 deterministic-support Tier-2 shards become executable.

For Tier-2, a solver/numerical failure is retained as the preregistered finite failure outcome and must not be rerun. An infrastructure failure may be rerun only for the exact same world, design and seed with an explicit audit linkage to the failed infrastructure attempt.

## Compute placement

The pilot measured about 1.33 seconds per Tier-1 fixture call and 1.99 seconds per Tier-2 fixture call on the hosted Azure runner. Those measurements are capacity-planning evidence, not performance evidence. A learned train+validate shard contains 54,400 calls and is therefore a long-running atomic job. Use a persistent local or self-hosted execution environment for these shards rather than breaking the frozen training loop merely to fit a short-lived hosted runner.

Waveform bytes remain private under `data/private/` and are never GitHub artifacts. Runtime results and scientific evidence are handled separately from source code and must be hash-audited before any publication claim is updated.