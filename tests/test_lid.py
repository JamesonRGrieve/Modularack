# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tool-less cover: it drops in, slides forward to lock, and only comes out the same way."""

import pytest
from build123d import Part, Pos

from zephyrack import lid
from zephyrack.chassis import RackChassis
from zephyrack.checks import check
from zephyrack.plate import Feature, Plate
from zephyrack.reference import chassis_10_inch, chassis_19_inch
from zephyrack.standards import RACK_19_INCH


@pytest.fixture(scope="module")
def chassis() -> RackChassis:
    built = RackChassis(RACK_19_INCH, 1, 470, toolless_cover=True)
    built.build()
    return built


def _placed(chassis: RackChassis, kind: type[Feature]) -> list[Part]:
    plates = [*chassis.cover.segments.values()]
    return [p.placement * f.shape(p) for p in plates for f in p.features if isinstance(f, kind)]


def _walls(chassis: RackChassis) -> list[Part]:
    return [p.placement * p.body() for w in (chassis.left_wall, chassis.right_wall) for p in w.segments.values()]


def _overlap(moving: list[Part], fixed: list[Part], dx: float, dz: float) -> float:
    total = 0.0
    for m in moving:
        for f in fixed:
            common = (Pos(dx, 0, dz) * m).intersect(f)
            total += sum(s.volume for s in common.solids()) if common is not None else 0.0
    return total


def test_the_latch_bends_well_inside_the_plastics_elastic_range() -> None:
    assert lid.latch_strain() < lid.PLA_STRAIN_LIMIT


def test_locked_the_cover_cannot_lift(chassis: RackChassis) -> None:
    tabs, walls = _placed(chassis, lid.CoverTab), _walls(chassis)
    assert _overlap(tabs, walls, 0, 0) == pytest.approx(0, abs=1e-6)
    assert _overlap(tabs, walls, 0, 1.0) > 1.0


@pytest.mark.parametrize("dz", [0.0, 3.0, 10.0])
def test_slid_back_the_cover_lifts_straight_out(chassis: RackChassis, dz: float) -> None:
    tabs, walls = _placed(chassis, lid.CoverTab), _walls(chassis)
    assert _overlap(tabs, walls, lid.SLIDE, dz) == pytest.approx(0, abs=1e-6)


def test_the_tooth_springs_into_its_pocket_only_when_locked(chassis: RackChassis) -> None:
    teeth, walls = _placed(chassis, lid.LatchTooth), _walls(chassis)
    assert len(teeth) == 1
    assert _overlap(teeth, walls, 0, 0) == pytest.approx(0, abs=1e-6)
    # Slid back, the tooth presses on the wall's face: the arm must bend by the tooth's height.
    assert _overlap(teeth, walls, lid.SLIDE, 0) > 1.0
    # Locked, its square rear face stops the cover sliding back.
    assert _overlap(teeth, walls, 1.0, 0) > 0.1


def test_the_cover_prints_inner_face_down_with_its_tabs_on_the_bed(chassis: RackChassis) -> None:
    parts = chassis.printable_parts()
    for plate in chassis.cover.segments.values():
        part = parts[plate.name]
        assert pytest.approx(0, abs=1e-6) == part.bounding_box().min.Z
        assert pytest.approx(plate.thickness, abs=1e-6) == part.bounding_box().size.Z


@pytest.mark.parametrize("build", [chassis_10_inch, chassis_19_inch])
def test_reference_chassis_take_a_tool_less_cover(build) -> None:  # type: ignore[no-untyped-def]
    built = build(2, toolless_cover=True)
    report = check(built)
    assert report.clean, report
    plates: list[Plate] = [*built.cover.segments.values()]
    assert sum(isinstance(f, lid.CoverTab) for p in plates for f in p.features) >= 4
