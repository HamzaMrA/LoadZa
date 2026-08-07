"""Plan quality measurement.

Kept apart from the solver on purpose: a solver that reports its own score is
free to grade generously. The validator (F2) fills in the violation counts;
until then ``violations`` stays empty, which ``Metrics.is_valid`` reads as clean
-- so do not treat an F1 plan as validated.
"""

from __future__ import annotations

from core.models import Gram, Job, Metrics, Placement, Unplaced


def centre_of_gravity(
    placements: tuple[Placement, ...], weights: dict[int, Gram]
) -> tuple[int, int, int]:
    """Weighted centroid of the load, in vehicle coordinates."""
    total = 0
    mx = my = mz = 0
    for p in placements:
        w = weights[p.item_uid]
        total += w
        mx += w * (p.pos.x + p.dims.l // 2)
        my += w * (p.pos.y + p.dims.w // 2)
        mz += w * (p.pos.z + p.dims.h // 2)
    if total == 0:
        return (0, 0, 0)
    return (mx // total, my // total, mz // total)


def evaluate(
    job: Job,
    placements: tuple[Placement, ...],
    unplaced: tuple[Unplaced, ...],
    solve_ms: int,
    violations: dict[str, int] | None = None,
) -> Metrics:
    """Score a plan against its job.

    ``volume_utilization`` is placed volume over interior volume. It is the
    headline number in the literature, but it is only meaningful for
    volume-bound loads: a pallet job hits the payload limit at roughly 60%
    volume, so ``weight_utilization`` has to be read alongside it.
    """
    weights = {item.uid: item.weight_g for item in job.items}
    placed_volume = sum(p.dims.volume for p in placements)
    placed_weight = sum(weights[p.item_uid] for p in placements)
    cog_x, cog_y, _ = centre_of_gravity(placements, weights)
    inner = job.vehicle.inner

    return Metrics(
        volume_utilization=placed_volume / inner.volume,
        weight_utilization=placed_weight / job.vehicle.max_payload_g,
        placed=len(placements),
        unplaced=len(unplaced),
        cog_lateral_mm=cog_y - inner.w // 2 if placements else 0,
        cog_longitudinal_mm=cog_x - inner.l // 2 if placements else 0,
        solve_ms=solve_ms,
        violations=dict(violations or {}),
    )
