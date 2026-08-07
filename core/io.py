"""JSON serialisation for jobs and plans.

The wire format is the contract between the solver, the HTTP layer (F6) and the
3-D viewer (F7), so it is defined here once and kept boring: plain dicts, plain
ints, no framework types.

A job file may reference catalogue entries by code/sku, or inline a full
definition. Inline definitions win, which keeps benchmark files (that have their
own box sets) self-contained.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import catalog
from core.models import (
    ALL_ORIENTATIONS,
    Access,
    Dims,
    Item,
    ItemType,
    Job,
    Metrics,
    Orientation,
    Placement,
    Plan,
    Pos,
    Unplaced,
    Vehicle,
)


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


def _dims_to_dict(d: Dims) -> dict[str, int]:
    return {"length": d.l, "width": d.w, "height": d.h}


def _dims_from_dict(raw: dict[str, Any]) -> Dims:
    return Dims(l=int(raw["length"]), w=int(raw["width"]), h=int(raw["height"]))


# --------------------------------------------------------------------------
# vehicle / item type
# --------------------------------------------------------------------------


def vehicle_to_dict(v: Vehicle) -> dict[str, Any]:
    return {
        "code": v.code,
        "name": v.name,
        "inner_mm": _dims_to_dict(v.inner),
        "max_payload_g": v.max_payload_g,
        "access": v.access.value,
        "cog_lateral_tol_mm": v.cog_lateral_tol_mm,
        "cog_long_tol_ratio": v.cog_long_tol_ratio,
        "min_support_ratio": v.min_support_ratio,
    }


def vehicle_from_dict(raw: dict[str, Any]) -> Vehicle:
    """Resolve a vehicle. ``{"code": "TIR-1360"}`` alone hits the catalogue."""
    if "inner_mm" not in raw:
        return catalog.vehicle(raw["code"])
    return Vehicle(
        code=raw["code"],
        name=raw.get("name", raw["code"]),
        inner=_dims_from_dict(raw["inner_mm"]),
        max_payload_g=int(raw["max_payload_g"]),
        access=Access(raw.get("access", Access.REAR.value)),
        cog_lateral_tol_mm=int(raw.get("cog_lateral_tol_mm", 100)),
        cog_long_tol_ratio=float(raw.get("cog_long_tol_ratio", 0.10)),
        min_support_ratio=float(raw.get("min_support_ratio", 0.70)),
    )


def item_type_to_dict(t: ItemType) -> dict[str, Any]:
    return {
        "sku": t.sku,
        "name": t.name,
        "dims_mm": _dims_to_dict(t.dims),
        "weight_g": t.weight_g,
        "fragile": t.fragile,
        "max_stack_weight_g": t.max_stack_weight_g,
        "allowed_orientations": [o.name for o in t.allowed_orientations],
        "this_side_up": t.this_side_up,
    }


def item_type_from_dict(raw: dict[str, Any]) -> ItemType:
    orientations = raw.get("allowed_orientations")
    return ItemType(
        sku=raw["sku"],
        name=raw.get("name", raw["sku"]),
        dims=_dims_from_dict(raw["dims_mm"]),
        weight_g=int(raw["weight_g"]),
        fragile=bool(raw.get("fragile", False)),
        max_stack_weight_g=(
            None if raw.get("max_stack_weight_g") is None
            else int(raw["max_stack_weight_g"])
        ),
        allowed_orientations=(
            ALL_ORIENTATIONS if orientations is None
            else tuple(Orientation[name] for name in orientations)
        ),
        this_side_up=bool(raw.get("this_side_up", False)),
    )


# --------------------------------------------------------------------------
# job
# --------------------------------------------------------------------------


def job_to_dict(job: Job) -> dict[str, Any]:
    """Collapse item instances back into ``sku`` + ``qty`` lines per stop.

    Each line carries the ``uid`` of every instance it stands for. Without them
    a round trip renumbers the items, and since placements refer to items by
    uid, a plan would silently come to describe different boxes than the ones
    it was computed for.
    """
    types: dict[str, ItemType] = {}
    lines: dict[tuple[str, int], list[int]] = {}
    for item in job.items:
        types.setdefault(item.type.sku, item.type)
        lines.setdefault((item.type.sku, item.stop), []).append(item.uid)

    return {
        "job_id": job.job_id,
        "vehicle": vehicle_to_dict(job.vehicle),
        "item_types": [item_type_to_dict(t) for t in types.values()],
        "items": [
            {"sku": sku, "qty": len(uids), "stop": stop, "uids": uids}
            for (sku, stop), uids in lines.items()
        ],
    }


def job_from_dict(raw: dict[str, Any]) -> Job:
    """Rebuild a job. ``uids`` are honoured when present, assigned when not.

    Hand-written and benchmark-derived job files legitimately omit them; only
    documents this module produced carry them.
    """
    inline = {
        entry["sku"]: item_type_from_dict(entry)
        for entry in raw.get("item_types", [])
    }

    items: list[Item] = []
    next_uid = 0
    for line in raw["items"]:
        sku = line["sku"]
        item_type = inline.get(sku) or catalog.item_type(sku)
        stop = int(line.get("stop", 1))
        uids = line.get("uids")
        if uids is None:
            uids = list(range(next_uid, next_uid + int(line.get("qty", 1))))
        elif len(uids) != int(line.get("qty", len(uids))):
            raise ValueError(
                f"{sku}: {len(uids)} uids for a quantity of {line['qty']}"
            )
        for uid in uids:
            items.append(Item(uid=int(uid), type=item_type, stop=stop))
        next_uid = max(next_uid, max(uids) + 1) if uids else next_uid

    seen = [item.uid for item in items]
    if len(set(seen)) != len(seen):
        raise ValueError("duplicate item uids in job document")

    return Job(
        job_id=raw["job_id"],
        vehicle=vehicle_from_dict(raw["vehicle"]),
        items=tuple(items),
    )


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def placement_to_dict(p: Placement) -> dict[str, Any]:
    return {
        "seq": p.seq,
        "item_uid": p.item_uid,
        "sku": p.sku,
        "pos_mm": {"x": p.pos.x, "y": p.pos.y, "z": p.pos.z},
        "dims_mm": _dims_to_dict(p.dims),
        "orientation": p.orientation.name,
        "stop": p.stop,
    }


def placement_from_dict(raw: dict[str, Any]) -> Placement:
    pos = raw["pos_mm"]
    return Placement(
        seq=int(raw["seq"]),
        item_uid=int(raw["item_uid"]),
        sku=raw["sku"],
        pos=Pos(x=int(pos["x"]), y=int(pos["y"]), z=int(pos["z"])),
        dims=_dims_from_dict(raw["dims_mm"]),
        orientation=Orientation[raw["orientation"]],
        stop=int(raw.get("stop", 1)),
    )


def metrics_to_dict(m: Metrics) -> dict[str, Any]:
    return {
        "volume_utilization": m.volume_utilization,
        "weight_utilization": m.weight_utilization,
        "placed": m.placed,
        "unplaced": m.unplaced,
        "cog_lateral_mm": m.cog_lateral_mm,
        "cog_longitudinal_mm": m.cog_longitudinal_mm,
        "solve_ms": m.solve_ms,
        "violations": dict(m.violations),
    }


def metrics_from_dict(raw: dict[str, Any]) -> Metrics:
    return Metrics(
        volume_utilization=float(raw["volume_utilization"]),
        weight_utilization=float(raw["weight_utilization"]),
        placed=int(raw["placed"]),
        unplaced=int(raw["unplaced"]),
        cog_lateral_mm=int(raw["cog_lateral_mm"]),
        cog_longitudinal_mm=int(raw["cog_longitudinal_mm"]),
        solve_ms=int(raw["solve_ms"]),
        violations=dict(raw.get("violations", {})),
    )


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "job_id": plan.job_id,
        "algorithm": plan.algorithm,
        "vehicle": vehicle_to_dict(plan.vehicle),
        "metrics": None if plan.metrics is None else metrics_to_dict(plan.metrics),
        "placements": [placement_to_dict(p) for p in plan.placements],
        "unplaced": [
            {"item_uid": u.item_uid, "sku": u.sku, "reason": u.reason}
            for u in plan.unplaced
        ],
    }


def plan_from_dict(raw: dict[str, Any]) -> Plan:
    metrics = raw.get("metrics")
    return Plan(
        plan_id=raw["plan_id"],
        job_id=raw["job_id"],
        vehicle=vehicle_from_dict(raw["vehicle"]),
        algorithm=raw["algorithm"],
        placements=tuple(placement_from_dict(p) for p in raw["placements"]),
        unplaced=tuple(
            Unplaced(item_uid=int(u["item_uid"]), sku=u["sku"], reason=u["reason"])
            for u in raw.get("unplaced", [])
        ),
        metrics=None if metrics is None else metrics_from_dict(metrics),
    )


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def _write(path: str | Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def load_job(path: str | Path) -> Job:
    return job_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_job(job: Job, path: str | Path) -> Path:
    return _write(path, job_to_dict(job))


def load_plan(path: str | Path) -> Plan:
    return plan_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_plan(plan: Plan, path: str | Path) -> Path:
    return _write(path, plan_to_dict(plan))
