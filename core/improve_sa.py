"""Simulated annealing over the item order.

The constructive solver is deterministic: hand it the same items in the same
order and it returns the same plan. Everything it decides afterwards --
which corner, which orientation -- follows from that order. So the order *is*
the search space, and it is a permutation space, which is what annealing is for.

Two facts shape the design.

**Evaluating a candidate is expensive.** Every score costs a full solve, tens
to hundreds of milliseconds. There is no incremental update: moving one item
early in the sequence changes where everything after it lands. So the budget is
measured in evaluations, not in the millions of cheap steps a textbook
annealer assumes, and the moves have to be worth their price.

**The starting point is already good.** Volume-decreasing order is a strong
heuristic, not a random guess. Annealing starts there and the temperature stays
low: this is a refinement, not an exploration from scratch.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from math import exp
from time import perf_counter

from core.models import Item, Job, Plan
from core.solver_ep import ITEM_ORDERS, SolverConfig, solve


@dataclass(frozen=True, slots=True)
class AnnealConfig:
    #: Hard cap on evaluations. Reached only if the time budget does not bite.
    iterations: int = 300
    #: Wall clock budget in seconds. ``None`` runs the full iteration count.
    time_budget_s: float | None = None
    #: Temperatures are in objective units -- the objective is a utilisation
    #: fraction, so 0.02 means "accept a two point loss about a third of the
    #: time at the start".
    start_temp: float = 0.02
    end_temp: float = 0.0005
    seed: int = 0
    #: Penalty weight on a centre of gravity outside tolerance. Nothing inside
    #: tolerance is penalised: a load balanced to the millimetre is no better
    #: than one balanced to the tolerance, and pretending otherwise spends the
    #: budget chasing an irrelevance.
    cog_weight: float = 0.5
    solver: SolverConfig = field(default_factory=SolverConfig)

    def solver_for_search(self) -> SolverConfig:
        return replace(self.solver, item_order="sequence")


@dataclass(frozen=True, slots=True)
class AnnealResult:
    plan: Plan
    start_score: float
    best_score: float
    evaluations: int
    accepted: int
    improved_at: int
    elapsed_s: float

    @property
    def gain(self) -> float:
        return self.best_score - self.start_score


def objective(job: Job, plan: Plan, cog_weight: float = 0.5) -> float:
    """Utilisation, less whatever the load's balance is over tolerance.

    Both terms are fractions of the vehicle, so the weight is comparable
    across vehicle sizes.
    """
    metrics = plan.metrics
    if metrics is None:
        return 0.0

    vehicle = job.vehicle
    inner = vehicle.inner
    lateral_excess = max(0.0, abs(metrics.cog_lateral_mm) - vehicle.cog_lateral_tol_mm)
    long_limit = vehicle.cog_long_tol_ratio * inner.l
    long_excess = max(0.0, abs(metrics.cog_longitudinal_mm) - long_limit)

    penalty = lateral_excess / (inner.w / 2) + long_excess / (inner.l / 2)
    return metrics.volume_utilization - cog_weight * penalty


def _swap(order: list[Item], rng: random.Random) -> None:
    i, j = rng.randrange(len(order)), rng.randrange(len(order))
    order[i], order[j] = order[j], order[i]


def _shift(order: list[Item], rng: random.Random) -> None:
    i = rng.randrange(len(order))
    j = rng.randrange(len(order))
    order.insert(j, order.pop(i))


def _reverse(order: list[Item], rng: random.Random) -> None:
    i = rng.randrange(len(order))
    j = min(len(order), i + rng.randint(2, 8))
    order[i:j] = reversed(order[i:j])


def _promote(order: list[Item], rng: random.Random) -> None:
    """Move a late item near the front.

    Position in the sequence is not uniform in value: the first items get an
    empty vehicle and the last ones get whatever gaps are left. Deliberately
    promoting a straggler explores something the uniform moves rarely hit.
    """
    if len(order) < 4:
        return
    i = rng.randrange(len(order) // 2, len(order))
    j = rng.randrange(0, max(1, len(order) // 4))
    order.insert(j, order.pop(i))


MOVES = ((_swap, 4), (_shift, 3), (_reverse, 2), (_promote, 1))
_MOVE_FUNCS = tuple(move for move, _ in MOVES)
_MOVE_WEIGHTS = tuple(weight for _, weight in MOVES)


def improve(job: Job, config: AnnealConfig | None = None) -> AnnealResult:
    """Anneal the item order and return the best plan found.

    Never worse than the constructive solution: the incumbent starts there and
    the best-so-far is tracked separately from the current state, so a run that
    finds nothing returns what it started with.
    """
    config = config or AnnealConfig()
    if config.solver.item_order not in ITEM_ORDERS:
        raise KeyError(f"unknown item order {config.solver.item_order!r}")

    started = perf_counter()
    rng = random.Random(config.seed)
    search_config = config.solver_for_search()

    # Start from the configured constructive order, whatever it is.
    seed_plan = solve(job, config.solver)
    seed_score = objective(job, seed_plan, config.cog_weight)

    # Recover the order the constructive pass used, so the search starts from
    # that sequence rather than from the job's arbitrary input order.
    seed_key = ITEM_ORDERS[config.solver.item_order]
    current = list(job.items) if seed_key is None else sorted(job.items, key=seed_key)

    current_score = seed_score
    best_plan = seed_plan
    best_score = seed_score

    evaluations = 0
    accepted = 0
    improved_at = 0
    steps = max(0, config.iterations)
    # Guard the exponent, not the step count: asking for no iterations has to
    # mean no evaluations, or "improve nothing" silently costs a solve.
    cooling = (config.end_temp / config.start_temp) ** (1.0 / steps) if steps else 1.0
    temperature = config.start_temp

    for step in range(1, steps + 1):
        if (
            config.time_budget_s is not None
            and perf_counter() - started >= config.time_budget_s
        ):
            break

        candidate = list(current)
        rng.choices(_MOVE_FUNCS, weights=_MOVE_WEIGHTS, k=1)[0](candidate, rng)

        plan = solve(replace(job, items=tuple(candidate)), search_config)
        score = objective(job, plan, config.cog_weight)
        evaluations += 1

        delta = score - current_score
        if delta >= 0 or rng.random() < exp(delta / max(temperature, 1e-9)):
            current, current_score = candidate, score
            accepted += 1
            if score > best_score:
                best_plan, best_score = plan, score
                improved_at = step

        temperature *= cooling

    # The winning plan was produced under "sequence"; relabel it so the plan
    # file says how it was actually found rather than naming the inner pass.
    best_plan = replace(
        best_plan,
        plan_id=f"{job.job_id}-sa",
        algorithm=f"SA({evaluations})/{config.solver.algorithm}",
    )

    return AnnealResult(
        plan=best_plan,
        start_score=seed_score,
        best_score=best_score,
        evaluations=evaluations,
        accepted=accepted,
        improved_at=improved_at,
        elapsed_s=perf_counter() - started,
    )
