# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every reference design, 10 in and 19 in at 1U-4U plus a printed rack of each width,
fits the bed, prints without supports, is made of valid single solids and assembles
without interference."""

import pytest
from build123d import Vector

from zephyrack.cassette import DriveBay, Vent
from zephyrack.chassis import EAR_HOLES_PER_UNIT, EAR_THICKNESS, SEAM_STAGGER, RackChassis
from zephyrack.checks import check
from zephyrack.plate import Boss, Plate, Slot
from zephyrack.rack import PrintedRack
from zephyrack.reference import reference_builders
from zephyrack.sled import Sled
from zephyrack.standards import (
    ATX,
    DRIVE_2_5_7MM,
    DRIVE_3_5,
    EEB,
    MINI_ITX,
    PANEL_HEIGHT_DEDUCTION,
    RACK_10_INCH,
    RACK_19_INCH,
    RACK_UNIT,
    U_HOLE_OFFSETS,
    MountingHole,
    panel_height,
)

DESIGNS = reference_builders()


@pytest.mark.parametrize("name", list(DESIGNS))
def test_reference_design_is_printable_and_assembles(name: str) -> None:
    report = check(DESIGNS[name]())
    assert report.parts > 0
    assert report.off_bed == []
    assert report.invalid == []
    assert report.needs_support == []
    assert report.interferences == []


@pytest.mark.parametrize("units", [1, 2, 3, 4])
@pytest.mark.parametrize("rack", [RACK_10_INCH, RACK_19_INCH])
def test_chassis_fills_its_rack_slot(units: int, rack) -> None:  # type: ignore[no-untyped-def]
    name = f"chassis_{rack.name}_{units}U"
    chassis = DESIGNS[name]()
    box = chassis.assemble().bounding_box()
    assert pytest.approx(panel_height(units)) == box.size.Z
    assert pytest.approx(rack.panel_width) == box.size.Y


@pytest.mark.parametrize("rack", [RACK_10_INCH, RACK_19_INCH])
def test_ear_slots_line_up_with_eia_holes(rack) -> None:  # type: ignore[no-untyped-def]
    chassis = RackChassis(rack, 2, 380, MINI_ITX if rack is RACK_10_INCH else None)
    chassis.build()
    ear = chassis.children[f"{chassis.name}_left_ear"]
    assert isinstance(ear, Plate)
    slots = [f for f in ear.features if isinstance(f, Slot)]
    expected_z = sorted(
        u * RACK_UNIT + U_HOLE_OFFSETS[i] - PANEL_HEIGHT_DEDUCTION / 2 for u in range(2) for i in EAR_HOLES_PER_UNIT
    )
    assert sorted(round(s.v, 3) for s in slots) == [round(z, 3) for z in expected_z]
    for s in slots:
        rack_y = ear.frame.to_rack(Vector(s.u, s.v, 0)).Y
        assert rack_y == pytest.approx(rack.hole_spacing / 2)
        assert s.travel == pytest.approx(2 * rack.hole_spacing_tolerance)


def test_chassis_heights_are_limited_to_1u_through_4u() -> None:
    with pytest.raises(ValueError):
        RackChassis(RACK_19_INCH, 5, 470)
    with pytest.raises(ValueError):
        RackChassis(RACK_19_INCH, 0, 470)


def test_a_module_can_span_several_rows() -> None:
    chassis = RackChassis(RACK_19_INCH, 3, 470)
    chassis.add_module(DriveBay(DRIVE_3_5, rows=2), 0, 0)
    chassis.add_module(Vent(rows=3), 4, 0, 6)
    chassis.build()
    sleds = [c for c in chassis.descendants() if isinstance(c, Sled)]
    assert len(sleds) == 2
    report = check(chassis)
    assert report.clean, report


def test_a_two_post_printed_rack_is_printable() -> None:
    report = check(PrintedRack(RACK_10_INCH, 4, 200, four_post=False))
    assert report.clean, report


def test_modules_wider_than_the_bed_are_refused_and_blanks_are_split() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, 470)
    with pytest.raises(ValueError, match="bed prints"):
        chassis.add_module(Vent(), 0, 0, 12)
    chassis.fill_blanks()
    assert [p.columns for p in chassis.placements] == [6, 6]


def test_a_board_that_collides_with_the_front_modules_is_refused() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, 300, ATX)
    chassis.add_module(DriveBay(DRIVE_3_5), 0, 0)
    with pytest.raises(ValueError, match="deeper"):
        chassis.build()


def test_an_eeb_board_with_alternates_fits_a_19_inch_chassis() -> None:
    chassis = RackChassis(
        RACK_19_INCH, 2, 540, EEB, alternate_holes=frozenset({MountingHole.F_ALT, MountingHole.J_ALT})
    )
    for column in (0, 4, 8):
        chassis.add_module(DriveBay(DRIVE_3_5), column, 0)
    chassis.build()
    bosses = [f for p in chassis.descendants() if isinstance(p, Plate) for f in p.features if isinstance(f, Boss)]
    assert len(bosses) == len(EEB.holes) + 2
    report = check(chassis)
    assert report.clean, report


def test_alternates_are_refused_for_non_ssi_boards() -> None:
    with pytest.raises(ValueError, match="SSI"):
        RackChassis(RACK_19_INCH, 2, 470, ATX, alternate_holes=frozenset({MountingHole.F_ALT}))


@pytest.mark.parametrize("name", ["chassis_19in_1U", "chassis_10in_2U"])
def test_wall_seams_are_staggered_against_floor_and_cover_seams(name: str) -> None:
    chassis = DESIGNS[name]()
    assert isinstance(chassis, RackChassis)
    box = chassis.floor.seams_u + chassis.cover.seams_u
    walls = chassis.left_wall.seams_u + [chassis.depth - EAR_THICKNESS - s for s in chassis.right_wall.seams_u]
    assert box and walls
    assert all(abs(a - b) >= SEAM_STAGGER for a in box for b in walls)


def test_thin_2_5_inch_drives_stack_two_sleds_to_a_1u_row() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, 470)
    for column in (0, 3, 6, 9):
        chassis.add_module(DriveBay(DRIVE_2_5_7MM), column, 0)
    chassis.build()
    assert len([c for c in chassis.descendants() if isinstance(c, Sled)]) == 8
    report = check(chassis)
    assert report.clean, report


def test_asking_for_more_sled_levels_than_fit_is_refused() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, 470)
    chassis.add_module(DriveBay(DRIVE_3_5, levels=2), 0, 0)
    with pytest.raises(ValueError, match="don't fit"):
        chassis.build()
