# OSF Simulation Studies freeze crosswalk (v0.8.0)

This crosswalk identifies infrastructure contracts only. It contains no scientific
performance result.

| OSF preregistration concept | Repository file / configuration key | Validation script / test |
|---|---|---|
| Ground-motion split | `confirmatory_freeze_v0.8.0.yaml:ground_motions` | `validate_ground_motion_manifest.py`; `test_event_level_split_and_partition_counts` |
| Seeds | `seed_ledger_v0.8.0.yaml` | confirmatory gate; YAML/config review |
| Tier-1 budget | `budgets.tier_1_completed_design_evaluations_per_stochastic_method_per_seed` | frozen-config digest in confirmatory gate |
| Tier-2 cap | `budgets.maximum_tier_2_openseespy_evaluations` | frozen-config digest in confirmatory gate |
| Objectives | `analysis.primary_normalized_objective_vector` | frozen-config digest in confirmatory gate |
| Normalization | `analysis.primary_normalized_objective_vector` denominators | frozen-config digest in confirmatory gate |
| Pareto reference point | `analysis.pareto_hypervolume_reference_point` | frozen-config digest in confirmatory gate |
| Cost slices | `analysis.normalized_cost_ceilings` | frozen-config digest in confirmatory gate |
| CVaR | `analysis.cvar_alpha` | frozen-config digest in confirmatory gate |
| Bootstrap | `analysis.bootstrap_repetitions`; seed ledger `bootstrap_resampling` | frozen-config and seed-ledger gate checks |
| Permutation / sign flip | `analysis.primary_paired_sign_flip_configurations` | frozen-config digest in confirmatory gate |
| Holm family | `analysis.multiplicity` | frozen-config digest in confirmatory gate |
| Failure vector | `analysis.fixed_failure_vector`; `separate_tunable_failure_penalty_permitted` | frozen-config digest in confirmatory gate |
| Confirmatory gate | `confirmatory_gate_v0.8.0.yaml` | `check_confirmatory_gate.py`; `test_confirmatory_gate_remains_blocked_before_registration` |

