"""Vehicle and item-type catalogue.

Vehicle figures are published container/trailer specifications, not customer
data. Truck payload follows the Turkish 40 t gross weight limit minus a typical
tractor + trailer tare of about 16 t.

Item types model common European unit loads. They exist so that generated demo
jobs look like real freight rather than random cubes.
"""

from __future__ import annotations

from core.models import Access, Dims, ItemType, Vehicle

VEHICLES: dict[str, Vehicle] = {
    "TIR-1360": Vehicle(
        code="TIR-1360",
        name="13.60 m curtainside semi-trailer",
        inner=Dims(l=13600, w=2480, h=2700),
        max_payload_g=24_000_000,
        access=Access.SIDE,
    ),
    "CNT-20DV": Vehicle(
        code="CNT-20DV",
        name="20 ft dry van container",
        inner=Dims(l=5898, w=2352, h=2393),
        max_payload_g=28_230_000,
        access=Access.REAR,
    ),
    "CNT-40DV": Vehicle(
        code="CNT-40DV",
        name="40 ft dry van container",
        inner=Dims(l=12032, w=2352, h=2393),
        max_payload_g=26_740_000,
        access=Access.REAR,
    ),
    "CNT-40HC": Vehicle(
        code="CNT-40HC",
        name="40 ft high cube container",
        inner=Dims(l=12032, w=2352, h=2698),
        max_payload_g=26_580_000,
        access=Access.REAR,
    ),
}


ITEM_TYPES: dict[str, ItemType] = {
    "EUR-FULL": ItemType(
        sku="EUR-FULL",
        name="Euro pallet, full height",
        dims=Dims(l=1200, w=800, h=1450),
        weight_g=620_000,
        max_stack_weight_g=600_000,
        this_side_up=True,
    ),
    "EUR-HALF": ItemType(
        sku="EUR-HALF",
        name="Euro pallet, half height",
        dims=Dims(l=1200, w=800, h=750),
        weight_g=310_000,
        max_stack_weight_g=900_000,
        this_side_up=True,
    ),
    "IND-FULL": ItemType(
        sku="IND-FULL",
        name="Industrial pallet, full height",
        dims=Dims(l=1200, w=1000, h=1450),
        weight_g=780_000,
        max_stack_weight_g=700_000,
        this_side_up=True,
    ),
    "BOX-L": ItemType(
        sku="BOX-L",
        name="Large carton",
        dims=Dims(l=800, w=600, h=600),
        weight_g=45_000,
        max_stack_weight_g=180_000,
    ),
    "BOX-M": ItemType(
        sku="BOX-M",
        name="Medium carton",
        dims=Dims(l=600, w=400, h=400),
        weight_g=18_000,
        max_stack_weight_g=120_000,
    ),
    "BOX-S": ItemType(
        sku="BOX-S",
        name="Small carton",
        dims=Dims(l=400, w=300, h=300),
        weight_g=7_000,
        max_stack_weight_g=90_000,
    ),
    "CRATE-FRAGILE": ItemType(
        sku="CRATE-FRAGILE",
        name="Fragile glass crate",
        dims=Dims(l=1150, w=750, h=1100),
        weight_g=340_000,
        fragile=True,
        max_stack_weight_g=0,
        this_side_up=True,
    ),
    "DRUM-200L": ItemType(
        sku="DRUM-200L",
        name="200 L steel drum",
        dims=Dims(l=600, w=600, h=880),
        weight_g=210_000,
        max_stack_weight_g=420_000,
        this_side_up=True,
    ),
}


def vehicle(code: str) -> Vehicle:
    try:
        return VEHICLES[code]
    except KeyError:
        raise KeyError(f"unknown vehicle code {code!r}; have {sorted(VEHICLES)}") from None


def item_type(sku: str) -> ItemType:
    try:
        return ITEM_TYPES[sku]
    except KeyError:
        raise KeyError(f"unknown sku {sku!r}; have {sorted(ITEM_TYPES)}") from None
