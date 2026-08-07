"""Independent physical validation of a plan.

This module deliberately does **not** reuse the solver's spatial index or its
placement logic. It recomputes overlap, support and load transfer from the
placement coordinates alone, with plain nested loops. A shared helper would let
a bug in that helper pass both the solver and its own audit; separate code
paths mean a disagreement shows up as a violation rather than as silence.

It is slower than the solver by design. Validation runs once per plan, not once
per candidate, so O(n^2) is a fine price for independence.

Constraints, as defined in the project notes:

===  ==========================================================================
K1   No two boxes share interior volume
K2   Every box lies inside the loading space
K3   Total loaded weight is within the payload limit
K4   Each box rests on enough surface below it
K5   The load carried by a box is within its stacking limit
K6   Each box uses an orientation its type permits
K7   The centre of gravity lies within tolerance
K8   A box is not buried behind freight for a later delivery stop
===  ==========================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Job, Placement, Plan, rotate

#: Checks applied when the caller does not narrow them down.
ALL_CHECKS: tuple[str, ...] = ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8")


@dataclass(frozen=True, slots=True)
class Violation:
    constraint: str
    detail: str
    item_uids: tuple[int, ...] = ()

    def __str__(self) -> str:
        return f"{self.constraint}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    violations: tuple[Violation, ...]
    #: Every checked constraint appears, including the ones that passed with 0.
    counts: dict[str, int]

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def of(self, constraint: str) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.constraint == constraint)

    def summary(self) -> str:
        return "  ".join(
            f"{name} {'ok' if count == 0 else f'x{count}'}"
            for name, count in sorted(self.counts.items())
        )


# ---------------------------------------------------------------------------
# local geometry, kept separate from core.geometry on purpose
# ---------------------------------------------------------------------------


def _extent(p: Placement) -> tuple[int, int, int, int, int, int]:
    return (
        p.pos.x, p.pos.y, p.pos.z,
        p.pos.x + p.dims.l, p.pos.y + p.dims.w, p.pos.z + p.dims.h,
    )


def _intersect_1d(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _volume_overlap(a: Placement, b: Placement) -> int:
    ax0, ay0, az0, ax1, ay1, az1 = _extent(a)
    bx0, by0, bz0, bx1, by1, bz1 = _extent(b)
    return (
        _intersect_1d(ax0, ax1, bx0, bx1)
        * _intersect_1d(ay0, ay1, by0, by1)
        * _intersect_1d(az0, az1, bz0, bz1)
    )


def _footprint_overlap(a: Placement, b: Placement) -> int:
    ax0, ay0, _, ax1, ay1, _ = _extent(a)
    bx0, by0, _, bx1, by1, _ = _extent(b)
    return _intersect_1d(ax0, ax1, bx0, bx1) * _intersect_1d(ay0, ay1, by0, by1)


def _cross_section_overlap(a: Placement, b: Placement) -> int:
    """Overlap of two boxes projected onto the y-z plane, i.e. down the aisle."""
    _, ay0, az0, _, ay1, az1 = _extent(a)
    _, by0, bz0, _, by1, bz1 = _extent(b)
    return _intersect_1d(ay0, ay1, by0, by1) * _intersect_1d(az0, az1, bz0, bz1)


def _supporters(target: Placement, others: list[Placement]) -> list[tuple[Placement, int]]:
    """Boxes whose top face is exactly the target's bottom face, with areas."""
    bottom = target.pos.z
    found = []
    for other in others:
        if other.item_uid == target.item_uid:
            continue
        if other.pos.z + other.dims.h != bottom:
            continue
        area = _footprint_overlap(target, other)
        if area > 0:
            found.append((other, area))
    return found


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------


def _check_overlap(placements: list[Placement]) -> list[Violation]:
    out = []
    for i, a in enumerate(placements):
        for b in placements[i + 1:]:
            shared = _volume_overlap(a, b)
            if shared > 0:
                out.append(
                    Violation(
                        "K1",
                        f"{a.sku}#{a.item_uid} and {b.sku}#{b.item_uid} share "
                        f"{shared / 1e9:.3f} m3",
                        (a.item_uid, b.item_uid),
                    )
                )
    return out


def _check_bounds(job: Job, placements: list[Placement]) -> list[Violation]:
    inner = job.vehicle.inner
    out = []
    for p in placements:
        x0, y0, z0, x1, y1, z1 = _extent(p)
        if x0 < 0 or y0 < 0 or z0 < 0:
            out.append(
                Violation("K2", f"{p.sku}#{p.item_uid} starts outside the vehicle "
                                f"at ({x0}, {y0}, {z0})", (p.item_uid,))
            )
        if x1 > inner.l or y1 > inner.w or z1 > inner.h:
            out.append(
                Violation("K2", f"{p.sku}#{p.item_uid} reaches ({x1}, {y1}, {z1}), "
                                f"past ({inner.l}, {inner.w}, {inner.h})", (p.item_uid,))
            )
    return out


def _check_payload(job: Job, placements: list[Placement]) -> list[Violation]:
    weights = {item.uid: item.weight_g for item in job.items}
    total = sum(weights[p.item_uid] for p in placements)
    limit = job.vehicle.max_payload_g
    if total > limit:
        return [
            Violation(
                "K3",
                f"loaded {total / 1e6:.2f} t against a {limit / 1e6:.2f} t limit",
            )
        ]
    return []


def _check_support(job: Job, placements: list[Placement]) -> list[Violation]:
    required = job.vehicle.min_support_ratio
    out = []
    for p in placements:
        if p.pos.z == 0:
            continue
        area = p.dims.footprint
        supported = sum(a for _, a in _supporters(p, placements))
        ratio = supported / area
        if ratio < required - 1e-9:
            out.append(
                Violation(
                    "K4",
                    f"{p.sku}#{p.item_uid} at z={p.pos.z} is {ratio:.0%} supported, "
                    f"needs {required:.0%}",
                    (p.item_uid,),
                )
            )
    return out


def _check_stacking(job: Job, placements: list[Placement]) -> list[Violation]:
    """Push every box's weight down onto whatever is holding it up.

    A box carries its own weight plus everything resting on it. Where several
    boxes share the support, the load is split by contact area -- a crude model
    of pressure distribution, but the alternative (ignoring it) would let a
    corner-resting stack look free.
    """
    types = {item.uid: item.type for item in job.items}
    weights = {item.uid: float(item.weight_g) for item in job.items}
    carried: dict[int, float] = {p.item_uid: 0.0 for p in placements}

    # Highest first, so a box's own load is final by the time it is passed down.
    for p in sorted(placements, key=lambda q: -q.pos.z):
        total = weights[p.item_uid] + carried[p.item_uid]
        supporters = _supporters(p, placements)
        area_total = sum(area for _, area in supporters)
        if area_total == 0:
            continue
        for other, area in supporters:
            carried[other.item_uid] += total * area / area_total

    out = []
    for p in placements:
        limit = types[p.item_uid].max_stack_weight_g
        if limit is None:
            continue
        load = carried[p.item_uid]
        if load > limit + 1e-6:
            out.append(
                Violation(
                    "K5",
                    f"{p.sku}#{p.item_uid} carries {load / 1e6:.2f} t, "
                    f"rated for {limit / 1e6:.2f} t",
                    (p.item_uid,),
                )
            )
    return out


def _check_orientation(job: Job, placements: list[Placement]) -> list[Violation]:
    types = {item.uid: item.type for item in job.items}
    out = []
    for p in placements:
        item_type = types[p.item_uid]
        if p.orientation not in item_type.allowed_orientations:
            out.append(
                Violation(
                    "K6",
                    f"{p.sku}#{p.item_uid} uses {p.orientation.name}, "
                    f"type allows {[o.name for o in item_type.allowed_orientations]}",
                    (p.item_uid,),
                )
            )
            continue
        expected = rotate(item_type.dims, p.orientation)
        if expected != p.dims:
            out.append(
                Violation(
                    "K6",
                    f"{p.sku}#{p.item_uid} claims {p.orientation.name} but its "
                    f"extents are {p.dims}, not {expected}",
                    (p.item_uid,),
                )
            )
    return out


def _check_centre_of_gravity(job: Job, placements: list[Placement]) -> list[Violation]:
    if not placements:
        return []
    weights = {item.uid: item.weight_g for item in job.items}
    inner = job.vehicle.inner
    total = sum(weights[p.item_uid] for p in placements)
    if total == 0:
        return []

    cx = sum(weights[p.item_uid] * (p.pos.x + p.dims.l / 2) for p in placements) / total
    cy = sum(weights[p.item_uid] * (p.pos.y + p.dims.w / 2) for p in placements) / total

    lateral = cy - inner.w / 2
    longitudinal = cx - inner.l / 2
    lateral_limit = job.vehicle.cog_lateral_tol_mm
    long_limit = job.vehicle.cog_long_tol_ratio * inner.l

    out = []
    if abs(lateral) > lateral_limit:
        out.append(
            Violation("K7", f"centre of gravity {lateral:+.0f} mm off centre "
                            f"sideways, tolerance {lateral_limit} mm")
        )
    if abs(longitudinal) > long_limit:
        out.append(
            Violation("K7", f"centre of gravity {longitudinal:+.0f} mm off centre "
                            f"lengthwise, tolerance {long_limit:.0f} mm")
        )
    return out


def _check_lifo(placements: list[Placement]) -> list[Violation]:
    """Nothing for a later stop may stand between a box and the doors.

    Doors are at the far end of the x axis, so "in front of" means a larger x.
    Only the straight-out path is modelled; freight stacked on top is a
    separate problem and is not counted here.
    """
    out = []
    for target in placements:
        for blocker in placements:
            if blocker.item_uid == target.item_uid:
                continue
            if blocker.stop <= target.stop:
                continue
            if blocker.pos.x < target.pos.x + target.dims.l:
                continue
            if _cross_section_overlap(target, blocker) == 0:
                continue
            out.append(
                Violation(
                    "K8",
                    f"{target.sku}#{target.item_uid} (stop {target.stop}) is "
                    f"blocked by {blocker.sku}#{blocker.item_uid} "
                    f"(stop {blocker.stop})",
                    (target.item_uid, blocker.item_uid),
                )
            )
    return out


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def validate(
    job: Job, plan: Plan, checks: tuple[str, ...] = ALL_CHECKS
) -> ValidationReport:
    """Audit ``plan`` against ``job``. Unknown check names raise."""
    unknown = set(checks) - set(ALL_CHECKS)
    if unknown:
        raise KeyError(f"unknown checks {sorted(unknown)}; have {list(ALL_CHECKS)}")
    if plan.job_id != job.job_id:
        raise ValueError(f"plan is for job {plan.job_id!r}, not {job.job_id!r}")

    known_uids = {item.uid for item in job.items}
    stray = [p.item_uid for p in plan.placements if p.item_uid not in known_uids]
    if stray:
        raise ValueError(f"plan places items that are not in the job: {stray}")

    placements = list(plan.placements)
    runners = {
        "K1": lambda: _check_overlap(placements),
        "K2": lambda: _check_bounds(job, placements),
        "K3": lambda: _check_payload(job, placements),
        "K4": lambda: _check_support(job, placements),
        "K5": lambda: _check_stacking(job, placements),
        "K6": lambda: _check_orientation(job, placements),
        "K7": lambda: _check_centre_of_gravity(job, placements),
        "K8": lambda: _check_lifo(placements),
    }

    violations: list[Violation] = []
    counts: dict[str, int] = {}
    for name in checks:
        found = runners[name]()
        counts[name] = len(found)
        violations.extend(found)

    return ValidationReport(violations=tuple(violations), counts=counts)
