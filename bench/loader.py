"""Parser for the OR-Library ``thpack`` container loading format.

One file holds many instances, each laid out as::

    <instance id> [<seed>]
    <container length> <container width> <container height>
    <number of box types>
    <type id> <d1> <v1> <d2> <v2> <d3> <v3> <count>      x number of types

The ``v`` flags say whether that dimension may point upwards. Rotation about
the vertical axis is always free in this benchmark, so a flag turns into a pair
of orientations: the two that put its dimension on the z axis.

Instances carry no weights. Boxes are given a nominal 1 g each and the vehicle
an unreachable payload limit, so K3 never binds and volume utilisation is
measured against volume alone -- which is what the published results report.

Coordinates are dimensionless integers here (BR uses centimetres, the small set
uses arbitrary units). The solver does not care; only the ratio matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.models import (
    ALL_ORIENTATIONS,
    Dims,
    Item,
    ItemType,
    Job,
    Orientation,
    Vehicle,
)

DATASET_DIR = Path("bench/datasets")

#: Friendly name -> file. BR1..BR7 grow from 3 to 20 box types, i.e. from
#: weakly to strongly heterogeneous cargo.
SETS: dict[str, str] = {
    "BR1": "thpack1.txt",
    "BR2": "thpack2.txt",
    "BR3": "thpack3.txt",
    "BR4": "thpack4.txt",
    "BR5": "thpack5.txt",
    "BR6": "thpack6.txt",
    "BR7": "thpack7.txt",
    "LN": "thpack8.txt",
    "SMALL": "thpack9.txt",
}

#: Which orientations put a given dimension on the vertical axis. Orientation
#: names read in axis order, so the third letter is the one standing up.
_VERTICAL: dict[str, tuple[Orientation, ...]] = {
    "l": (Orientation.WHL, Orientation.HWL),
    "w": (Orientation.LHW, Orientation.HLW),
    "h": (Orientation.LWH, Orientation.WLH),
}

#: Far beyond any instance's total box weight, so K3 never binds.
_UNLIMITED_PAYLOAD = 10**12


class MalformedInstance(ValueError):
    """A record in the source file does not match the documented layout."""


@dataclass(frozen=True, slots=True)
class Instance:
    """One benchmark problem, still in benchmark terms."""

    set_name: str
    number: int
    container: Dims
    #: (dims, allowed orientations, count) per box type.
    types: tuple[tuple[Dims, tuple[Orientation, ...], int], ...]

    @property
    def job_id(self) -> str:
        return f"{self.set_name}-{self.number:03d}"

    @property
    def total_boxes(self) -> int:
        return sum(count for _, _, count in self.types)

    def to_job(self, support_ratio: float = 0.0) -> Job:
        """Build a solvable job. ``support_ratio`` 0.0 disables the K4 check."""
        vehicle = Vehicle(
            code=self.set_name,
            name=f"{self.set_name} container",
            inner=self.container,
            max_payload_g=_UNLIMITED_PAYLOAD,
            min_support_ratio=support_ratio,
        )
        items = []
        uid = 0
        for index, (dims, orientations, count) in enumerate(self.types):
            item_type = ItemType(
                sku=f"B{index + 1}",
                name=f"box type {index + 1}",
                dims=dims,
                weight_g=1,
                allowed_orientations=orientations,
            )
            for _ in range(count):
                items.append(Item(uid=uid, type=item_type))
                uid += 1
        return Job(job_id=self.job_id, vehicle=vehicle, items=tuple(items))


@dataclass(frozen=True, slots=True)
class Dataset:
    """A parsed set, plus whatever had to be left out of it."""

    name: str
    instances: tuple[Instance, ...]
    #: Instance numbers dropped because the source record was malformed.
    skipped: tuple[int, ...] = ()

    def __len__(self) -> int:
        return len(self.instances)

    def __iter__(self):
        return iter(self.instances)


def _ints(line: str) -> list[int]:
    return [int(token) for token in line.split()]


def parse(text: str, set_name: str, strict: bool = True) -> Dataset:
    """Parse a whole thpack file.

    Parsed line by line rather than by flattening to a token stream: the
    instance header is one or two numbers depending on the file, and only the
    line structure says which.

    The shipped ``thpack9.txt`` contains at least one box-type line with a
    vertical flag missing, so the record cannot be read as documented. With
    ``strict`` the parse fails; without it the instance is dropped and its
    number recorded. It is never patched: guessing which flag went missing
    would put an invented instance into a benchmark table.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{set_name}: file is empty")

    cursor = 0
    expected = _ints(lines[cursor])[0]
    cursor += 1

    instances: list[Instance] = []
    skipped: list[int] = []
    seen = 0

    while cursor < len(lines) and seen < expected:
        number = _ints(lines[cursor])[0]
        cursor += 1
        seen += 1

        length, width, height = _ints(lines[cursor])[:3]
        cursor += 1

        type_count = _ints(lines[cursor])[0]
        cursor += 1

        types = []
        broken = False
        for _ in range(type_count):
            fields = _ints(lines[cursor])
            cursor += 1
            if len(fields) < 8:
                if strict:
                    raise MalformedInstance(
                        f"{set_name} instance {number}: expected 8 fields per box "
                        f"type, got {fields}. Re-run with strict=False (or "
                        f"--skip-malformed) to drop this instance."
                    )
                broken = True
                continue
            _, d1, v1, d2, v2, d3, v3, count = fields[:8]

            allowed: list[Orientation] = []
            for flag, axis in ((v1, "l"), (v2, "w"), (v3, "h")):
                if flag:
                    allowed.extend(_VERTICAL[axis])
            # No flag set would mean the box may not stand any way up; treat it
            # as unconstrained rather than silently dropping the type.
            orientations = tuple(dict.fromkeys(allowed)) or ALL_ORIENTATIONS

            types.append((Dims(l=d1, w=d2, h=d3), orientations, count))

        if broken:
            skipped.append(number)
            continue

        instances.append(
            Instance(
                set_name=set_name,
                number=number,
                container=Dims(l=length, w=width, h=height),
                types=tuple(types),
            )
        )

    if seen != expected:
        raise ValueError(
            f"{set_name}: header promises {expected} instances, found {seen}"
        )
    return Dataset(name=set_name, instances=tuple(instances), skipped=tuple(skipped))


def load_set(name: str, directory: Path = DATASET_DIR, strict: bool = True) -> Dataset:
    """Load one named set. Raises if it has not been fetched."""
    try:
        filename = SETS[name]
    except KeyError:
        raise KeyError(f"unknown set {name!r}; have {sorted(SETS)}") from None

    path = directory / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing -- run: python -m tools.fetch_datasets"
        )
    return parse(path.read_text(encoding="utf-8"), name, strict=strict)
