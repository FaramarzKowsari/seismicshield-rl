# Deviations and execution clarifications

## 2026-08-22 — v0.8.2 executable confirmatory clarification

**Timing:** after public OSF registration and after deterministic partition/manifests were materialized, but **before any confirmatory structural-performance outcome was executed or inspected**.

**Public preregistration:** https://doi.org/10.17605/OSF.IO/64DTX

**Parent source freeze:** `confirmatory-v0.8.1-final`

### Why this clarification was required

A pre-execution audit found several implementation-level ambiguities/inconsistencies that could be resolved directly from the already-public preregistration without looking at confirmatory outcomes:

1. The generic repository `DesignEvaluator` normalized MIDR and PFA to an undamped reference response, whereas the OSF registration froze the confirmatory objective vector as `[C, MIDR/0.02, PFA/1.0g]`.
2. The v0.8.1 learned-method smoke implementation returned the best individual design observed during training but did not yet preserve/select a deployable policy checkpoint on the validation partition, despite the registered rule that model selection must use training/validation only.
3. The public proposed model described undamped response descriptors from the **training scenario set**. The preliminary helper could instead construct descriptors from the currently evaluated ground motion. For confirmatory execution this would expose held-out earthquake-specific response information to the policy and create an information asymmetry versus conventional optimizers.
4. The OSF Methods section listed a genetic/evolutionary baseline separately from NSGA-II; the v0.8.1 executable stochastic bundle contained NSGA-II but no separate scalar genetic algorithm.
5. The 51,200-call budget needed an explicit balanced allocation across the 16 frozen structural states so that variable building height/uncertainty did not create an implementation-dependent sampling imbalance.
6. Cost-slice selection and the exact event-level aggregation used before bootstrap/sign-flip inference needed executable rules before any confirmatory response was computed.

### Resolution

`open_science/confirmatory_execution_v0.8.2.yaml` freezes the executable interpretation before confirmatory outcome inspection. It:

- uses the exact OSF objective normalization and frozen failure vector;
- forbids confirmatory earthquake identity, samples, or confirmatory undamped response from policy observations;
- defines one robust retrofit design per structural state and seed, reused across held-out earthquakes;
- builds policy response descriptors only from the 52 training records for the same structural state;
- balances the 51,200 Tier-1 simulator calls exactly across all 16 structural states;
- selects learned checkpoints and non-policy candidates using only the 20-record validation partition;
- restores a scalar GA baseline distinct from NSGA-II;
- fixes discrete cost-slice rules, event aggregation, bootstrap and exact sign-flip semantics.

### Effect on hypotheses and status

The registered hypotheses, 34-event source sample, 13/5/4/12 event partition counts, 136-record manifest, 768 confirmatory worlds, eight primary seeds, 51,200-call stochastic training budget, objective reference point, cost ceilings, 20,000 event-cluster bootstrap repetitions, 4,096 exact sign-flips, Holm correction and alpha=0.05 are unchanged.

This clarification is **not based on effect direction, statistical significance, method ranking, or any confirmatory response**. No confirmatory hypothesis is promoted, removed or rewritten. The purpose is to make the already-registered design executable without leakage or ambiguous post-outcome choices.

Any analysis that departs from this v0.8.2 execution contract after confirmatory outcomes are inspected will be labeled exploratory unless separately justified as an unavoidable infrastructure correction with no outcome-dependent choice.
