"""Integer geometry and the spatial index the solver queries.

A box is a plain 6-tuple ``(x0, y0, z0, x1, y1, z1)`` of millimetres rather than
a dataclass: the solver evaluates hundreds of thousands of candidates and tuple
indexing is several times cheaper than attribute access.

Everything here is exact integer arithmetic. Touching faces do not count as
overlapping -- two boxes sharing a plane is exactly what a tight load looks
like.
"""

from __future__ import annotations

from collections.abc import Iterator

from core.models import Dims, Orientation, Pos, rotate

#: ``(x0, y0, z0, x1, y1, z1)``, half-open: the box occupies ``[x0, x1)``.
Box = tuple[int, int, int, int, int, int]


def make_box(pos: Pos, dims: Dims) -> Box:
    return (pos.x, pos.y, pos.z, pos.x + dims.l, pos.y + dims.w, pos.z + dims.h)


def box_pos(b: Box) -> Pos:
    return Pos(b[0], b[1], b[2])


def box_dims(b: Box) -> Dims:
    return Dims(b[3] - b[0], b[4] - b[1], b[5] - b[2])


def box_volume(b: Box) -> int:
    return (b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2])


def overlaps(a: Box, b: Box) -> bool:
    """True if the two boxes share interior volume. Touching is allowed."""
    return (
        a[0] < b[3] and b[0] < a[3]
        and a[1] < b[4] and b[1] < a[4]
        and a[2] < b[5] and b[2] < a[5]
    )


def inside(b: Box, inner: Dims) -> bool:
    return (
        b[0] >= 0 and b[1] >= 0 and b[2] >= 0
        and b[3] <= inner.l and b[4] <= inner.w and b[5] <= inner.h
    )


def overlap_area_xy(a: Box, b: Box) -> int:
    """Footprint overlap of two boxes, ignoring height."""
    dx = min(a[3], b[3]) - max(a[0], b[0])
    if dx <= 0:
        return 0
    dy = min(a[4], b[4]) - max(a[1], b[1])
    return dx * dy if dy > 0 else 0


def face_contact_area(a: Box, b: Box) -> int:
    """Area of the shared face between two touching boxes, 0 if not touching."""
    if a[3] == b[0] or b[3] == a[0]:
        dy = min(a[4], b[4]) - max(a[1], b[1])
        dz = min(a[5], b[5]) - max(a[2], b[2])
        return dy * dz if dy > 0 and dz > 0 else 0
    if a[4] == b[1] or b[4] == a[1]:
        dx = min(a[3], b[3]) - max(a[0], b[0])
        dz = min(a[5], b[5]) - max(a[2], b[2])
        return dx * dz if dx > 0 and dz > 0 else 0
    if a[5] == b[2] or b[5] == a[2]:
        return overlap_area_xy(a, b)
    return 0


def distinct_orientations(
    dims: Dims, allowed: tuple[Orientation, ...]
) -> tuple[tuple[Orientation, Dims], ...]:
    """Drop orientations that produce identical extents.

    A 600x600x880 drum has six nominal orientations but only three distinct
    shapes. Skipping the duplicates cuts the search by a third for free.
    """
    seen: dict[tuple[int, int, int], tuple[Orientation, Dims]] = {}
    for orientation in allowed:
        rotated = rotate(dims, orientation)
        seen.setdefault((rotated.l, rotated.w, rotated.h), (orientation, rotated))
    return tuple(seen.values())


class SpatialIndex:
    """Uniform grid over the loading space.

    Collision queries are the solver's hot path. A linear scan over every placed
    box costs O(n) per query and the solver makes O(items x points x
    orientations) of them; bucketing by cell keeps each query to the handful of
    boxes that could possibly be in the way.
    """

    __slots__ = ("cell", "_cells", "_boxes")

    def __init__(self, cell: int = 1000) -> None:
        if cell <= 0:
            raise ValueError("cell size must be positive")
        self.cell = cell
        self._cells: dict[tuple[int, int, int], list[int]] = {}
        self._boxes: list[Box] = []

    def __len__(self) -> int:
        return len(self._boxes)

    @property
    def boxes(self) -> list[Box]:
        return self._boxes

    def _span(self, b: Box) -> Iterator[tuple[int, int, int]]:
        c = self.cell
        for i in range(b[0] // c, (max(b[3], b[0] + 1) - 1) // c + 1):
            for j in range(b[1] // c, (max(b[4], b[1] + 1) - 1) // c + 1):
                for k in range(b[2] // c, (max(b[5], b[2] + 1) - 1) // c + 1):
                    yield (i, j, k)

    def add(self, b: Box) -> int:
        index = len(self._boxes)
        self._boxes.append(b)
        for key in self._span(b):
            self._cells.setdefault(key, []).append(index)
        return index

    def nearby(self, b: Box) -> set[int]:
        found: set[int] = set()
        for key in self._span(b):
            bucket = self._cells.get(key)
            if bucket:
                found.update(bucket)
        return found

    def collides(self, b: Box) -> bool:
        boxes = self._boxes
        for i in self.nearby(b):
            if overlaps(b, boxes[i]):
                return True
        return False

    def settle(self, b: Box) -> Box:
        """Drop the box straight down until it rests on the floor or a box.

        Extreme points sit at the corners of placed boxes, so a candidate often
        starts higher than it needs to be. Settling turns those into supported
        placements instead of floating ones, and it is what stops the 3D view
        from showing boxes hovering in mid-air.
        """
        x0, y0, z0, x1, y1, z1 = b
        if z0 == 0:
            return b
        probe = (x0, y0, 0, x1, y1, z0)
        rest = 0
        boxes = self._boxes
        for i in self.nearby(probe):
            other = boxes[i]
            if other[5] <= z0 and other[5] > rest and overlap_area_xy(b, other) > 0:
                rest = other[5]
        if rest == z0:
            return b
        return (x0, y0, rest, x1, y1, rest + (z1 - z0))

    def support_ratio(self, b: Box) -> float:
        """Fraction of the box footprint resting on the floor or other boxes."""
        if b[2] == 0:
            return 1.0
        area = (b[3] - b[0]) * (b[4] - b[1])
        if area == 0:
            return 0.0
        probe = (b[0], b[1], max(b[2] - 1, 0), b[3], b[4], b[2] + 1)
        supported = 0
        boxes = self._boxes
        for i in self.nearby(probe):
            other = boxes[i]
            if other[5] == b[2]:
                supported += overlap_area_xy(b, other)
        return supported / area

    def contact_area(self, b: Box, inner: Dims) -> int:
        """Total area of faces touching a wall, the floor or another box.

        Used by the ``contact`` placement scorer: a box wedged against its
        neighbours is a box that will not shift in transit.
        """
        width_h = (b[4] - b[1]) * (b[5] - b[2])
        length_h = (b[3] - b[0]) * (b[5] - b[2])
        total = 0
        if b[0] == 0:
            total += width_h
        if b[3] == inner.l:
            total += width_h
        if b[1] == 0:
            total += length_h
        if b[4] == inner.w:
            total += length_h
        if b[2] == 0:
            total += (b[3] - b[0]) * (b[4] - b[1])

        probe = (
            max(b[0] - 1, 0), max(b[1] - 1, 0), max(b[2] - 1, 0),
            b[3] + 1, b[4] + 1, b[5] + 1,
        )
        boxes = self._boxes
        for i in self.nearby(probe):
            total += face_contact_area(b, boxes[i])
        return total

    def contains_point(self, p: Pos) -> bool:
        """True if the point lies strictly inside an already placed box."""
        probe = (p.x, p.y, p.z, p.x + 1, p.y + 1, p.z + 1)
        return self.collides(probe)
