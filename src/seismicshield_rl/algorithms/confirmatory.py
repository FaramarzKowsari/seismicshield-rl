from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np

from seismicshield_rl.physics.base import DamperDesign


@dataclass(frozen=True)
class ObjectiveRecord:
    """One completed design evaluation.

    ``vector`` is minimized componentwise and is expected to contain
    [normalized_cost, MIDR_ratio, PFA_ratio]. ``scalar`` is the frozen
    scalar training objective, including any fixed failure penalty.
    """

    vector: np.ndarray
    scalar: float
    converged: bool = True

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=float)
        if vector.shape != (3,):
            raise ValueError("objective vector must have exactly three components")
        if not np.all(np.isfinite(vector)) or not np.isfinite(self.scalar):
            raise ValueError("objective values must be finite")
        object.__setattr__(self, "vector", vector)


@dataclass(frozen=True)
class DesignSpace:
    n_stories: int
    max_dampers_per_story: int
    slip_force_levels_n: np.ndarray

    def __post_init__(self) -> None:
        levels = np.asarray(self.slip_force_levels_n, dtype=float)
        if self.n_stories <= 0 or self.max_dampers_per_story < 0:
            raise ValueError("invalid design-space dimensions")
        if levels.ndim != 1 or levels.size == 0 or np.any(levels < 0):
            raise ValueError("slip-force levels must be a non-empty non-negative 1D array")
        object.__setattr__(self, "slip_force_levels_n", levels)

    @property
    def n_genes(self) -> int:
        return 2 * self.n_stories

    def decode(self, genome: np.ndarray) -> DamperDesign:
        genes = np.asarray(genome, dtype=int)
        if genes.shape != (self.n_genes,):
            raise ValueError(f"genome must have shape ({self.n_genes},)")
        counts = genes[0::2]
        slips = genes[1::2]
        if np.any(counts < 0) or np.any(counts > self.max_dampers_per_story):
            raise ValueError("damper-count gene outside frozen action bounds")
        if np.any(slips < 0) or np.any(slips >= self.slip_force_levels_n.size):
            raise ValueError("slip-force index outside frozen action bounds")
        return DamperDesign(counts.astype(int), self.slip_force_levels_n[slips].astype(float))

    def random_genome(self, rng: np.random.Generator) -> np.ndarray:
        genome = np.empty(self.n_genes, dtype=int)
        genome[0::2] = rng.integers(0, self.max_dampers_per_story + 1, size=self.n_stories)
        genome[1::2] = rng.integers(0, self.slip_force_levels_n.size, size=self.n_stories)
        return genome


@dataclass(frozen=True)
class DesignContext:
    """A training/validation context with causal, non-identifying features only."""

    local_features: np.ndarray
    evaluate: Callable[[DamperDesign], ObjectiveRecord]
    context_id: str = "context"

    def __post_init__(self) -> None:
        features = np.asarray(self.local_features, dtype=np.float32)
        if features.ndim != 2 or features.shape[0] == 0 or features.shape[1] == 0:
            raise ValueError("local_features must be a non-empty [stories, features] array")
        if not np.all(np.isfinite(features)):
            raise ValueError("local_features must be finite")
        object.__setattr__(self, "local_features", features)


@dataclass
class BudgetLedger:
    limit: int
    completed: int = 0

    def charge(self) -> None:
        if self.completed >= self.limit:
            raise RuntimeError("frozen simulator-evaluation budget exhausted")
        self.completed += 1

    @property
    def remaining(self) -> int:
        return self.limit - self.completed


@dataclass
class RunResult:
    method: str
    seed: int
    evaluations: int
    best_design: DamperDesign
    best_record: ObjectiveRecord
    pareto_designs: list[DamperDesign] = field(default_factory=list)
    pareto_records: list[ObjectiveRecord] = field(default_factory=list)


def record_from_design_evaluation(evaluation) -> ObjectiveRecord:
    """Adapt the repository's DesignEvaluator result to the frozen algorithm contract."""

    return ObjectiveRecord(
        np.asarray([evaluation.cost, evaluation.midr_ratio, evaluation.pfa_ratio], dtype=float),
        float(evaluation.objective),
        bool(evaluation.converged),
    )


def context_from_design_evaluator(evaluator, *, context_id: str = "design-evaluator") -> DesignContext:
    """Construct the six-feature story observation used by IPPO/MAPPO.

    This mirrors the public PettingZoo environment and contains no record identity.
    """

    building = evaluator.simulator.building
    reference_story = np.max(np.abs(evaluator.reference.story_drift_ratio), axis=0)
    maximum = max(float(reference_story.max()), 1e-12)
    n = building.n_stories
    local = np.zeros((n, 6), dtype=np.float32)
    for index in range(n):
        local[index] = np.asarray(
            [
                index / max(1, n - 1),
                building.masses_kg[index] / building.masses_kg.mean(),
                building.stiffness_n_per_m[index] / building.stiffness_n_per_m.mean(),
                reference_story[index] / maximum,
                evaluator.reference.metrics["midr"],
                evaluator.reference.metrics["pfa_g"],
            ],
            dtype=np.float32,
        )

    def _evaluate(design: DamperDesign) -> ObjectiveRecord:
        return record_from_design_evaluation(evaluator.evaluate(design))

    return DesignContext(local, _evaluate, context_id=context_id)


def _evaluate(
    ledger: BudgetLedger,
    oracle: Callable[[DamperDesign], ObjectiveRecord],
    design: DamperDesign,
) -> ObjectiveRecord:
    ledger.charge()
    record = oracle(design)
    if not isinstance(record, ObjectiveRecord):
        raise TypeError("evaluation oracle must return ObjectiveRecord")
    return record


def _best_index(records: list[ObjectiveRecord]) -> int:
    return int(np.argmin([record.scalar for record in records]))


def run_random_search(
    space: DesignSpace,
    oracle: Callable[[DamperDesign], ObjectiveRecord],
    *,
    budget: int,
    seed: int,
) -> RunResult:
    if budget <= 0:
        raise ValueError("budget must be positive")
    rng = np.random.default_rng(seed)
    ledger = BudgetLedger(int(budget))
    designs: list[DamperDesign] = []
    records: list[ObjectiveRecord] = []
    while ledger.remaining:
        design = space.decode(space.random_genome(rng))
        designs.append(design)
        records.append(_evaluate(ledger, oracle, design))
    best = _best_index(records)
    return RunResult("random_search", seed, ledger.completed, designs[best], records[best])


def _dominates(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.all(a <= b) and np.any(a < b))


def _nondominated_sort(vectors: np.ndarray) -> tuple[np.ndarray, list[list[int]]]:
    n = vectors.shape[0]
    dominates: list[list[int]] = [[] for _ in range(n)]
    dominated_count = np.zeros(n, dtype=int)
    fronts: list[list[int]] = [[]]
    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if _dominates(vectors[p], vectors[q]):
                dominates[p].append(q)
            elif _dominates(vectors[q], vectors[p]):
                dominated_count[p] += 1
        if dominated_count[p] == 0:
            fronts[0].append(p)
    rank = np.full(n, -1, dtype=int)
    level = 0
    while level < len(fronts) and fronts[level]:
        next_front: list[int] = []
        for p in fronts[level]:
            rank[p] = level
            for q in dominates[p]:
                dominated_count[q] -= 1
                if dominated_count[q] == 0:
                    next_front.append(q)
        if next_front:
            fronts.append(next_front)
        level += 1
    return rank, fronts


def _crowding_distance(vectors: np.ndarray, front: Iterable[int]) -> dict[int, float]:
    indices = list(front)
    if not indices:
        return {}
    distance = {index: 0.0 for index in indices}
    if len(indices) <= 2:
        return {index: float("inf") for index in indices}
    for objective in range(vectors.shape[1]):
        ordered = sorted(indices, key=lambda index: vectors[index, objective])
        distance[ordered[0]] = float("inf")
        distance[ordered[-1]] = float("inf")
        low = vectors[ordered[0], objective]
        high = vectors[ordered[-1], objective]
        span = high - low
        if span <= 0:
            continue
        for position in range(1, len(ordered) - 1):
            if np.isinf(distance[ordered[position]]):
                continue
            previous = vectors[ordered[position - 1], objective]
            following = vectors[ordered[position + 1], objective]
            distance[ordered[position]] += float((following - previous) / span)
    return distance


def _rank_and_crowding(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[list[int]]]:
    rank, fronts = _nondominated_sort(vectors)
    crowding = np.zeros(vectors.shape[0], dtype=float)
    for front in fronts:
        for index, value in _crowding_distance(vectors, front).items():
            crowding[index] = value
    return rank, crowding, fronts


def _survival_indices(vectors: np.ndarray, population_size: int) -> np.ndarray:
    _, _, fronts = _rank_and_crowding(vectors)
    chosen: list[int] = []
    for front in fronts:
        if len(chosen) + len(front) <= population_size:
            chosen.extend(front)
            continue
        crowd = _crowding_distance(vectors, front)
        ordered = sorted(front, key=lambda index: (-crowd[index], index))
        chosen.extend(ordered[: population_size - len(chosen)])
        break
    return np.asarray(chosen, dtype=int)


def run_nsga2(
    space: DesignSpace,
    oracle: Callable[[DamperDesign], ObjectiveRecord],
    *,
    budget: int,
    seed: int,
    population_size: int = 256,
    crossover_probability: float = 0.90,
) -> RunResult:
    """Discrete NSGA-II with exact simulator-call accounting."""

    if budget <= 0 or population_size <= 1:
        raise ValueError("budget and population_size must be positive")
    if population_size > budget:
        population_size = int(budget)
    rng = np.random.default_rng(seed)
    ledger = BudgetLedger(int(budget))

    population = np.stack([space.random_genome(rng) for _ in range(population_size)])
    records = [_evaluate(ledger, oracle, space.decode(genome)) for genome in population]

    while ledger.remaining:
        vectors = np.stack([record.vector for record in records])
        rank, crowding, _ = _rank_and_crowding(vectors)

        def tournament() -> int:
            candidates = rng.integers(0, population.shape[0], size=2)
            left, right = int(candidates[0]), int(candidates[1])
            if rank[left] != rank[right]:
                return left if rank[left] < rank[right] else right
            if crowding[left] != crowding[right]:
                return left if crowding[left] > crowding[right] else right
            return left if rng.random() < 0.5 else right

        offspring: list[np.ndarray] = []
        target = min(population_size, ledger.remaining)
        mutation_probability = 1.0 / space.n_genes
        while len(offspring) < target:
            first = population[tournament()].copy()
            second = population[tournament()].copy()
            if rng.random() < crossover_probability:
                mask = rng.random(space.n_genes) < 0.5
                child = np.where(mask, first, second)
            else:
                child = first
            for gene in range(space.n_genes):
                if rng.random() >= mutation_probability:
                    continue
                upper = (
                    space.max_dampers_per_story
                    if gene % 2 == 0
                    else space.slip_force_levels_n.size - 1
                )
                if upper <= 0:
                    child[gene] = 0
                    continue
                proposal = int(rng.integers(0, upper + 1))
                if proposal == child[gene]:
                    proposal = (proposal + 1 + int(rng.integers(0, upper))) % (upper + 1)
                child[gene] = proposal
            offspring.append(child.astype(int))

        offspring_array = np.stack(offspring)
        offspring_records = [
            _evaluate(ledger, oracle, space.decode(genome)) for genome in offspring_array
        ]
        combined_population = np.vstack([population, offspring_array])
        combined_records = records + offspring_records
        combined_vectors = np.stack([record.vector for record in combined_records])
        keep = _survival_indices(combined_vectors, population_size)
        population = combined_population[keep]
        records = [combined_records[index] for index in keep.tolist()]

    vectors = np.stack([record.vector for record in records])
    _, fronts = _nondominated_sort(vectors)
    pareto_indices = fronts[0]
    pareto_designs = [space.decode(population[index]) for index in pareto_indices]
    pareto_records = [records[index] for index in pareto_indices]
    best = _best_index(records)
    return RunResult(
        "nsga2",
        seed,
        ledger.completed,
        space.decode(population[best]),
        records[best],
        pareto_designs=pareto_designs,
        pareto_records=pareto_records,
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


def run_ppo_family(
    method: str,
    space: DesignSpace,
    contexts: list[DesignContext],
    *,
    budget: int,
    seed: int,
    batch_design_evaluations: int = 256,
    update_epochs: int = 4,
    learning_rate: float = 3.0e-4,
    clip_epsilon: float = 0.20,
    value_loss_coefficient: float = 0.50,
    entropy_coefficient: float = 0.01,
    max_grad_norm: float = 0.50,
    hidden_units: tuple[int, int] = (128, 128),
) -> RunResult:
    """Run frozen one-step PPO, IPPO or MAPPO offline co-design.

    Each sampled joint design consumes exactly one simulator-evaluation budget unit.
    Gradient epochs never consume simulator budget. IPPO and MAPPO use a shared
    story actor; MAPPO differs by its centralized critic. PPO uses global context in
    the actor and a joint-design probability ratio.
    """

    if method not in {"ppo", "ippo", "mappo"}:
        raise ValueError("method must be one of: ppo, ippo, mappo")
    if budget <= 0 or batch_design_evaluations <= 0 or update_epochs <= 0:
        raise ValueError("invalid PPO budget/update settings")
    if not contexts:
        raise ValueError("at least one training context is required")
    feature_dim = int(contexts[0].local_features.shape[1])
    for context in contexts:
        if context.local_features.shape[1] != feature_dim:
            raise ValueError("all contexts must use the same local feature width")
        if context.local_features.shape[0] != space.n_stories:
            raise ValueError("context story count must match DesignSpace")

    try:
        import torch
        from torch import nn
        from torch.distributions import Categorical
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyTorch is required for PPO/IPPO/MAPPO") from exc

    torch.manual_seed(int(seed))
    torch.use_deterministic_algorithms(True)
    rng = np.random.default_rng(seed)
    device = torch.device("cpu")
    global_dim = 3 * feature_dim + 1
    actor_dim = feature_dim + global_dim if method == "ppo" else feature_dim
    critic_dim = feature_dim if method == "ippo" else global_dim

    class Actor(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(actor_dim, hidden_units[0]),
                nn.Tanh(),
                nn.Linear(hidden_units[0], hidden_units[1]),
                nn.Tanh(),
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
                nn.Linear(critic_dim, hidden_units[0]),
                nn.Tanh(),
                nn.Linear(hidden_units[0], hidden_units[1]),
                nn.Tanh(),
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
    best_design: DamperDesign | None = None
    best_record: ObjectiveRecord | None = None

    while ledger.remaining:
        batch_size = min(int(batch_design_evaluations), ledger.remaining)
        trajectories: list[dict] = []
        for _ in range(batch_size):
            context = contexts[int(rng.integers(0, len(contexts)))]
            local_np = context.local_features
            global_np = _global_summary(local_np)
            local = torch.as_tensor(local_np, dtype=torch.float32, device=device)
            global_tensor = torch.as_tensor(global_np, dtype=torch.float32, device=device)
            if method == "ppo":
                global_repeated = global_tensor.unsqueeze(0).repeat(space.n_stories, 1)
                actor_input = torch.cat([local, global_repeated], dim=1)
            else:
                actor_input = local
            with torch.no_grad():
                count_logits, slip_logits = actor(actor_input)
                count_dist = Categorical(logits=count_logits)
                slip_dist = Categorical(logits=slip_logits)
                count_actions = count_dist.sample()
                slip_actions = slip_dist.sample()
                log_prob_agents = count_dist.log_prob(count_actions) + slip_dist.log_prob(
                    slip_actions
                )
                entropy_agents = count_dist.entropy() + slip_dist.entropy()
                if method == "ippo":
                    old_values = critic(local)
                else:
                    old_values = critic(global_tensor.unsqueeze(0)).squeeze(0)
            design = DamperDesign(
                count_actions.cpu().numpy().astype(int),
                space.slip_force_levels_n[slip_actions.cpu().numpy().astype(int)].astype(float),
            )
            record = _evaluate(ledger, context.evaluate, design)
            reward = -float(record.scalar)
            if best_record is None or record.scalar < best_record.scalar:
                best_record = record
                best_design = design
            trajectories.append(
                {
                    "local": local_np.copy(),
                    "global": global_np.copy(),
                    "count": count_actions.cpu().numpy().astype(np.int64),
                    "slip": slip_actions.cpu().numpy().astype(np.int64),
                    "old_logp": log_prob_agents.cpu().numpy().astype(np.float64),
                    "old_entropy": entropy_agents.cpu().numpy().astype(np.float64),
                    "old_value": old_values.cpu().numpy().copy(),
                    "reward": reward,
                }
            )

        if method == "ippo":
            raw_advantages = np.concatenate(
                [
                    np.full(space.n_stories, item["reward"], dtype=float)
                    - np.asarray(item["old_value"], dtype=float)
                    for item in trajectories
                ]
            )
        else:
            raw_advantages = np.asarray(
                [item["reward"] - float(item["old_value"]) for item in trajectories], dtype=float
            )
        advantage_mean = float(raw_advantages.mean())
        advantage_std = max(float(raw_advantages.std()), 1e-8)

        for _ in range(int(update_epochs)):
            actor_terms = []
            value_terms = []
            entropy_terms = []
            agent_adv_offset = 0
            for trajectory_index, item in enumerate(trajectories):
                local = torch.as_tensor(item["local"], dtype=torch.float32, device=device)
                global_tensor = torch.as_tensor(item["global"], dtype=torch.float32, device=device)
                if method == "ppo":
                    actor_input = torch.cat(
                        [global_tensor.unsqueeze(0).repeat(space.n_stories, 1), local], dim=1
                    )
                    # Restore the frozen ordering: local features followed by global summary.
                    actor_input = torch.cat([local, actor_input[:, :global_dim]], dim=1)
                else:
                    actor_input = local
                count_actions = torch.as_tensor(item["count"], dtype=torch.long, device=device)
                slip_actions = torch.as_tensor(item["slip"], dtype=torch.long, device=device)
                old_logp = torch.as_tensor(item["old_logp"], dtype=torch.float32, device=device)
                count_logits, slip_logits = actor(actor_input)
                count_dist = Categorical(logits=count_logits)
                slip_dist = Categorical(logits=slip_logits)
                current_logp = count_dist.log_prob(count_actions) + slip_dist.log_prob(slip_actions)
                entropy = (count_dist.entropy() + slip_dist.entropy()).mean()

                if method == "ppo":
                    normalized_advantage = (
                        raw_advantages[trajectory_index] - advantage_mean
                    ) / advantage_std
                    advantage = torch.tensor(
                        normalized_advantage, dtype=torch.float32, device=device
                    )
                    ratio = torch.exp(current_logp.sum() - old_logp.sum())
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(-torch.minimum(ratio * advantage, clipped * advantage))
                    predicted = critic(global_tensor.unsqueeze(0)).squeeze(0)
                    target = torch.tensor(item["reward"], dtype=torch.float32, device=device)
                    value_terms.append((predicted - target).pow(2))
                elif method == "mappo":
                    normalized_advantage = (
                        raw_advantages[trajectory_index] - advantage_mean
                    ) / advantage_std
                    advantage = torch.tensor(
                        normalized_advantage, dtype=torch.float32, device=device
                    )
                    ratio = torch.exp(current_logp - old_logp)
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(
                        -torch.minimum(ratio * advantage, clipped * advantage).mean()
                    )
                    predicted = critic(global_tensor.unsqueeze(0)).squeeze(0)
                    target = torch.tensor(item["reward"], dtype=torch.float32, device=device)
                    value_terms.append((predicted - target).pow(2))
                else:
                    local_advantages = raw_advantages[
                        agent_adv_offset : agent_adv_offset + space.n_stories
                    ]
                    agent_adv_offset += space.n_stories
                    normalized = (local_advantages - advantage_mean) / advantage_std
                    advantage = torch.as_tensor(normalized, dtype=torch.float32, device=device)
                    ratio = torch.exp(current_logp - old_logp)
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon)
                    actor_terms.append(
                        -torch.minimum(ratio * advantage, clipped * advantage).mean()
                    )
                    predicted = critic(local)
                    target = torch.full_like(predicted, float(item["reward"]))
                    value_terms.append((predicted - target).pow(2).mean())
                entropy_terms.append(entropy)

            actor_loss = torch.stack(actor_terms).mean()
            value_loss = torch.stack(value_terms).mean()
            entropy_bonus = torch.stack(entropy_terms).mean()
            total_loss = (
                actor_loss
                + float(value_loss_coefficient) * value_loss
                - float(entropy_coefficient) * entropy_bonus
            )
            optimizer.zero_grad(set_to_none=True)
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(actor.parameters()) + list(critic.parameters()), float(max_grad_norm)
            )
            optimizer.step()

    if best_design is None or best_record is None:  # pragma: no cover
        raise RuntimeError("PPO family produced no completed design evaluation")
    return RunResult(method, seed, ledger.completed, best_design, best_record)
