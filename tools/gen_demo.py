"""Generate synthetic loading jobs.

No customer data is used anywhere in this project. Demo jobs are drawn from the
catalogue in :mod:`core.catalog` with a seeded RNG, so a given seed always
produces the same job and results stay reproducible.

    python -m tools.gen_demo --vehicle TIR-1360 --mix mixed --fill 1.05 \
        --seed 42 --out data/demo/job-tir-mixed.json
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from core import catalog
from core.io import save_job
from core.models import Item, Job

#: Relative frequencies per scenario. Freight is not uniform: a pallet load has
#: few distinct types and many instances, a parcel load is the opposite.
MIXES: dict[str, dict[str, int]] = {
    "pallets": {"EUR-FULL": 5, "EUR-HALF": 3, "IND-FULL": 2, "DRUM-200L": 1},
    "cartons": {"BOX-L": 3, "BOX-M": 5, "BOX-S": 4},
    "mixed": {
        "EUR-FULL": 3,
        "EUR-HALF": 2,
        "IND-FULL": 1,
        "BOX-L": 3,
        "BOX-M": 4,
        "BOX-S": 3,
        "DRUM-200L": 1,
        "CRATE-FRAGILE": 1,
    },
}


def generate(
    vehicle_code: str = "TIR-1360",
    mix: str = "mixed",
    fill: float = 1.0,
    stops: int = 1,
    seed: int = 42,
    job_id: str | None = None,
) -> Job:
    """Draw items until the target volume is reached or the payload runs out.

    ``fill`` is a fraction of the vehicle's interior volume. Values above 1.0
    deliberately over-supply the job so the solver has to leave items behind --
    that exercises the ``unplaced`` path, which a perfectly sized job never does.
    """
    if mix not in MIXES:
        raise KeyError(f"unknown mix {mix!r}; have {sorted(MIXES)}")
    if stops < 1:
        raise ValueError("stops must be >= 1")

    rng = random.Random(seed)
    vehicle = catalog.vehicle(vehicle_code)

    skus = list(MIXES[mix])
    weights = [MIXES[mix][sku] for sku in skus]

    target_volume = int(vehicle.inner.volume * fill)
    # Boxes never tessellate perfectly, so filling to the payload limit exactly
    # would make weight the binding constraint in every single job. Leave slack.
    weight_cap = int(vehicle.max_payload_g * 0.95)

    items: list[Item] = []
    volume = 0
    weight = 0
    uid = 0

    while volume < target_volume:
        sku = rng.choices(skus, weights=weights, k=1)[0]
        item_type = catalog.item_type(sku)
        if weight + item_type.weight_g > weight_cap:
            # Heavy type does not fit any more; try a lighter one a few times
            # before declaring the job full.
            if all(
                weight + catalog.item_type(s).weight_g > weight_cap for s in skus
            ):
                break
            continue
        items.append(Item(uid=uid, type=item_type, stop=1 + uid % stops))
        volume += item_type.dims.volume
        weight += item_type.weight_g
        uid += 1

    return Job(
        job_id=job_id or f"{vehicle_code}-{mix}-s{seed}",
        vehicle=vehicle,
        items=tuple(items),
    )


def _summary(job: Job) -> str:
    inner = job.vehicle.inner.volume
    return (
        f"{job.job_id}: {len(job.items)} items, "
        f"{job.total_volume / inner:.0%} of interior volume, "
        f"{job.total_weight_g / job.vehicle.max_payload_g:.0%} of payload"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic LoadZa job")
    parser.add_argument("--vehicle", default="TIR-1360", choices=sorted(catalog.VEHICLES))
    parser.add_argument("--mix", default="mixed", choices=sorted(MIXES))
    parser.add_argument("--fill", type=float, default=1.0,
                        help="target volume as a fraction of the interior")
    parser.add_argument("--stops", type=int, default=1,
                        help="number of delivery stops (multi-drop lands in F4)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    job = generate(
        vehicle_code=args.vehicle,
        mix=args.mix,
        fill=args.fill,
        stops=args.stops,
        seed=args.seed,
        job_id=args.job_id,
    )

    out = args.out or Path("data/demo") / f"{job.job_id}.json"
    save_job(job, out)
    print(_summary(job))
    print(f"written to {out}")


if __name__ == "__main__":
    main()
