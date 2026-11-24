# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tool-less box: walls on floor dovetails, a latched rear wall, and the cover, swept through assembly."""

import pytest
from build123d import Part, Pos

from modularack import lid, toolless
from modularack.chassis import RackChassis
from modularack.checks import check
from modularack.layout import Panel
from modularack.plate import Feature
from modularack.reference import chassis_10_inch, chassis_19_inch
from modularack.standards import RACK_19_INCH


@pytest.fixture(scope="module")
def chassis() -> RackChassis:
    built = RackChassis(RACK_19_INCH, 1, 470, toolless_box=True)
    built.build()
    return built


def _features(panel: Panel, kind: type[Feature]) -> list[Part]:
    return [p.placement * f.shape(p) for p in panel.segments.values() for f in p.features if isinstance(f, kind)]


def _bodies(*panels: Panel) -> list[Part]:
    return [p.placement * p.body() for panel in panels for p in panel.segments.values()]


def _overlap(moving: list[Part], fixed: list[Part], dx: float = 0.0, dz: float = 0.0) -> float:
    total = 0.0
    for m in moving:
        for f in fixed:
            common = (Pos(dx, 0, dz) * m).intersect(f)
            total += sum(s.volume for s in common.solids()) if common is not None else 0.0
    return total


def test_both_latches_bend_well_inside_the_plastics_elastic_range(chassis: RackChassis) -> None:
    assert toolless.rear_latch_strain(chassis.rear_wall.width) < lid.PLA_STRAIN_LIMIT


@pytest.mark.parametrize("side", ["left", "right"])
def test_a_locked_side_wall_holds_the_floor(chassis: RackChassis, side: str) -> None:
    wall = chassis.left_wall if side == "left" else chassis.right_wall
    tabs, floor = _features(wall, lid.CoverTab), _bodies(chassis.floor)
    assert len(tabs) >= 2
    assert _overlap(tabs, floor) == pytest.approx(0, abs=1e-6)
    assert _overlap(tabs, floor, dz=1.0) > 1.0


@pytest.mark.parametrize("dz", [0.0, 3.0, 10.0])
def test_slid_forward_a_side_wall_lifts_off(chassis: RackChassis, dz: float) -> None:
    tabs, floor = _features(chassis.left_wall, lid.CoverTab), _bodies(chassis.floor)
    assert _overlap(tabs, floor, dx=-lid.SLIDE, dz=dz) == pytest.approx(0, abs=1e-6)


def test_the_rear_wall_locates_on_its_tenons_and_latches(chassis: RackChassis) -> None:
    tenons, teeth = _features(chassis.rear_wall, toolless.Tenon), _features(chassis.rear_wall, toolless.SideTooth)
    floor, sides = _bodies(chassis.floor), _bodies(chassis.left_wall, chassis.right_wall)
    assert len(tenons) >= 2 and len(teeth) == 2
    assert _overlap(tenons, floor) == pytest.approx(0, abs=1e-6)
    assert _overlap(teeth, sides) == pytest.approx(0, abs=1e-6)
    assert _overlap(tenons, floor, dx=1.0) > 0.1
    # Latched, it can't lift.
    assert _overlap(teeth, sides, dz=1.0) > 0.1


def test_the_rear_wall_stops_the_side_walls_sliding_out(chassis: RackChassis) -> None:
    teeth, sides = _features(chassis.rear_wall, toolless.SideTooth), _bodies(chassis.left_wall, chassis.right_wall)
    # Moving the teeth back is moving the side walls forward relative to them.
    assert _overlap(teeth, sides, dx=1.0) > 0.1


def test_no_screws_join_the_boxs_panels(chassis: RackChassis) -> None:
    screwed = RackChassis(RACK_19_INCH, 1, 470)
    screwed.build()
    count = sum(n for item, n in chassis.bill_of_materials().items() if "countersunk" in item)
    before = sum(n for item, n in screwed.bill_of_materials().items() if "countersunk" in item)
    assert count < before


@pytest.mark.parametrize(("build", "units"), [(chassis_10_inch, 1), (chassis_19_inch, 1), (chassis_19_inch, 4)])
def test_reference_chassis_build_tool_less(build, units: int) -> None:  # type: ignore[no-untyped-def]
    built = build(units, toolless_box=True)
    report = check(built)
    assert report.clean, report
