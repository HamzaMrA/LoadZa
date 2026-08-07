"""Core domain model for LoadZa.

Design rules (see Obsidian note "LoadZa - Veri Modeli"):

* All lengths are millimetres and all weights are grams, stored as ``int``.
  Floating point is never used for geometry: overlap tests must be exact.
* Coordinate system: origin is the rear-left-bottom corner of the vehicle.
  ``x`` runs along the vehicle length (door -> cab), ``y`` across the width
  (left -> right), ``z`` upwards.
* Every type is a frozen dataclass. The solver copies and replaces, it never
  mutates in place -- that keeps search backtracking free of aliasing bugs.
* This module has no dependency on the database, the HTTP layer or numpy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

Mm = int
Gram = int


class Orientation(IntEnum):
    """Which original (length, width, height) maps onto the (x, y, z) axes.

    The three letters read in axis order: ``LWH`` means length->x, width->y,
    height->z, i.e. the box standing the way it was measured.
    """

    LWH = 0
    WLH = 1
    LHW = 2
    HLW = 3
    WHL = 4
    HWL = 5


ALL_ORIENTATIONS: tuple[Orientation, ...] = tuple(Orientation)

#: Orientations that keep the original height on the z axis. Used for boxes
#: flagged ``this_side_up``.
UPRIGHT_ORIENTATIONS: tuple[Orientation, ...] = (Orientation.LWH, Orientation.WLH)


class Access(StrEnum):
    """How the vehicle can be loaded.

    Unused until phase F4 (multi-drop LIFO); until then every vehicle is
    treated as rear-loading.
    """

    REAR = "rear"
    SIDE = "side"


@dataclass(frozen=True, slots=True)
class Dims:
    """Axis-aligned extents in millimetres."""

    l: Mm
    w: Mm
    h: Mm

    def __post_init__(self) -> None:
        if self.l <= 0 or self.w <= 0 or self.h <= 0:
            raise ValueError(f"dimensions must be positive, got {self!r}")

    @property
    def volume(self) -> int:
        return self.l * self.w * self.h

    @property
    def footprint(self) -> int:
        return self.l * self.w


@dataclass(frozen=True, slots=True)
class Pos:
    """A point in vehicle space, millimetres from the rear-left-bottom corner."""

    x: Mm
    y: Mm
    z: Mm


def rotate(dims: Dims, orientation: Orientation) -> Dims:
    """Return ``dims`` expressed along the (x, y, z) axes for ``orientation``."""
    l, w, h = dims.l, dims.w, dims.h
    match orientation:
        case Orientation.LWH:
            return Dims(l, w, h)
        case Orientation.WLH:
            return Dims(w, l, h)
        case Orientation.LHW:
            return Dims(l, h, w)
        case Orientation.HLW:
            return Dims(h, l, w)
        case Orientation.WHL:
            return Dims(w, h, l)
        case Orientation.HWL:
            return Dims(h, w, l)
    raise ValueError(f"unknown orientation: {orientation!r}")


@dataclass(frozen=True, slots=True)
class ItemType:
    """A kind of box. Dimensions and rules live here, not on each instance."""

    sku: str
    name: str
    dims: Dims
    weight_g: Gram
    fragile: bool = False
    #: Total weight the box can carry on top of it. ``None`` means unlimited,
    #: which disables the K5 stacking check for this type. We do not invent a
    #: limit when the data does not provide one.
    max_stack_weight_g: Gram | None = None
    allowed_orientations: tuple[Orientation, ...] = ALL_ORIENTATIONS
    this_side_up: bool = False

    def __post_init__(self) -> None:
        if self.weight_g <= 0:
            raise ValueError(f"{self.sku}: weight must be positive")
        if self.this_side_up:
            allowed = tuple(
                o for o in self.allowed_orientations if o in UPRIGHT_ORIENTATIONS
            )
            if not allowed:
                raise ValueError(f"{self.sku}: this_side_up leaves no orientation")
            object.__setattr__(self, "allowed_orientations", allowed)


@dataclass(frozen=True, slots=True)
class Item:
    """One physical instance of an :class:`ItemType`."""

    uid: int
    type: ItemType
    #: Delivery stop index, 1-based. Single-drop (always 1) until phase F4.
    stop: int = 1

    @property
    def sku(self) -> str:
        return self.type.sku

    @property
    def weight_g(self) -> Gram:
        return self.type.weight_g


@dataclass(frozen=True, slots=True)
class Vehicle:
    """Loading space plus the physical limits that constrain a plan."""

    code: str
    name: str
    inner: Dims
    max_payload_g: Gram
    access: Access = Access.REAR
    #: K7 -- centre of gravity tolerance, sideways, in millimetres.
    cog_lateral_tol_mm: Mm = 100
    #: K7 -- lengthwise tolerance as a fraction of the loading length.
    cog_long_tol_ratio: float = 0.10
    #: K4 -- minimum fraction of a box footprint that must rest on something.
    min_support_ratio: float = 0.70


@dataclass(frozen=True, slots=True)
class Placement:
    """One box, positioned and oriented inside the vehicle."""

    seq: int
    item_uid: int
    sku: str
    pos: Pos
    #: Already rotated: consumers (validator, viewer) must not rotate again.
    dims: Dims
    orientation: Orientation
    stop: int = 1

    @property
    def max_corner(self) -> Pos:
        return Pos(
            self.pos.x + self.dims.l,
            self.pos.y + self.dims.w,
            self.pos.z + self.dims.h,
        )

    @property
    def volume(self) -> int:
        return self.dims.volume


@dataclass(frozen=True, slots=True)
class Unplaced:
    """An item the solver could not fit, with the reason it gave up."""

    item_uid: int
    sku: str
    reason: str


@dataclass(frozen=True, slots=True)
class Metrics:
    """Quality of a plan. Produced by ``core.metrics``, never by the solver."""

    volume_utilization: float
    weight_utilization: float
    placed: int
    unplaced: int
    cog_lateral_mm: Mm
    cog_longitudinal_mm: Mm
    solve_ms: int
    #: Violation counts keyed by constraint id, e.g. ``{"K1": 0, "K4": 2}``.
    violations: dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return all(count == 0 for count in self.violations.values())


@dataclass(frozen=True, slots=True)
class Job:
    """A loading problem: these items into this vehicle."""

    job_id: str
    vehicle: Vehicle
    items: tuple[Item, ...]

    @property
    def total_volume(self) -> int:
        return sum(item.type.dims.volume for item in self.items)

    @property
    def total_weight_g(self) -> Gram:
        return sum(item.weight_g for item in self.items)


@dataclass(frozen=True, slots=True)
class Plan:
    """A solved job. Carries its own vehicle so the JSON is self-contained."""

    plan_id: str
    job_id: str
    vehicle: Vehicle
    algorithm: str
    placements: tuple[Placement, ...]
    unplaced: tuple[Unplaced, ...] = ()
    metrics: Metrics | None = None
