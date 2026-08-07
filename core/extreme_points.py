"""Candidate position pool for the placement heuristic.

Extreme points, after Crainic, Perboli and Tadei (2008). The loading space
starts with a single candidate at the origin. Every placed box contributes
three new ones -- past its far end, past its right side, and on top of it -- so
the pool tracks exactly the corners where the next box could sit flush against
what is already loaded.

Points that end up buried inside a later box are dead weight; they are pruned
lazily rather than eagerly, because pruning costs a collision query per point
and most points are consumed long before they need it.
"""

from __future__ import annotations

from core.geometry import Box, SpatialIndex
from core.models import Pos


class ExtremePoints:
    """An ordered, de-duplicated pool of candidate corners."""

    __slots__ = ("_points", "_seen")

    def __init__(self) -> None:
        origin = (0, 0, 0)
        self._points: list[tuple[int, int, int]] = [origin]
        self._seen: set[tuple[int, int, int]] = {origin}

    def __len__(self) -> int:
        return len(self._points)

    def add_from_box(self, b: Box) -> None:
        """Register the three corners opened up by a newly placed box."""
        for point in ((b[3], b[1], b[2]), (b[0], b[4], b[2]), (b[0], b[1], b[5])):
            if point not in self._seen:
                self._seen.add(point)
                self._points.append(point)

    def prune(self, index: SpatialIndex) -> int:
        """Drop points now swallowed by a placed box. Returns how many went."""
        kept = [p for p in self._points if not index.contains_point(Pos(*p))]
        removed = len(self._points) - len(kept)
        self._points = kept
        return removed

    def ordered(self, order: str = "dbl", limit: int | None = None) -> list[Pos]:
        """Candidates ranked by the chosen strategy, best first."""
        try:
            key = POINT_ORDERS[order]
        except KeyError:
            raise KeyError(
                f"unknown point order {order!r}; have {sorted(POINT_ORDERS)}"
            ) from None
        points = sorted(self._points, key=key)
        if limit is not None and len(points) > limit:
            points = points[:limit]
        return [Pos(*p) for p in points]


#: How candidate points are ranked. ``dbl`` walks the load from the closed end
#: towards the doors, which is the physical loading order; ``layer`` finishes a
#: floor level before starting the next one, which suits uniform cartons.
POINT_ORDERS = {
    "dbl": lambda p: (p[0], p[1], p[2]),
    "layer": lambda p: (p[2], p[0], p[1]),
}

