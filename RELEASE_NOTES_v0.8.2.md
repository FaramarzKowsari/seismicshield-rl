# SeismicShield-RL v0.8.2 — Final Infrastructure Release

This release closes the current SeismicShield-RL project as a **Final Infrastructure Release**.

## Release status

- Reproducible experimental infrastructure: **complete**
- Preregistered protocol: **preserved** at OSF DOI `10.17605/OSF.IO/64DTX`
- Immutable scientific source: **preserved** at `confirmatory-v0.8.2-final`
- Full Stage-A training/selection run: **deferred**
- Confirmatory Tier-2 structural-response run: **not run**
- Confirmatory outcomes inspected: **no**
- Algorithm-superiority claim: **none**

## Completed evidence

The release preserves:

- the frozen 136-record ESM manifest and partitions;
- the 16-state structural-world design;
- frozen objectives, algorithms, budgets, seeds, validation rules, and analysis rules;
- the fail-closed confirmatory gate;
- independent processed-waveform hash verification for all 136 records;
- successful pilot runtime checks on four Tier-1 and four Tier-2 fixtures;
- deterministic planning of 475 atomic execution shards;
- a selection-only execution workspace with all 51 confirmatory Tier-2 shards locked;
- CI, tests, evidence ledger, SHA-256 provenance, and open-science contracts.

## Why the full experiment was deferred

The final deterministic plan contains **2,820,160 structural-response calls**. Stage A alone contains **2,780,992 Tier-1 calls**. Runtime preflight measured approximately `1.32904380175 s/call`, projecting about **1,026.68 sequential Tier-1 hours**. The Tier-2 campaign contains **39,168 calls**, with measured preflight throughput projecting approximately **21.64 sequential hours**.

The learned Stage-A shards are scientifically atomic under the frozen implementation. Reducing budgets or splitting those shards merely to satisfy hosted-CI wall-clock limits would change the preregistered execution semantics. Rather than alter the protocol or present a reduced experiment as the registered study, the project is stopped before the large compute campaign.

## Scientific interpretation

This is a research-software and reproducibility-infrastructure release. It **does not** establish that MAPPO, PPO, IPPO, NSGA-II, scalar GA, or random search is superior on the preregistered confirmatory benchmark.

The confirmatory boundary remains uninspected, preserving the possibility of a scientifically clean future continuation if suitable compute becomes available.

## Documentation

- `README.md` — final public project status
- `paper/TECHNICAL_REPORT_FINAL_INFRASTRUCTURE_RELEASE.md` — full closure report
- `paper/EVIDENCE_LEDGER.csv` — verified and blocked claims
- `results/validation/confirmatory_runtime_preflight_v0.8.2.json` — preserved runtime/integrity evidence
- `CITATION.cff` — software citation metadata

## Citation

The OSF DOI `10.17605/OSF.IO/64DTX` identifies the preregistered protocol. Cite this GitHub release (and its Zenodo software DOI, if automatically minted) for the software/infrastructure object.
