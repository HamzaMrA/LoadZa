"""Constructive placement heuristic: extreme points + a sorted item order.

The classic first-fit-decreasing family. Items are sorted once, then each is
dropped into the best candidate corner the pool offers. The solution quality
therefore depends almost entirely on two things -- the item order and the
corner preference -- which is exactly the search space the improvement pass
(F5) will explore.

Constraint handling splits three ways, because the constraints themselves do:

* **Local** -- K1, K2, K3, K4, K6 are decided by looking at one candidate
  position. They are filters inside the placement loop.
* **Cumulative** -- K5 (stacking) and K8 (multi-drop reach) depend on what is
  already loaded, so the solver carries running state: a load figure per box
  and, for LIFO, the packing order runs from the last delivery stop to the
  first, so early stops end up nearest the doors.
* **Global** -- K7 is a property of the finished load, not of any one box, and
  a greedy filter cannot enforce it. It is handled by translating the whole
  packed block along the vehicle afterwards, which moves the centre of gravity
  without disturbing a single relative position.

Nothing here reports its own correctness: run :mod:`core.validator` over the
result.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter

from core.extreme_points import POINT_ORDERS, ExtremePoints
from core.geometry import (
    Box,
    SpatialIndex,
    box_pos,
    box_dims,
    distinct_orientations,
    inside,
    make_box,
    suggest_cell_size,
)
from core.metrics import evaluate
from core.models import Dims, Gram, Item, Job, Orientation, Placement, Plan, Pos, Unplaced

#: Item sort keys. Bulky-first is the standard opening move: the awkward pieces
#: get the empty vehicle, and the small ones fill the gaps they leave.
ITEM_ORDERS = {
    "volume_desc": lambda it: (-it.type.dims.volume, it.uid),
    "base_area_desc": lambda it: (-it.type.dims.footprint, -it.type.dims.h, it.uid),
    "height_desc": lambda it: (-it.type.dims.h, -it.type.dims.volume, it.uid),
    "weight_desc": lambda it: (-it.type.weight_g, it.uid),
    "as_given": lambda it: (it.uid,),
    #: Take the job's item tuple in the order it arrives. This is the hook the
    #: improvement pass (F5) drives: it searches permutations, so it must be
    #: able to hand one over without the solver re-sorting it away.
    "sequence": None,
}


def _score_position(box: Box, index: SpatialIndex, inner: Dims) -> tuple:
    return (box[0], box[1], box[2])


def _score_layer(box: Box, index: SpatialIndex, inner: Dims) -> tuple:
    return (box[2], box[0], box[1])


def _score_contact(box: Box, index: SpatialIndex, inner: Dims) -> tuple:
    # Negated so that "smaller score wins" holds for every scorer.
    return (-index.contact_area(box, inner), box[0], box[1], box[2])


#: Candidate rankings. All are minimised.
SCORERS = {
    "dbl": _score_position,
    "layer": _score_layer,
    "contact": _score_contact,
}


@dataclass(frozen=True, slots=True)
class SolverConfig:
    item_order: str = "volume_desc"
    #: Also selects the candidate ordering when ``search`` is ``first_fit``.
    #: ``layer`` is the default on benchmark evidence: over the 700 BR1-BR7
    #: instances it averages 82.1% against 81.6% for ``dbl``, and it is
    #: slightly faster. See bench/results and docs/BENCHMARKS.md.
    scorer: str = "layer"
    #: ``first_fit`` takes the first workable corner, ``best_fit`` scores them
    #: all. Best-fit buys a little utilisation for a lot of time.
    search: str = "first_fit"
    #: K4 -- nothing floats.
    enforce_support: bool = True
    #: K5 -- no box carries more than it is rated for.
    enforce_stacking: bool = True
    #: K8 -- pack the last delivery stop first, and refuse to bury an earlier
    #: one behind a later one.
    enforce_lifo: bool = True
    #: K7 -- slide the finished load along the vehicle to centre its weight.
    rebalance: bool = True
    #: K7 sideways, and **off by default**. Sliding cannot centre a load that
    #: already spans the full width, so this tries both sides per item and
    #: keeps whichever leaves the smaller lean. Measured over the demo jobs it
    #: fixes one, worsens another and costs roughly double the time: a greedy
    #: rule cannot see that a locally better side forces later boxes to a worse
    #: one. Lateral balance belongs to the F5 global search.
    balance_lateral: bool = False
    #: Cap on candidate corners examined per item. The pool grows by three per
    #: placement, and the far tail is almost never the winner.
    max_points: int = 400
    #: Grid cell size. ``None`` derives it from the cargo, which is almost
    #: always right; a fixed value that exceeds the container turns the index
    #: into a linear scan.
    cell_mm: int | None = None
    #: Pruning buried corners costs a collision query each, so batch it.
    prune_every: int = 16

    def validate(self) -> None:
        if self.item_order not in ITEM_ORDERS:
            raise KeyError(f"unknown item order {self.item_order!r}")
        if self.scorer not in SCORERS:
            raise KeyError(f"unknown scorer {self.scorer!r}")
        if self.search not in ("first_fit", "best_fit"):
            raise KeyError(f"unknown search {self.search!r}")

    @property
    def point_order(self) -> str:
        return self.scorer if self.scorer in POINT_ORDERS else "dbl"

    @property
    def algorithm(self) -> str:
        return f"EP/{self.item_order}/{self.scorer}/{self.search}"


@dataclass(slots=True)
class _LoadState:
    """Running bookkeeping for the constraints that depend on what is loaded."""

    weights: list[Gram] = field(default_factory=list)
    limits: list[Gram | None] = field(default_factory=list)
    stops: list[int] = field(default_factory=list)
    #: Weight currently resting on each box, own weight excluded.
    carried: list[float] = field(default_factory=list)
    #: (index, contact area) of whatever holds each box up.
    supporters: list[list[tuple[int, int]]] = field(default_factory=list)
    #: Boxes grouped by delivery stop, for the LIFO reach check.
    by_stop: dict[int, list[Box]] = field(default_factory=dict)
    #: How far towards the doors each stop's freight reaches.
    reach: dict[int, int] = field(default_factory=dict)
    #: Running sideways moment, for the lateral balance tie-break.
    moment_y: float = 0.0
    total_weight: float = 0.0

    def record(self, box: Box, item: Item, supporters: list[tuple[int, int]]) -> None:
        self.weights.append(item.weight_g)
        self.limits.append(item.type.max_stack_weight_g)
        self.stops.append(item.stop)
        self.carried.append(0.0)
        self.supporters.append(supporters)
        self.by_stop.setdefault(item.stop, []).append(box)
        self.reach[item.stop] = max(self.reach.get(item.stop, 0), box[3])
        self.moment_y += item.weight_g * (box[1] + box[4]) / 2
        self.total_weight += item.weight_g

    def lateral_offset(self, inner: Dims) -> float:
        """How far the load so far sits from the centreline, signed."""
        if self.total_weight == 0:
            return 0.0
        return self.moment_y / self.total_weight - inner.w / 2

    def barrier(self, stop: int) -> int:
        """Furthest point towards the doors reached by any later stop.

        A candidate ending beyond this cannot have a later-stop box in front of
        it, which lets most LIFO checks skip the detailed scan.
        """
        later = [x for s, x in self.reach.items() if s > stop]
        return max(later) if later else 0


def _load_delta(
    index: SpatialIndex, state: _LoadState, supporters: list[tuple[int, int]], weight: Gram
) -> dict[int, float]:
    """How much extra load each box below would end up carrying.

    Weight splits between supporters in proportion to contact area -- a crude
    pressure model, but ignoring the split would let a box resting on one
    corner of a pallet appear to weigh nothing there. The walk continues down
    the support tree, so the box at the bottom of a stack sees the whole column.
    """
    delta: dict[int, float] = {}
    total_area = sum(area for _, area in supporters)
    if total_area == 0:
        return delta

    pending = [(index_, weight * area / total_area) for index_, area in supporters]
    while pending:
        target, share = pending.pop()
        delta[target] = delta.get(target, 0.0) + share
        below = state.supporters[target]
        if not below:
            continue
        below_area = sum(area for _, area in below)
        if below_area == 0:
            continue
        for deeper, area in below:
            pending.append((deeper, share * area / below_area))
    return delta


def _stacking_ok(state: _LoadState, delta: dict[int, float]) -> bool:
    for target, extra in delta.items():
        limit = state.limits[target]
        if limit is not None and state.carried[target] + extra > limit + 1e-6:
            return False
    return True


def _lifo_ok(state: _LoadState, box: Box, stop: int, barrier: int) -> bool:
    """No freight for a later stop may stand between this box and the doors."""
    if box[3] > barrier:
        return True
    for other_stop, boxes in state.by_stop.items():
        if other_stop <= stop:
            continue
        for other in boxes:
            if other[0] < box[3]:
                continue
            if min(box[4], other[4]) <= max(box[1], other[1]):
                continue
            if min(box[5], other[5]) <= max(box[2], other[2]):
                continue
            return False
    return True


def _try_item(
    item: Item,
    index: SpatialIndex,
    state: _LoadState,
    points: list,
    inner: Dims,
    min_support: float,
    barrier: int,
    config: SolverConfig,
) -> tuple[Box, Orientation, list[tuple[int, int]], dict[int, float]] | None:
    """Best (or first) legal box for this item, or None if it does not fit."""
    scorer = SCORERS[config.scorer]
    best_fit = config.search == "best_fit"
    shapes = distinct_orientations(item.type.dims, item.type.allowed_orientations)

    best = None
    best_score: tuple | None = None

    for point in points:
        for orientation, dims in shapes:
            box = make_box(point, dims)
            if not inside(box, inner):
                continue
            box = index.settle(box)
            if index.collides(box):
                continue

            supporters = index.supporters(box) if box[2] > 0 else []
            if min_support > 0.0 and box[2] > 0:
                area = dims.footprint
                if sum(a for _, a in supporters) / area < min_support:
                    continue

            delta: dict[int, float] = {}
            if config.enforce_stacking and supporters:
                delta = _load_delta(index, state, supporters, item.weight_g)
                if not _stacking_ok(state, delta):
                    continue

            if config.enforce_lifo and not _lifo_ok(state, box, item.stop, barrier):
                continue

            if not best_fit:
                return box, orientation, supporters, delta
            score = scorer(box, index, inner)
            if best_score is None or score < best_score:
                best_score = score
                best = (box, orientation, supporters, delta)

    return best


def _projected_offset(state: _LoadState, box: Box, item: Item, inner: Dims) -> float:
    """Where the sideways centre of gravity lands if this box goes here."""
    weight = item.weight_g
    total = state.total_weight + weight
    if total == 0:
        return 0.0
    moment = state.moment_y + weight * (box[1] + box[4]) / 2
    return moment / total - inner.w / 2


def _rebalance(
    placements: list[Placement], inner: Dims, weights: dict[int, Gram]
) -> list[Placement]:
    """Slide the whole load so its centre of gravity sits mid-vehicle.

    Translating every box by the same vector cannot break anything: overlap,
    support, stacking and stop order are all relative. Only the walls are
    absolute, so the shift is clamped to the free space at each end. A load
    that fills the vehicle has nowhere to go, and needs nowhere to go.
    """
    if not placements:
        return placements

    total = sum(weights[p.item_uid] for p in placements)
    if total == 0:
        return placements

    cog_x = sum(weights[p.item_uid] * (p.pos.x + p.dims.l / 2) for p in placements) / total
    cog_y = sum(weights[p.item_uid] * (p.pos.y + p.dims.w / 2) for p in placements) / total

    min_x = min(p.pos.x for p in placements)
    max_x = max(p.pos.x + p.dims.l for p in placements)
    min_y = min(p.pos.y for p in placements)
    max_y = max(p.pos.y + p.dims.w for p in placements)

    shift_x = max(-min_x, min(inner.l - max_x, round(inner.l / 2 - cog_x)))
    shift_y = max(-min_y, min(inner.w - max_y, round(inner.w / 2 - cog_y)))
    if shift_x == 0 and shift_y == 0:
        return placements

    return [
        replace(p, pos=Pos(p.pos.x + shift_x, p.pos.y + shift_y, p.pos.z))
        for p in placements
    ]


def solve(job: Job, config: SolverConfig | None = None) -> Plan:
    """Pack ``job`` and return a plan. Never raises on an infeasible item."""
    config = config or SolverConfig()
    config.validate()

    started = perf_counter()
    inner = job.vehicle.inner
    cell = config.cell_mm or suggest_cell_size(
        inner, [item.type.dims for item in job.items]
    )
    index = SpatialIndex(cell=cell)
    pool = ExtremePoints()
    state = _LoadState()
    min_support = job.vehicle.min_support_ratio if config.enforce_support else 0.0
    lateral_deadband = job.vehicle.cog_lateral_tol_mm / 2

    placements: list[Placement] = []
    unplaced: list[Unplaced] = []
    remaining_payload = job.vehicle.max_payload_g
    since_prune = 0

    base_key = ITEM_ORDERS[config.item_order]
    if base_key is None:
        # "sequence": honour the caller's order. Sorting by stop alone is
        # stable, so the given order survives inside each stop.
        ordered_items = list(job.items)
        if config.enforce_lifo:
            ordered_items.sort(key=lambda item: -item.stop)
    else:
        if config.enforce_lifo:
            # Last stop first, so it ends up deepest and the first drop
            # finishes nearest the doors.
            def order_key(item: Item):
                return (-item.stop, *base_key(item))
        else:
            order_key = base_key
        ordered_items = sorted(job.items, key=order_key)

    for item in ordered_items:
        if item.weight_g > remaining_payload:
            # Sorted by size, not weight, so a later light item may still fit.
            unplaced.append(Unplaced(item.uid, item.sku, "payload"))
            continue

        barrier = state.barrier(item.stop) if config.enforce_lifo else 0
        offset = state.lateral_offset(inner)

        def attempt(mirror: bool):
            return _try_item(
                item, index, state,
                pool.ordered(order=config.point_order, limit=config.max_points,
                             mirror_y=mirror),
                inner, min_support, barrier, config,
            )

        found = attempt(mirror=False)

        # Correct the side only once the lean is worth correcting, and then by
        # measuring rather than by flipping. Blindly preferring the light side
        # makes the solver chase its own tail -- it disturbs loads that were
        # already centred and can finish further out than it started.
        if config.balance_lateral and abs(offset) > lateral_deadband:
            mirrored = attempt(mirror=True)
            if found is None:
                found = mirrored
            elif mirrored is not None:
                straight_lean = abs(_projected_offset(state, found[0], item, inner))
                mirrored_lean = abs(_projected_offset(state, mirrored[0], item, inner))
                if mirrored_lean < straight_lean:
                    found = mirrored
        if found is None:
            unplaced.append(Unplaced(item.uid, item.sku, "no_fit"))
            continue

        box, orientation, supporters, delta = found
        index.add(box)
        pool.add_from_box(box)
        state.record(box, item, supporters)
        for target, extra in delta.items():
            state.carried[target] += extra
        remaining_payload -= item.weight_g
        placements.append(
            Placement(
                seq=0,
                item_uid=item.uid,
                sku=item.sku,
                pos=box_pos(box),
                dims=box_dims(box),
                orientation=orientation,
                stop=item.stop,
            )
        )

        since_prune += 1
        if since_prune >= config.prune_every:
            pool.prune(index)
            since_prune = 0

    if config.rebalance:
        weights = {item.uid: item.weight_g for item in job.items}
        placements = _rebalance(placements, inner, weights)

    # The solver visits items biggest-first, which is not an order anyone can
    # load in. Renumber by position instead: deep end first, then bottom up.
    # Settling guarantees every box rests on something already below it, so
    # this sequence is physically executable.
    placements.sort(key=lambda p: (p.pos.x, p.pos.z, p.pos.y))
    placed = tuple(
        replace(placement, seq=i) for i, placement in enumerate(placements, start=1)
    )

    solve_ms = int((perf_counter() - started) * 1000)
    missed = tuple(unplaced)

    return Plan(
        plan_id=f"{job.job_id}-{config.scorer}-{config.search}",
        job_id=job.job_id,
        vehicle=job.vehicle,
        algorithm=config.algorithm,
        placements=placed,
        unplaced=missed,
        metrics=evaluate(job, placed, missed, solve_ms),
    )
