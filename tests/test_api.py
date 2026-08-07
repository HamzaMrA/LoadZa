"""The HTTP layer and its database.

Each test gets its own SQLite file through LOADZA_DB, so nothing leaks between
them and no test depends on the order it runs in.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="install the api extra: pip install -e '.[api]'")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from app.db import NotFound, Store  # noqa: E402
from core.io import job_to_dict, plan_to_dict  # noqa: E402
from core.solver_ep import solve  # noqa: E402
from core.validator import validate  # noqa: E402
from tools.gen_demo import generate  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOADZA_DB", str(tmp_path / "test.sqlite"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def job():
    return generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.5, seed=13)


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalog_is_enough_to_build_a_job_from(client):
    """The UI populates its dropdowns from here; without it, job creation can
    only happen from a shell that already knows the catalogue by heart."""
    body = client.get("/catalog").json()
    assert {v["code"] for v in body["vehicles"]} >= {"TIR-1360", "CNT-20DV"}
    assert {t["sku"] for t in body["item_types"]} >= {"EUR-FULL", "BOX-M"}

    vehicle = next(v for v in body["vehicles"] if v["code"] == "TIR-1360")
    assert vehicle["inner_mm"]["length"] == 13600
    assert vehicle["max_payload_g"] > 0

    # A job built purely from catalogue codes has to be accepted.
    created = client.post(
        "/jobs",
        json={
            "job_id": "from-catalog",
            "vehicle": {"code": vehicle["code"]},
            "items": [{"sku": "EUR-FULL", "qty": 4, "stop": 1}],
        },
    )
    assert created.status_code == 201
    assert client.post("/jobs/from-catalog/solve", json={}).status_code == 200


def test_create_read_and_list_a_job(client, job):
    created = client.post("/jobs", json=job_to_dict(job))
    assert created.status_code == 201
    body = created.json()
    assert body["job_id"] == job.job_id
    assert body["items"] == len(job.items)

    fetched = client.get(f"/jobs/{job.job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["vehicle"]["code"] == job.vehicle.code

    listed = client.get("/jobs").json()
    assert [row["job_id"] for row in listed] == [job.job_id]


def test_a_job_survives_the_round_trip_intact(client, job):
    client.post("/jobs", json=job_to_dict(job))
    returned = client.get(f"/jobs/{job.job_id}").json()

    original = job_to_dict(job)
    assert returned["vehicle"] == original["vehicle"]
    assert sorted(returned["item_types"], key=lambda t: t["sku"]) == sorted(
        original["item_types"], key=lambda t: t["sku"]
    )
    assert sorted(map(str, returned["items"])) == sorted(map(str, original["items"]))


def test_solve_stores_a_plan_with_the_validator_verdict(client, job):
    client.post("/jobs", json=job_to_dict(job))
    response = client.post(f"/jobs/{job.job_id}/solve", json={})
    assert response.status_code == 200

    summary = response.json()
    assert summary["placed"] > 0
    assert summary["volume_utilization"] > 0
    # A stored plan nobody had checked would have no counts at all.
    assert set(summary["violations"]) >= {"K1", "K2", "K3", "K4"}
    assert summary["violations"]["K1"] == 0

    plan = client.get(f"/plans/{summary['plan_id']}").json()
    assert len(plan["placements"]) == summary["placed"]
    assert plan["metrics"]["violations"]["K1"] == 0


def test_plan_document_matches_what_the_solver_produced(client, job):
    client.post("/jobs", json=job_to_dict(job))
    plan_id = client.post(f"/jobs/{job.job_id}/solve", json={}).json()["plan_id"]
    stored = client.get(f"/plans/{plan_id}").json()

    direct = plan_to_dict(solve(job))
    assert stored["placements"] == direct["placements"]
    assert stored["vehicle"] == direct["vehicle"]


def test_solving_twice_with_different_settings_gives_two_comparable_plans(client, job):
    client.post("/jobs", json=job_to_dict(job))
    client.post(f"/jobs/{job.job_id}/solve", json={"scorer": "layer"})
    client.post(f"/jobs/{job.job_id}/solve", json={"scorer": "dbl"})

    rows = client.get(f"/jobs/{job.job_id}/plans").json()
    assert len(rows) == 2
    utilisations = [row["volume_utilization"] for row in rows]
    assert utilisations == sorted(utilisations, reverse=True), "best first"


def test_annealing_through_the_api(client, job):
    client.post("/jobs", json=job_to_dict(job))
    plain = client.post(f"/jobs/{job.job_id}/solve", json={}).json()
    annealed = client.post(
        f"/jobs/{job.job_id}/solve", json={"anneal_seconds": 2.0}
    ).json()
    assert annealed["volume_utilization"] >= plain["volume_utilization"]
    assert annealed["plan_id"].endswith("-sa")


def test_the_annealing_budget_is_capped(client, job):
    client.post("/jobs", json=job_to_dict(job))
    response = client.post(
        f"/jobs/{job.job_id}/solve", json={"anneal_seconds": 10_000}
    )
    assert response.status_code == 422


def test_validate_endpoint_agrees_with_the_local_validator(client, job):
    """The endpoint is a transport for core.validator, not a second opinion."""
    plan = solve(job)
    expected = validate(job, plan)

    response = client.post(
        "/validate", json={"job": job_to_dict(job), "plan": plan_to_dict(plan)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] == expected.is_valid
    assert body["counts"] == expected.counts
    assert len(body["violations"]) == len(expected.violations)
    assert body["counts"]["K1"] == 0


def test_validate_endpoint_reports_a_broken_plan(client, job):
    document = plan_to_dict(solve(job))
    # Shove one box out through the roof.
    document["placements"][0]["pos_mm"]["z"] = 9_000_000

    response = client.post("/validate", json={"job": job_to_dict(job), "plan": document})
    body = response.json()
    assert body["valid"] is False
    assert body["counts"]["K2"] >= 1
    assert any(v["constraint"] == "K2" for v in body["violations"])


def test_validate_endpoint_can_narrow_the_checks(client, job):
    plan = solve(job)
    response = client.post(
        "/validate",
        json={"job": job_to_dict(job), "plan": plan_to_dict(plan), "checks": ["K1"]},
    )
    assert set(response.json()["counts"]) == {"K1"}


def test_validate_endpoint_rejects_a_mismatched_pair(client, job):
    other = generate(vehicle_code="CNT-40DV", mix="mixed", fill=0.3, seed=2)
    response = client.post(
        "/validate", json={"job": job_to_dict(other), "plan": plan_to_dict(solve(job))}
    )
    assert response.status_code == 409


def test_report_endpoints_return_real_documents(client, job):
    pytest.importorskip("openpyxl", reason="install the viz extra")
    client.post("/jobs", json=job_to_dict(job))
    plan_id = client.post(f"/jobs/{job.job_id}/solve", json={}).json()["plan_id"]

    pdf = client.get(f"/plans/{plan_id}/report.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert f'filename="{plan_id}.pdf"' in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF-")

    xlsx = client.get(f"/plans/{plan_id}/report.xlsx")
    assert xlsx.status_code == 200
    assert xlsx.content.startswith(b"PK\x03\x04")


def test_report_for_an_unknown_plan_is_404(client):
    assert client.get("/plans/nope/report.pdf").status_code == 404
    assert client.get("/plans/nope/report.xlsx").status_code == 404


def test_assign_stores_each_trip_as_a_job_of_its_own(client):
    """Trips are stored, so the viewer and the reports work on them unchanged."""
    big = generate(vehicle_code="CNT-20DV", mix="mixed", fill=3.0, stops=2, seed=55)
    client.post("/jobs", json=job_to_dict(big))

    response = client.post(
        f"/jobs/{big.job_id}/assign",
        json={"fleet": ["CNT-20DV", "TIR-1360"], "max_trips": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vehicles_used"] > 1
    assert body["placed"] > 0

    listed = {row["job_id"] for row in client.get("/jobs").json()}
    for trip in body["trips"]:
        assert trip["job_id"] in listed
        assert trip["violations"]["K1"] == 0
        # Every trip has to be openable in the viewer, which means the plan
        # document has to load and match what the trip reported.
        plan = client.get(f"/plans/{trip['plan_id']}").json()
        assert len(plan["placements"]) == trip["boxes"]


def test_assign_rejects_an_unknown_vehicle(client, job):
    client.post("/jobs", json=job_to_dict(job))
    bad = client.post(f"/jobs/{job.job_id}/assign", json={"fleet": ["NOPE"]})
    assert bad.status_code == 422


def test_assign_for_an_unknown_job_is_404(client):
    assert client.post("/jobs/nope/assign", json={}).status_code == 404


def test_unknown_ids_are_404(client):
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/plans/nope").status_code == 404
    assert client.get("/jobs/nope/plans").status_code == 404
    assert client.post("/jobs/nope/solve", json={}).status_code == 404


def test_malformed_documents_are_422(client, job):
    assert client.post("/jobs", json={"job_id": "x"}).status_code == 422
    client.post("/jobs", json=job_to_dict(job))
    bad = client.post(f"/jobs/{job.job_id}/solve", json={"scorer": "nope"})
    assert bad.status_code == 422


def test_store_round_trips_a_job_exactly(tmp_path, job):
    """Including item order, which the annealing pass uses as its start point."""
    store = Store(tmp_path / "s.sqlite")
    store.initialise()
    store.save_job(job)
    assert store.load_job(job.job_id) == job


def test_store_rejects_a_plan_without_its_job(tmp_path, job):
    store = Store(tmp_path / "s.sqlite")
    store.initialise()
    with pytest.raises(NotFound):
        store.save_plan(solve(job))


def test_store_keeps_inline_item_types(tmp_path):
    """Benchmark jobs carry types that are not in the catalogue."""
    from bench.loader import parse

    store = Store(tmp_path / "s.sqlite")
    store.initialise()
    instance = parse(" 1\n 1\n 100 80 60\n 1\n 1 30 0 20 0 10 1 4\n", "T").instances[0]
    job = instance.to_job()

    store.save_job(job)
    restored = store.load_job(job.job_id)
    assert restored.items[0].type == job.items[0].type
    assert restored.vehicle == job.vehicle
