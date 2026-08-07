"""The schematic renderer. Skipped when the optional viz extra is absent."""

from __future__ import annotations

import pytest

from core.solver_ep import solve
from tools.gen_demo import generate
from tools.view import STOP_COLOURS, stop_style

pytest.importorskip("matplotlib", reason="install the viz extra: pip install -e '.[viz]'")


def test_stop_colours_repeat_with_a_hatch_rather_than_a_new_hue():
    """Only three hues clear all-pairs separation, so stop 4 reuses hue 1.

    Identity is carried by the hatch and the box label, never by colour alone.
    """
    first = [stop_style(stop) for stop in (1, 2, 3)]
    assert [colour for colour, _ in first] == list(STOP_COLOURS)
    assert {hatch for _, hatch in first} == {""}

    colour_4, hatch_4 = stop_style(4)
    assert colour_4 == STOP_COLOURS[0]
    assert hatch_4 != ""


def test_render_writes_a_png(tmp_path):
    from tools.view import render

    job = generate(vehicle_code="CNT-20DV", mix="cartons", fill=0.6, seed=13)
    out = render(job, solve(job), tmp_path / "plan.png")
    assert out.exists()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out.stat().st_size > 10_000


def test_render_handles_an_empty_plan(tmp_path):
    """A job where nothing fits still has to draw the empty vehicle."""
    from core import catalog
    from core.models import Dims, Item, ItemType, Job
    from tools.view import render

    huge = ItemType(sku="HUGE", name="huge", dims=Dims(9000, 9000, 9000), weight_g=1000)
    job = Job(
        job_id="empty",
        vehicle=catalog.vehicle("CNT-20DV"),
        items=(Item(uid=0, type=huge),),
    )
    plan = solve(job)
    assert plan.placements == ()
    assert render(job, plan, tmp_path / "empty.png").exists()


@pytest.mark.parametrize("label", ["sku", "seq", "none"])
def test_every_label_mode_renders(tmp_path, label):
    from tools.view import render

    job = generate(vehicle_code="CNT-40DV", mix="mixed", fill=0.5, stops=3, seed=77)
    out = render(job, solve(job), tmp_path / f"{label}.png", label=label)
    assert out.exists()
