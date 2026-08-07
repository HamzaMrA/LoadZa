"""The thpack parser, including the malformed record in the shipped data."""

from __future__ import annotations

import pytest

from bench.loader import DATASET_DIR, SETS, MalformedInstance, load_set, parse
from core.models import Orientation

# Two instances in the documented layout. The first box type may only stand on
# its third dimension; the second may stand on any.
SAMPLE = """ 2
 1 12345
 100 80 60
 2
 1 30 0 20 0 10 1 4
 2 15 1 15 1 15 1 6
 2
 200 100 100
 1
 1 50 0 40 1 30 0 12
"""

MALFORMED = """ 1
 1
 100 80 60
 1
 1 30 0 20 10 1 4
"""


def test_parses_both_instances():
    dataset = parse(SAMPLE, "TEST")
    assert dataset.name == "TEST"
    assert len(dataset) == 2
    assert dataset.skipped == ()

    first, second = dataset.instances
    assert (first.container.l, first.container.w, first.container.h) == (100, 80, 60)
    assert first.total_boxes == 10
    assert second.total_boxes == 12


def test_vertical_flags_become_orientations():
    first = parse(SAMPLE, "TEST").instances[0]
    restricted, free = first.types

    # Flag on the third dimension only: the two orientations keeping it upright.
    assert restricted[1] == (Orientation.LWH, Orientation.WLH)
    # All three flags set: every orientation, each listed once.
    assert set(free[1]) == set(Orientation)
    assert len(free[1]) == len(set(free[1]))


def test_flag_on_the_second_dimension_stands_that_side_up():
    second = parse(SAMPLE, "TEST").instances[1]
    _, orientations, _ = second.types[0]
    assert orientations == (Orientation.LHW, Orientation.HLW)


def test_instance_becomes_a_solvable_job():
    instance = parse(SAMPLE, "TEST").instances[0]
    job = instance.to_job()
    assert len(job.items) == 10
    assert job.vehicle.inner == instance.container
    # Payload must never be the binding constraint in a volume benchmark.
    assert job.total_weight_g < job.vehicle.max_payload_g / 1000
    assert job.vehicle.min_support_ratio == 0.0


def test_support_ratio_is_opt_in():
    instance = parse(SAMPLE, "TEST").instances[0]
    assert instance.to_job(support_ratio=0.7).vehicle.min_support_ratio == 0.7


def test_malformed_record_raises_by_default():
    with pytest.raises(MalformedInstance):
        parse(MALFORMED, "TEST")


def test_malformed_record_is_reported_not_repaired():
    dataset = parse(MALFORMED, "TEST", strict=False)
    assert dataset.instances == ()
    assert dataset.skipped == (1,)


def test_truncated_file_is_rejected():
    with pytest.raises(ValueError, match="promises"):
        parse(" 5\n 1\n 10 10 10\n 1\n 1 2 1 2 1 2 1 3\n", "TEST")


def test_unknown_set_name():
    with pytest.raises(KeyError):
        load_set("NOPE")


def test_missing_dataset_points_at_the_fetch_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_datasets"):
        load_set("BR1", directory=tmp_path)


@pytest.mark.skipif(
    not (DATASET_DIR / SETS["BR1"]).exists(),
    reason="benchmark data not fetched: python -m tools.fetch_datasets",
)
def test_real_br1_matches_its_published_shape():
    """BR1 is 100 instances of three box types in a 587x233x220 container."""
    dataset = load_set("BR1")
    assert len(dataset) == 100
    assert dataset.skipped == ()
    for instance in dataset:
        assert len(instance.types) == 3
        assert (instance.container.l, instance.container.w, instance.container.h) == (
            587, 233, 220
        )


@pytest.mark.skipif(
    not (DATASET_DIR / SETS["SMALL"]).exists(),
    reason="benchmark data not fetched: python -m tools.fetch_datasets",
)
def test_the_small_set_still_has_its_upstream_defect():
    """Three records in thpack9 are short a vertical flag. Documented, not fixed.

    If this test starts failing, OR-Library has corrected the file and the
    --skip-malformed workaround can go.
    """
    with pytest.raises(MalformedInstance):
        load_set("SMALL")
    assert load_set("SMALL", strict=False).skipped == (18, 19, 20)
