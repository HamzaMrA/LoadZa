"""Geometry primitives and the spatial index."""

from __future__ import annotations

from core.geometry import (
    SpatialIndex,
    distinct_orientations,
    face_contact_area,
    inside,
    make_box,
    overlap_area_xy,
    overlaps,
)
from core.models import ALL_ORIENTATIONS, Dims, Pos


def test_touching_boxes_do_not_overlap():
    a = (0, 0, 0, 100, 100, 100)
    b = (100, 0, 0, 200, 100, 100)
    assert not overlaps(a, b)
    assert not overlaps(b, a)


def test_one_millimetre_of_interpenetration_is_an_overlap():
    a = (0, 0, 0, 100, 100, 100)
    b = (99, 0, 0, 200, 100, 100)
    assert overlaps(a, b)


def test_inside_rejects_a_box_that_pokes_through_the_roof():
    inner = Dims(1000, 1000, 1000)
    assert inside((0, 0, 0, 1000, 1000, 1000), inner)
    assert not inside((0, 0, 1, 1000, 1000, 1001), inner)
    assert not inside((-1, 0, 0, 100, 100, 100), inner)


def test_overlap_area_xy_ignores_height():
    a = (0, 0, 0, 100, 100, 10)
    b = (50, 50, 900, 150, 150, 1000)
    assert overlap_area_xy(a, b) == 50 * 50


def test_face_contact_area_between_stacked_boxes():
    lower = (0, 0, 0, 100, 100, 100)
    upper = (0, 0, 100, 60, 100, 200)
    assert face_contact_area(lower, upper) == 60 * 100


def test_distinct_orientations_collapses_duplicates():
    cube = distinct_orientations(Dims(500, 500, 500), ALL_ORIENTATIONS)
    square_base = distinct_orientations(Dims(600, 600, 880), ALL_ORIENTATIONS)
    all_different = distinct_orientations(Dims(1200, 800, 1450), ALL_ORIENTATIONS)
    assert len(cube) == 1
    assert len(square_base) == 3
    assert len(all_different) == 6


def test_settle_drops_a_floating_box_onto_the_one_below():
    index = SpatialIndex(cell=500)
    index.add((0, 0, 0, 1000, 1000, 500))
    floating = (0, 0, 900, 1000, 1000, 1400)
    assert index.settle(floating) == (0, 0, 500, 1000, 1000, 1000)


def test_settle_drops_to_the_floor_when_nothing_is_underneath():
    index = SpatialIndex(cell=500)
    index.add((5000, 0, 0, 6000, 1000, 500))
    assert index.settle((0, 0, 800, 500, 500, 1300)) == (0, 0, 0, 500, 500, 500)


def test_support_ratio_counts_only_the_surface_directly_below():
    index = SpatialIndex(cell=500)
    index.add((0, 0, 0, 1000, 1000, 500))
    fully = (0, 0, 500, 1000, 1000, 900)
    half = (500, 0, 500, 1500, 1000, 900)
    assert index.support_ratio(fully) == 1.0
    assert index.support_ratio(half) == 0.5
    assert index.support_ratio((0, 0, 0, 100, 100, 100)) == 1.0


def test_collides_finds_boxes_across_cell_boundaries():
    index = SpatialIndex(cell=1000)
    index.add((900, 900, 0, 1100, 1100, 100))
    assert index.collides((1050, 1050, 0, 1200, 1200, 100))
    assert not index.collides((1100, 1100, 0, 1200, 1200, 100))


def test_contact_area_counts_walls():
    inner = Dims(2000, 2000, 2000)
    index = SpatialIndex(cell=1000)
    corner = make_box(Pos(0, 0, 0), Dims(1000, 1000, 1000))
    # Floor plus two walls, each face a million square millimetres.
    assert index.contact_area(corner, inner) == 3 * 1000 * 1000


def test_contains_point_is_strict():
    index = SpatialIndex(cell=1000)
    index.add((0, 0, 0, 1000, 1000, 1000))
    assert index.contains_point(Pos(500, 500, 500))
    assert not index.contains_point(Pos(1000, 500, 500))
