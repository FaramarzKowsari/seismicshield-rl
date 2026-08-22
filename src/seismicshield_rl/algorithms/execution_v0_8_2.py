from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from seismicshield_rl.algorithms.confirmatory import (
    BudgetLedger,
    DesignContext,
    DesignSpace,
    ObjectiveRecord,
    _crowding_distance,
    _nondominated_sort,
    _rank_and_crowding,
    _survival_indices,
)
from seismicshield_rl.execution_v0_8_2 import ValidationPanel, sha256_balanced_order
from seismicshield_rl.physics.base import DamperDesign


@dataclass
class CandidateRunResult:
    method: str
    seed: int
    evaluations: int
    designs: list[DamperDesign]
    records: list[ObjectiveRecord]


@dataclass(frozen=True)
class CandidateSelection:
    method: str
    seed: int
    structural_state_id: str
    design: DamperDesign
    validation_record: ObjectiveRecord
    validation_calls: int
    pool_size: int


@dataclass(frozen=True)
class PolicyCheckpoint:
    method: str
    seed: int
    training_call: int
    validation_scalar: float
    validation_calls: int
    max_dampers_per_story: int
    slip_force_levels_n: np.ndarray
    hidden_units: tuple[int, int]
    actor_state: dict[str, np.ndarray]

    def __post_init__(self) -> None:
        levels = np.asarray(self.slip_force_levels_n, dtype=float)
        if levels.ndim != 1 or levels.size == 0:
            raise ValueError("checkpoint slip-force grid must be non-empty")
        state = {key: np.asarray(value, dtype=np.float32).copy() for key, value in self.actor_state.items()}
        object.__setattr__(self, "slip_force_levels_n", levels)
        object.__setattr__(self, "actor_state", state)

    def _global_summary(self, local_features: np.ndarray) -> np.ndarray:
        local = np.asarray(local_features, dtype=np.float32)
        return np.concatenate(
            [
                local.mean(axis=0),
                local.std(axis=0),
                local.max(axis=0),
                np.asarray([local.shape[0] / 20.0], dtype=np.float32),
            ]
        ).astype(np.float32)

    def design(self, local_features: np.ndarray) -> DamperDesign:
        local = np.asarray(local_features, dtype=np.float32)
        if local.ndim != 2 or local.shape[0] == 0:
            raise ValueError("policy local features must be [stories, features]")
        if self.method == "ppo":
            global_summary = self._global_summary(local)
            global_rows = np.repeat(global_summary[None, :], local.shape[0], axis=0)
            x = np.concatenate([local, global_rows], axis=1)
        elif self.method in {"ippo", "mappo"}:
            x = local
        else:
            raise ValueError(f"unsupported policy method {self.method!r}")
        state = self.actor_state
        h1 = np.tanh(x @ state["backbone.0.weight"].T + state["backbone.0.bias"])
        h2 = np.tanh(h1 @ state["backbone.2.weight"].T + state["backbone.2.bias"])
        count_logits = h2 @ state["count_head.weight"].T + state["count_head.bias"]
        slip_logits = h2 @ state["slip_head.weight"].T + state["slip_head.bias"]
        counts = np.argmax(count_logits, axis=1).astype(int)
        slip_index = np.argmax(slip_logits, axis=1).astype(int)
        return DamperDesign(counts, self.slip_force_levels_n[slip_index].astype(float))


@dataclass(frozen=True)
class PolicyRunResult:
    method: str
    seed: int
    training_evaluations: int
    validation_evaluations: int
    checkpoint: PolicyCheckpoint


def _design_key(design: DamperDesign) -> tuple:
    return tuple(design.counts.astype(int).tolist()) + tuple(
        float(value) for value in design.slip_force_n.tolist()
    )


def _evaluate(ledger: BudgetLedger, oracle, design: DamperDesign) -> ObjectiveRecord:
    ledger.charge()
    record = oracle(design)
    if not isinstance(record, ObjectiveRecord):
        raise TypeError("evaluation oracle must return ObjectiveRecord")
    return record


def run_random_candidates(
    space: DesignSpace,
    oracle,
    *,
    budget: int,
    seed: int,
    retain: int = 256,
) -> CandidateRunResult:
    if budget <= 0 or retain <= 0:
        raise ValueError("budget and retain must be positive")
    rng = np.random.default_rng(seed)
    ledger = BudgetLedger(int(budget))
    best: dict[tuple, tuple[DamperDesign, ObjectiveRecord]] = {}
    while ledger.remaining:
        design = space.decode(space.random_genome(rng))
        record = _evaluate(ledger, oracle, design)
        key = _design_key(design)
        previous = best.get(key)
        if previous is None or record.scalar < previous[1].scalar:
            best[key] = (design, record)
    ordered = sorted(best.values(), key=lambda item: (item[1].scalar, _design_key(item[0])))[:retain]
    return CandidateRunResult(
        "random_search", seed, ledger.completed,
        [item[0] for item in ordered], [item[1] for item in ordered]
    )


def _mutate_genome(space: DesignSpace, genome: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    child = np.asarray(genome, dtype=int).copy()
    probability = 1.0 / space.n_genes
    for gene in range(space.n_genes):
        if rng.random() >= probability:
            continue
        upper = space.max_dampers_per_story if gene % 2 == 0 else space.slip_force_levels_n.size - 1
        if upper <= 0:
            child[gene] = 0
            continue
        proposal = int(rng.integers(0, upper + 1))
        if proposal == child[gene]:
            proposal = (proposal + 1 + int(rng.integers(0, upper))) % (upper + 1)
        child[gene] = proposal
    return child


def run_scalar_ga_candidates(
    space: DesignSpace,
    oracle,
    *,
    budget: int,
    seed: int,
    population_size: int = 256,
    crossover_probability: float = 0.90,
) -> CandidateRunResult:
    if budget <= 1 or population_size <= 1:
        raise ValueError("budget and population_size must exceed one")
    rng = np.random.default_rng(seed)
    ledger = BudgetLedger(int(budget))
    population_size = min(int(population_size), int(budget))
    population = np.stack([space.random_genome(rng) for _ in range(population_size)])
    records = [_evaluate(ledger, oracle, space.decode(genome)) for genome in population]

    while ledger.remaining:
        scalar = np.asarray([record.scalar for record in records], dtype=float)

        def tournament() -> int:
            left, right = rng.integers(0, population.shape[0], size=2).tolist()
            if scalar[left] != scalar[right]:
                return int(left if scalar[left] < scalar[right] else right)
            return int(left if tuple(population[left].tolist()) <= tuple(population[right].tolist()) else right)

        target = min(population_size, ledger.remaining)
        children: list[np.ndarray] = []
        while len(children) < target:
            first = population[tournament()].copy()
            second = population[tournament()].copy()
            if rng.random() < crossover_probability:
                mask = rng.random(space.n_genes) < 0.5
                child = np.where(mask, first, second)
            else:
                child = first
            children.append(_mutate_genome(space, child, rng))
        child_array = np.stack(children)
        child_records = [_evaluate(ledger, oracle, space.decode(genome)) for genome in child_array]
        combined = np.vstack([population, child_array])
        combined_records = records + child_records
        order = sorted(
            range(len(combined_records)),
            key=lambda index: (combined_records[index].scalar, tuple(combined[index].tolist())),
        )[:population_size]
        population = combined[np.asarray(order, dtype=int)]
        records = [combined_records[index] for index in order]

    return CandidateRunResult(
        "scalar_ga",
        seed,
        ledger.completed,
        [space.decode(genome) for genome in population],
        records,
    )


def run_nsga2_candidates(
    space: DesignSpace,
    oracle,
    *,
    budget: int,
    seed: int,
    population_size: int = 256,
    crossover_probability: float = 0.90,
) -> CandidateRunResult:
    if budget <= 1 or population_size <= 1:
        raise ValueError("budget and population_size must exceed one")
    rng = np.random.default_rng(seed)
    ledger = BudgetLedger(int(budget))
    population_size = min(int(population_size), int(budget))
    population = np.stack([space.random_genome(rng) for _ in range(population_size)])
    records = [_evaluate(ledger, oracle, space.decode(genome)) for genome in population]

    while ledger.remaining:
        vectors = np.stack([record.vector for record in records])
        rank, crowding, _ = _rank_and_crowding(vectors)

        def tournament() -> int:
            left, right = rng.integers(0, population.shape[0], size=2).tolist()
            if rank[left] != rank[right]:
                return int(left if rank[left] < rank[right] else right)
            if crowding[left] != crowding[right]:
                return int(left if crowding[left] > crowding[right] else right)
            return int(left if rng.random() < 0.5 else right)

        target = min(population_size, ledger.remaining)
        children: list[np.ndarray] = []
        while len(children) < target:
            first = population[tournament()].copy()
            second = population[tournament()].copy()
            if rng.random() < crossover_probability:
                mask = rng.random(space.n_genes) < 0.5
                child = np.where(mask, first, second)
            else:
                child = first
            children.append(_mutate_genome(space, child, rng))
        child_array = np.stack(children)
        child_records = [_evaluate(ledger, oracle, space.decode(genome)) for genome in child_array]
        combined = np.vstack([population, child_array])
        combined_records = records + child_records
        vectors = np.stack([record.vector for record in combined_records])
        keep = _survival_indices(vectors, population_size)
        population = combined[keep]
        records = [combined_records[index] for index in keep.tolist()]

    return CandidateRunResult(
        "nsga2", seed, ledger.completed,
        [space.decode(genome) for genome in population], records
    )


def _candidate_pool(result: CandidateRunResult, limit: int) -> list[DamperDesign]:
    if limit <= 0:
        raise ValueError("candidate-pool limit must be positive")
    indices = list(range(len(result.designs)))
    if result.method == "nsga2":
        vectors = np.stack([record.vector for record in result.records])
        rank, crowding, _ = _rank_and_crowding(vectors)
        indices.sort(
            key=lambda index: (
                int(rank[index]),
                -float(crowding[index]),
                float(result.records[index].scalar),
                _design_key(result.designs[index]),
            )
        )
    else:
        indices.sort(
            key=lambda index: (
                float(result.records[index].scalar),
                _design_key(result.designs[index]),
            )
        )
    selected: list[DamperDesign] = []
    seen: set[tuple] = set()
    for index in indices:
        design = result.designs[index]
        key = _design_key(design)
        if key in seen:
            continue
        seen.add(key)
        selected.append(design)
        if len(selected) >= limit:
            break
    return selected


def select_candidate_on_validation(
    result: CandidateRunResult,
    panel: ValidationPanel,
    *,
    pool_size: int = 32,
) -> CandidateSelection:
    pool = _candidate_pool(result, pool_size)
    if not pool:
        raise RuntimeError("candidate optimizer produced no validation candidates")
    scored: list[tuple[DamperDesign, ObjectiveRecord]] = []
    for design in pool:
        scored.append((design, panel.mean_record(design)))
    scored.sort(
        key=lambda item: (
            float(item[1].scalar),
            float(item[1].vector[1]),
            float(item[1].vector[2]),
            float(item[1].vector[0]),
            _design_key(item[0]),
        )
    )
    design, record = scored[0]
    return CandidateSelection(
        method=result.method,
        seed=result.seed,
        structural_state_id=panel.structural_state_id,
        design=design,
        validation_record=record,
        validation_calls=len(pool) * len(panel.evaluators),
        pool_size=len(pool),
    )


def _global_summary(local_features: np.ndarray) -> np.ndarray:
    local = np.asarray(local_features, dtype=np.float32)
    return np.concatenate(
        [
            local.mean(axis=0),
            local.std(axis=0),
            local.max(axis=0),
            np.asarray([local.shape[0] / 20.0], dtype=np.float32),
        ]
    ).astype(np.float32)


def _capture_actor_state(actor) -> dict[str, np.ndarray]:
    return {
        key: value.detach().cpu().numpy().astype(np.float32, copy=True)
        for key, value in actor.state_dict().items()
    }


def _checkpoint_from_actor(
    *, method: str, seed: int, training_call: int, validation_scalar: float,
    validation_calls: int, space: DesignSpace, hidden_units: tuple[int, int], actor
) -> PolicyCheckpoint:
    return PolicyCheckpoint(
        method=method,
        seed=int(seed),
        training_call=int(training_call),
        validation_scalar=float(validation_scalar),
        validation_calls=int(validation_calls),
        max_dampers_per_story=int(space.max_dampers_per_story),
        slip_force_levels_n=space.slip_force_levels_n.copy(),
        hidden_units=tuple(int(value) for value in hidden_units),
        actor_state=_capture_actor_state(actor),
    )


def _validation_score(
    checkpoint: PolicyCheckpoint,
    panels: list[ValidationPanel],
) -> tuple[float, int]:
    scalars: list[float] = []
    calls = 0
    for panel in panels:
        design = checkpoint.design(panel.local_features)
        evaluations = panel.evaluate_design(design)
        calls += len(evaluations)
        scalars.extend(float(item.scalar) for item in evaluations)
    if not scalars:
        raise RuntimeError("validation checkpoint has no validation evaluations")
    return float(np.mean(scalars)), calls


def train_validation_selected_policy(
    method: str,
    space: DesignSpace,
    contexts: list[DesignContext],
    validation_panels: list[ValidationPanel],
    *,
    budget: int,
    seed: int,
    checkpoint_calls: Iterable[int],
    batch_design_evaluations: int = 256,
    update_epochs: int = 4,
    learning_rate: float = 3.0e-4,
    clip_epsilon: float = 0.20,
    value_loss_coefficient: float = 0.50,
    entropy_coefficient: float = 0.01,
    max_grad_norm: float = 0.50,
    hidden_units: tuple[int, int] = (128, 128),
) -> PolicyRunResult:
    """Train variable-height PPO/IPPO/MAPPO and select only on validation.

    Contexts are visited in balanced SHA-256 cycles, so a 51,200-call budget over
    16 structural states gives exactly 3,200 calls per state. The actor is shared
    across story counts. Validation is greedy and never exposes confirmatory input.
    """

    if method not in {"ppo", "ippo", "mappo"}:
        raise ValueError("method must be ppo, ippo or mappo")
    if budget <= 0 or batch_design_evaluations <= 0 or update_epochs <= 0:
        raise ValueError("invalid policy training settings")
    if not contexts:
        raise ValueError("at least one training context is required")
    contexts = sorted(contexts, key=lambda item: item.context_id)
    if len({item.context_id for item in contexts}) != len(contexts):
        raise ValueError("training context IDs must be unique")
    feature_dim = int(contexts[0].local_features.shape[1])
    if any(item.local_features.shape[1] != feature_dim for item in contexts):
        raise ValueError("all policy contexts must have the same feature width")
    if budget % len(contexts) != 0:
        raise ValueError("policy budget must divide evenly across structural contexts")
    checkpoints = sorted({int(value) for value in checkpoint_calls})
    if not checkpoints or checkpoints[-1] != int(budget):
        raise ValueError("checkpoint schedule must include the final training budget")
    if any(value <= 0 or value > budget for value in checkpoints):
        raise ValueError("checkpoint call outside training budget")
    if any(value % batch_design_evaluations != 0 for value in checkpoints):
        raise ValueError("checkpoint calls must align with policy batch size")

    try:
        import torch
        from torch import nn
        from torch.distributions import Categorical
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyTorch is required for policy training") from exc

    torch.manual_seed(int(seed))
    torch.use_deterministic_algorithms(True)
    device = torch.device("cpu")
    global_dim = 3 * feature_dim + 1
    actor_dim = feature_dim + global_dim if method == "ppo" else feature_dim
    critic_dim = feature_dim if method == "ippo" else global_dim

    class Actor(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(actor_dim, hidden_units[0]), nn.Tanh(),
                nn.Linear(hidden_units[0], hidden_units[1]), nn.Tanh(),
            )
            self.count_head = nn.Linear(hidden_units[1], space.max_dampers_per_story + 1)
            self.slip_head = nn.Linear(hidden_units[1], space.slip_force_levels_n.size)

        def forward(self, x):
            hidden = self.backbone(x)
            return self.count_head(hidden), self.slip_head(hidden)

    class Critic(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(critic_dim, hidden_units[0]), nn.Tanh(),
                nn.Linear(hidden_units[0], hidden_units[1]), nn.Tanh(),
                nn.Linear(hidden_units[1], 1),
            )

        def forward(self, x):
            return self.net(x).squeeze(-1)

    actor = Actor().to(device)
    critic = Critic().to(device)
    optimizer = torch.optim.Adam(
        list(actor.parameters()) + list(critic.parameters()), lr=float(learning_rate)
    )
    ledger = BudgetLedger(int(budget))
    context_map = {item.context_id: item for item in contexts}
    context_ids = sorted(context_map)
    best_checkpoint: PolicyCheckpoint | None = None
    total_validation_calls = 0

    def next_context(call_index: int) -> DesignContext:
        cycle, position = divmod(call_index, len(context_ids))
        order = sha256_balanced_order(
            context_ids,
            seed=seed,
            namespace="training-context",
            cycle_index=cycle,
        )
        return context_map[order[position]]

    while ledger.remaining:
        batch_size = min(int(batch_design_evaluations), ledger.remaining)
        trajectories: list[dict] = []
        for _ in range(batch_size):
            context = next_context(ledger.completed)
            local_np = context.local_features
            global_np = _global_summary(local_np)
            local = torch.as_tensor(local_np, dtype=torch.float32, device=device)
            global_tensor = torch.as_tensor(global_np, dtype=torch.float32, device=device)
            if method == "ppo":
                actor_input = torch.cat(
                    [local, global_tensor.unsqueeze(0).repeat(local.shape[0], 1)], dim=1
                )
            else:
                actor_input = local
            with torch.no_grad():
                count_logits, slip_logits = actor(actor_input)
                count_dist = Categorical(logits=count_logits)
                slip_dist = Categorical(logits=slip_logits)
                count_actions = count_dist.sample()
                slip_actions = slip_dist.sample()
                old_logp = count_dist.log_prob(count_actions) + slip_dist.log_prob(slip_actions)
                if method == "ippo":
                    old_value = critic(local)
                else:
                    old_value = critic(global_tensor.unsqueeze(0)).squeeze(0)
            design = DamperDesign(
                count_actions.cpu().numpy().astype(int),
                space.slip_force_levels_n[slip_actions.cpu().numpy().astype(int)].astype(float),
            )
            ledger.charge()
            record = context.evaluate(design)
            if not isinstance(record, ObjectiveRecord):
                raise TypeError("policy context oracle must return ObjectiveRecord")
            trajectories.append(
                {
                    "local": local_np.copy(), "global": global_np.copy(),
                    "count": count_actions.cpu().numpy().astype(np.int64),
                    "slip": slip_actions.cpu().numpy().astype(np.int64),
                    "old_logp": old_logp.cpu().numpy().astype(np.float64),
                    "old_value": old_value.cpu().numpy().copy(),
                    "reward": -float(record.scalar),
                }
            )

        if method == "ippo":
            raw_advantages = np.concatenate(
                [
                    np.full(item["local"].shape[0], item["reward"], dtype=float)
                    - np.asarray(item["old_value"], dtype=float)
                    for item in trajectories
                ]
            )
        else:
            raw_advantages = np.asarray(
                [item["reward"] - float(item["old_value"]) for item in trajectories], dtype=float
            )
        mean_advantage = float(raw_advantages.mean())
        std_advantage = max(float(raw_advantages.std()), 1e-8)

        for _ in range(int(update_epochs)):
            actor_terms = []
            value_terms = []
            entropy_terms = []
            agent_offset = 0
            for trajectory_index, item in enumerate(trajectories):
                local = torch.as_tensor(item["local"], dtype=torch.float32, device=device)
                global_tensor = torch.as_tensor(item["global"], dtype=torch.float32, device=device)
                if method == "ppo":
                    actor_input = torch.cat(
                        [local, global_tensor.unsqueeze(0).repeat(local.shape[0], 1)], dim=1
                    )
                else:
                    actor_input = local
                count_actions = torch.as_tensor(item["count"], dtype=torch.long, device=device)
                slip_actions = torch.as_tensor(item["slip"], dtype=torch.long, device=device)
                old_logp = torch.as_tensor(item["old_logp"], dtype=torch.float32, device=device)
                count_logits, slip_logits = actor(actor_input)
                count_dist = Categorical(logits=count_logits)
                slip_dist = Categorical(logits=slip_logits)
                current_logp = count_dist.log_prob(count_actions) + slip_dist.log_prob(slip_actions)
                entropy_terms.append((count_dist.entropy() + slip_dist.entropy()).mean())
                if method == "ippo":
                    n_agents = int(local.shape[0])
                    local_adv = raw_advantages[agent_offset: agent_offset + n_agents]
                    agent_offset += n_agents
                    advantage = torch.as_tensor(
                        (local_adv - mean_advantage) / std_advantage,
                        dtype=torch.float32, device=device,
                    )
                    ratio = torch.exp(current_logp - old_logp)
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(-torch.minimum(ratio * advantage, clipped * advantage).mean())
                    predicted = critic(local)
                    target = torch.full_like(predicted, float(item["reward"]))
                    value_terms.append((predicted - target).pow(2).mean())
                elif method == "mappo":
                    advantage = torch.tensor(
                        (raw_advantages[trajectory_index] - mean_advantage) / std_advantage,
                        dtype=torch.float32, device=device,
                    )
                    ratio = torch.exp(current_logp - old_logp)
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(-torch.minimum(ratio * advantage, clipped * advantage).mean())
                    predicted = critic(global_tensor.unsqueeze(0)).squeeze(0)
                    target = torch.tensor(item["reward"], dtype=torch.float32, device=device)
                    value_terms.append((predicted - target).pow(2))
                else:
                    advantage = torch.tensor(
                        (raw_advantages[trajectory_index] - mean_advantage) / std_advantage,
                        dtype=torch.float32, device=device,
                    )
                    ratio = torch.exp(current_logp.sum() - old_logp.sum())
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(-torch.minimum(ratio * advantage, clipped * advantage))
                    predicted = critic(global_tensor.unsqueeze(0)).squeeze(0)
                    target = torch.tensor(item["reward"], dtype=torch.float32, device=device)
                    value_terms.append((predicted - target).pow(2))

            total_loss = (
                torch.stack(actor_terms).mean()
                + float(value_loss_coefficient) * torch.stack(value_terms).mean()
                - float(entropy_coefficient) * torch.stack(entropy_terms).mean()
            )
            optimizer.zero_grad(set_to_none=True)
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(actor.parameters()) + list(critic.parameters()), float(max_grad_norm)
            )
            optimizer.step()

        if ledger.completed in checkpoints:
            provisional = _checkpoint_from_actor(
                method=method, seed=seed, training_call=ledger.completed,
                validation_scalar=float("inf"), validation_calls=0,
                space=space, hidden_units=hidden_units, actor=actor,
            )
            if validation_panels:
                score, calls = _validation_score(provisional, validation_panels)
                total_validation_calls += calls
            else:
                score, calls = 0.0, 0
            checkpoint = _checkpoint_from_actor(
                method=method, seed=seed, training_call=ledger.completed,
                validation_scalar=score, validation_calls=calls,
                space=space, hidden_units=hidden_units, actor=actor,
            )
            if best_checkpoint is None or checkpoint.validation_scalar < best_checkpoint.validation_scalar:
                best_checkpoint = checkpoint

    if best_checkpoint is None:
        raise RuntimeError("policy training produced no frozen checkpoint")
    return PolicyRunResult(
        method=method,
        seed=int(seed),
        training_evaluations=ledger.completed,
        validation_evaluations=total_validation_calls,
        checkpoint=best_checkpoint,
    )
