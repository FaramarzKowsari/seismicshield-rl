# Proposed model — SeismicShield-MAPPO

## Design principle

The proposed model is not a single opaque controller. It is a hierarchical research design that separates structural representation, decentralized story decisions, centralized value estimation, multi-objective conditioning and robustness.

## Task A: offline co-design

### Agents

One agent represents each story. For story *i*, the discrete action is:

- number of dampers `n_i ∈ {0, …, Nmax}`
- slip-force level `F_i ∈ predefined engineering grid`

A future continuous-action variant may predict normalized capacity and use a projection layer for constructability constraints.

### Observation

Local story features:

- normalized story index
- mass and lateral stiffness descriptors
- undamped local response descriptors from the training scenario set
- local damper-budget state

Global context available during centralized training:

- building height / modal summary
- objective-weight vector
- earthquake/structural-domain embedding that contains no test-set identity leakage
- remaining global retrofit budget where constrained optimization is used

### Actor

Parameter-shared story actor by default. A story-index embedding allows one network to operate across different floor positions and, later, different building heights.

### Critic

Centralized critic consumes the joint/global state and joint action. This is the primary MAPPO-style candidate. IPPO with the same actor capacity and environment contract is a required ablation.

### Reward / objective

Training may use a scalarized objective

`J = wc*C + wd*(MIDR/MIDR0) + wa*(PFA/PFA0) + penalties`

but the scientific output is the unscalarized vector `(C, MIDR, PFA)`. Multiple weight vectors or a weight-conditioned policy can approximate a Pareto set.

### Constraint handling

- per-story damper cap
- total damper/capacity budget
- invalid design projection or explicit penalty
- solver non-convergence penalty with separate failure reporting

## Robust extension

For each candidate design, evaluation can aggregate multiple earthquake/structure worlds. Risk-sensitive variants optimize mean performance plus CVaR/tail loss rather than only the mean.

## Task B: adaptive semi-active control

This is a separate benchmark, not a hidden extension of Task A. Agents act at structural time steps and modify admissible slip-force commands. It requires:

- causal observations only
- actuator-rate and force bounds
- latency/noise ablations
- fixed passive and rule-based controllers
- separate compute and sample budgets

## Required ablations

- MAPPO vs IPPO
- parameter sharing on/off
- centralized critic on/off
- global context on/off
- domain randomization on/off
- cost/PFA reward terms on/off
- fixed damper count vs jointly learned count
- scalarized policy vs weight-conditioned policy

## Success criteria

The model is not considered successful because training reward increases. It must improve prespecified held-out metrics or Pareto hypervolume against equal-budget baselines with uncertainty intervals, while maintaining acceptable solver-failure rates.
