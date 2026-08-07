"""Constructive placement heuristic: extreme points + a sorted item order.

The classic first-fit-decreasing family. Items are sorted once, then each is
dropped into the best candidate corner the pool offers. The solution quality
therefore depends almost entirely on two things -- the item order and the
corner preference -- which is exactly the search space the improvement pass
(F5) will explore.

The solver enforces K1 (no overlap), K2 (inside the vehicle), K3 (payload) and
K4 (support). The remaining constraints arrive in F4. Nothing here reports its
own correctness: run :mod:`core.validator` over the result.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
)
from core.metrics import evaluate
from core.models import Dims, Item, Job, Orientation, Placement, Plan, Unplaced

#: Item sort keys. Bulky-first is the standard opening move: the awkward pieces
#: get the empty vehicle, and the small ones fill the gaps they leave.
ITEM_ORDERS = {
    "volume_desc": lambda it: (-it.type.dims.volume, it.uid),
    "base_area_desc": lambda it: (-it.type.dims.footprint, -it.type.dims.h, it.uid),
    "height_desc": lambda it: (-it.type.dims.h, -it.type.dims.volume, it.uid),
    "weight_desc": lambda it: (-it.type.weight_g, it.uid),
    "as_given": lambda it: (it.uid,),
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
    scorer: str = "dbl"
    #: ``first_fit`` takes the first workable corner, ``best_fit`` scores them
    #: all. Best-fit buys a little utilisation for a lot of time.
    search: str = "first_fit"
    enforce_support: bool = True
    #: Cap on candidate corners examined per item. The pool grows by three per
    #: placement, and the far tail is almost never the winner.
    max_points: int = 400
    cell_mm: int = 1000
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


def _try_item(
    item: Item,
    index: SpatialIndex,
    points: list,
    inner: Dims,
    min_support: float,
    config: SolverConfig,
) -> tuple[Box, Orientation] | None:
    """Best (or first) legal box for this item, or None if it does not fit."""
    scorer = SCORERS[config.scorer]
    best_fit = config.search == "best_fit"
    shapes = distinct_orientations(item.type.dims, item.type.allowed_orientations)

    best: tuple[Box, Orientation] | None = None
    best_score: tuple | None = None

    for point in points:
        for orientation, dims in shapes:
            box = make_box(point, dims)
            if not inside(box, inner):
                continue
            box = index.settle(box)
            if index.collides(box):
                continue
            if min_support > 0.0 and index.support_ratio(box) < min_support:
                continue
            if not best_fit:
                return box, orientation
            score = scorer(box, index, inner)
            if best_score is None or score < best_score:
                best_score, best = score, (box, orientation)

    return best


def solve(job: Job, config: SolverConfig | None = None) -> Plan:
    """Pack ``job`` and return a plan. Never raises on an infeasible item."""
    config = config or SolverConfig()
    config.validate()

    started = perf_counter()
    inner = job.vehicle.inner
    index = SpatialIndex(cell=config.cell_mm)
    pool = ExtremePoints()
    min_support = job.vehicle.min_support_ratio if config.enforce_support else 0.0

    placements: list[Placement] = []
    unplaced: list[Unplaced] = []
    remaining_payload = job.vehicle.max_payload_g
    since_prune = 0

    for item in sorted(job.items, key=ITEM_ORDERS[config.item_order]):
        if item.weight_g > remaining_payload:
            # Sorted by size, not weight, so a later light item may still fit.
            unplaced.append(Unplaced(item.uid, item.sku, "payload"))
            continue

        points = pool.ordered(order=config.point_order, limit=config.max_points)
        found = _try_item(item, index, points, inner, min_support, config)
        if found is None:
            unplaced.append(Unplaced(item.uid, item.sku, "no_fit"))
            continue

        box, orientation = found
        index.add(box)
        pool.add_from_box(box)
        remaining_payload -= item.weight_g
        placements.append(
            Placement(
                seq=len(placements) + 1,
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
