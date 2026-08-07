"""SQLite persistence for jobs and plans.

Plain ``sqlite3``, no ORM. The schema is six small tables and the queries are
all single-table; an ORM would add a dependency and a layer of indirection to
save about forty lines.

Placements are stored one row per box rather than as a JSON blob. A plan for a
234-box load is 234 rows, which SQLite does not notice, and it means the
comparison view can aggregate in SQL instead of parsing every plan it lists.

Item types are upserted on save. A job may carry inline definitions that are not
in the catalogue -- benchmark instances do -- and those have to survive a
round trip.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.io import item_type_from_dict, item_type_to_dict, vehicle_from_dict, vehicle_to_dict
from core.models import (
    Dims,
    Item,
    Job,
    Metrics,
    Orientation,
    Placement,
    Plan,
    Pos,
    Unplaced,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicle_type (
    code          TEXT PRIMARY KEY,
    spec_json     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_type (
    sku           TEXT PRIMARY KEY,
    spec_json     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    id            TEXT PRIMARY KEY,
    vehicle_code  TEXT NOT NULL REFERENCES vehicle_type(code),
    created_at    TEXT NOT NULL,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS job_item (
    id            INTEGER PRIMARY KEY,
    job_id        TEXT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    uid           INTEGER NOT NULL,
    sku           TEXT NOT NULL REFERENCES item_type(sku),
    stop          INTEGER NOT NULL DEFAULT 1,
    UNIQUE (job_id, uid)
);

CREATE TABLE IF NOT EXISTS plan (
    id                  TEXT PRIMARY KEY,
    job_id              TEXT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    algorithm           TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    volume_utilization  REAL,
    weight_utilization  REAL,
    placed              INTEGER,
    unplaced            INTEGER,
    cog_lateral_mm      INTEGER,
    cog_longitudinal_mm INTEGER,
    solve_ms            INTEGER,
    violations_json     TEXT,
    unplaced_json       TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS placement (
    id            INTEGER PRIMARY KEY,
    plan_id       TEXT NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    item_uid      INTEGER NOT NULL,
    sku           TEXT NOT NULL,
    x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
    l INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL,
    orientation   TEXT NOT NULL,
    stop          INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS placement_by_plan ON placement(plan_id, seq);
CREATE INDEX IF NOT EXISTS plan_by_job ON plan(job_id, created_at);
"""


class NotFound(LookupError):
    """Asked for a job or plan that is not in the database."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Everything that touches the database. The API layer holds one of these."""

    def __init__(self, path: str | Path = "data/loadza.sqlite") -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialise(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    # -- jobs ------------------------------------------------------------

    def save_job(self, job: Job, note: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO vehicle_type (code, spec_json) VALUES (?, ?)",
                (job.vehicle.code, json.dumps(vehicle_to_dict(job.vehicle))),
            )
            for item_type in {item.type.sku: item.type for item in job.items}.values():
                connection.execute(
                    "INSERT OR REPLACE INTO item_type (sku, spec_json) VALUES (?, ?)",
                    (item_type.sku, json.dumps(item_type_to_dict(item_type))),
                )
            connection.execute(
                "INSERT OR REPLACE INTO job (id, vehicle_code, created_at, note) "
                "VALUES (?, ?, ?, ?)",
                (job.job_id, job.vehicle.code, _now(), note),
            )
            connection.execute("DELETE FROM job_item WHERE job_id = ?", (job.job_id,))
            connection.executemany(
                "INSERT INTO job_item (job_id, uid, sku, stop) VALUES (?, ?, ?, ?)",
                [(job.job_id, item.uid, item.type.sku, item.stop) for item in job.items],
            )

    def load_job(self, job_id: str) -> Job:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT vehicle_code FROM job WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"no job {job_id!r}")

            vehicle_row = connection.execute(
                "SELECT spec_json FROM vehicle_type WHERE code = ?", (row["vehicle_code"],)
            ).fetchone()
            vehicle = vehicle_from_dict(json.loads(vehicle_row["spec_json"]))

            types = {
                r["sku"]: item_type_from_dict(json.loads(r["spec_json"]))
                for r in connection.execute("SELECT sku, spec_json FROM item_type")
            }
            items = tuple(
                Item(uid=r["uid"], type=types[r["sku"]], stop=r["stop"])
                for r in connection.execute(
                    "SELECT uid, sku, stop FROM job_item WHERE job_id = ? ORDER BY uid",
                    (job_id,),
                )
            )
        return Job(job_id=job_id, vehicle=vehicle, items=items)

    def list_jobs(self) -> list[dict]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT j.id AS job_id, j.vehicle_code, j.created_at, j.note, "
                    "       COUNT(i.id) AS items "
                    "FROM job j LEFT JOIN job_item i ON i.job_id = j.id "
                    "GROUP BY j.id ORDER BY j.created_at DESC, j.id"
                )
            ]

    # -- plans -----------------------------------------------------------

    def save_plan(self, plan: Plan) -> None:
        metrics = plan.metrics
        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM job WHERE id = ?", (plan.job_id,)
            ).fetchone() is None:
                raise NotFound(f"no job {plan.job_id!r} to attach this plan to")

            connection.execute(
                "INSERT OR REPLACE INTO plan (id, job_id, algorithm, created_at, "
                " volume_utilization, weight_utilization, placed, unplaced, "
                " cog_lateral_mm, cog_longitudinal_mm, solve_ms, violations_json, "
                " unplaced_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan.plan_id, plan.job_id, plan.algorithm, _now(),
                    metrics.volume_utilization if metrics else None,
                    metrics.weight_utilization if metrics else None,
                    metrics.placed if metrics else len(plan.placements),
                    metrics.unplaced if metrics else len(plan.unplaced),
                    metrics.cog_lateral_mm if metrics else None,
                    metrics.cog_longitudinal_mm if metrics else None,
                    metrics.solve_ms if metrics else None,
                    json.dumps(metrics.violations) if metrics else None,
                    json.dumps([
                        {"item_uid": u.item_uid, "sku": u.sku, "reason": u.reason}
                        for u in plan.unplaced
                    ]),
                ),
            )
            connection.execute("DELETE FROM placement WHERE plan_id = ?", (plan.plan_id,))
            connection.executemany(
                "INSERT INTO placement (plan_id, seq, item_uid, sku, x, y, z, l, w, h, "
                " orientation, stop) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        plan.plan_id, p.seq, p.item_uid, p.sku,
                        p.pos.x, p.pos.y, p.pos.z,
                        p.dims.l, p.dims.w, p.dims.h,
                        p.orientation.name, p.stop,
                    )
                    for p in plan.placements
                ],
            )

    def load_plan(self, plan_id: str) -> Plan:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM plan WHERE id = ?", (plan_id,)
            ).fetchone()
            if row is None:
                raise NotFound(f"no plan {plan_id!r}")

            vehicle_row = connection.execute(
                "SELECT v.spec_json FROM vehicle_type v "
                "JOIN job j ON j.vehicle_code = v.code WHERE j.id = ?",
                (row["job_id"],),
            ).fetchone()
            vehicle = vehicle_from_dict(json.loads(vehicle_row["spec_json"]))

            placements = tuple(
                Placement(
                    seq=p["seq"], item_uid=p["item_uid"], sku=p["sku"],
                    pos=Pos(p["x"], p["y"], p["z"]),
                    dims=Dims(p["l"], p["w"], p["h"]),
                    orientation=Orientation[p["orientation"]],
                    stop=p["stop"],
                )
                for p in connection.execute(
                    "SELECT * FROM placement WHERE plan_id = ? ORDER BY seq", (plan_id,)
                )
            )

        metrics = None
        if row["volume_utilization"] is not None:
            metrics = Metrics(
                volume_utilization=row["volume_utilization"],
                weight_utilization=row["weight_utilization"],
                placed=row["placed"],
                unplaced=row["unplaced"],
                cog_lateral_mm=row["cog_lateral_mm"],
                cog_longitudinal_mm=row["cog_longitudinal_mm"],
                solve_ms=row["solve_ms"],
                violations=json.loads(row["violations_json"] or "{}"),
            )

        return Plan(
            plan_id=plan_id,
            job_id=row["job_id"],
            vehicle=vehicle,
            algorithm=row["algorithm"],
            placements=placements,
            unplaced=tuple(
                Unplaced(item_uid=u["item_uid"], sku=u["sku"], reason=u["reason"])
                for u in json.loads(row["unplaced_json"])
            ),
            metrics=metrics,
        )

    def plans_for(self, job_id: str) -> list[dict]:
        """Metric rows for every plan of a job -- the comparison view.

        Aggregated in SQL rather than by loading each plan, which is why
        placements are rows and metrics are columns.
        """
        with self.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM job WHERE id = ?", (job_id,)
            ).fetchone() is None:
                raise NotFound(f"no job {job_id!r}")
            rows = connection.execute(
                "SELECT id AS plan_id, algorithm, created_at, volume_utilization, "
                "       weight_utilization, placed, unplaced, cog_lateral_mm, "
                "       cog_longitudinal_mm, solve_ms, violations_json "
                "FROM plan WHERE job_id = ? ORDER BY volume_utilization DESC",
                (job_id,),
            ).fetchall()

        out = []
        for row in rows:
            record = dict(row)
            record["violations"] = json.loads(record.pop("violations_json") or "{}")
            out.append(record)
        return out
