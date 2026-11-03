# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less sleds: printed pins on sprung rail skins in the drive's side holes, no screws."""

import pytest
from build123d import Box, Pos

from zephyrack.cassette import DriveBay
from zephyrack.chassis import RackChassis
from zephyrack.checks import check
from zephyrack.fea import PLA
from zephyrack.printability import overhangs
from zephyrack.reference import COLUMNS_2_5_19_INCH, COLUMNS_3_5_19_INCH, DEPTH_19_INCH
from zephyrack.sled import (
    FRONT_BAR_THICKNESS,
    PIN_ARM_GAP,
    PIN_ARM_SKIN,
    PLA_MODULUS,
    Sled,
    pin_arm_strain,
    pin_release_force,
)
from zephyrack.standards import ATX, DRIVE_2_5, DRIVE_3_5, RACK_19_INCH, DriveFormFactor


def _volume(part, box) -> float:  # type: ignore[no-untyped-def]
    common = part & box
    return 0.0 if common is None else float(common.volume)


DRIVE_WEIGHT_N = {DRIVE_3_5.name: 0.75 * 9.81, DRIVE_2_5.name: 0.15 * 9.81}


def _sled(drive: DriveFormFactor, column: int) -> Sled:
    chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX, toolless_sleds=True)
    chassis.add_module(DriveBay(drive, levels=1), column, 0)
    chassis.build()
    return next(d for d in chassis.descendants() if isinstance(d, Sled))


@pytest.mark.parametrize(
    ("drive", "column"), [(DRIVE_3_5, COLUMNS_3_5_19_INCH[0]), (DRIVE_2_5, COLUMNS_2_5_19_INCH[0])]
)
def test_a_pinned_sled_prints_alone_without_supports(drive: DriveFormFactor, column: int) -> None:
    sled = _sled(drive, column)
    part = sled.solids()["part"]
    assert part.is_valid and len(part.solids()) == 1
    assert not overhangs(part.moved(sled.print_location))


@pytest.mark.parametrize(
    ("drive", "column"), [(DRIVE_3_5, COLUMNS_3_5_19_INCH[0]), (DRIVE_2_5, COLUMNS_2_5_19_INCH[0])]
)
def test_each_pin_sits_in_its_side_hole_on_a_free_skin(drive: DriveFormFactor, column: int) -> None:
    sled = _sled(drive, column)
    g = sled.geometry
    part = sled.solids()["part"]
    z = g.drive_base + drive.side_hole_height
    arms = g.pin_arms()
    assert len(arms) == 4
    for x, inner_y, inward, _ in arms:
        # The pin stands out of the rail's inner face at the hole's centre...
        probe = Pos(x, inner_y + inward * 1.2, z) * Box(0.4, 0.4, 0.4)
        assert _volume(part, probe) > 0.03
        # ...and its skin is cut free behind it.
        gap_y = inner_y - inward * (PIN_ARM_SKIN + PIN_ARM_GAP / 2)
        assert _volume(part, Pos(x, gap_y, z) * Box(0.4, 0.4, 0.4)) == pytest.approx(0, abs=1e-6)
    assert all(x > FRONT_BAR_THICKNESS for x, *_ in arms)


def test_the_release_force_uses_the_fea_modulus() -> None:
    assert PLA.modulus == PLA_MODULUS


def test_the_pin_arms_bend_within_the_plastic_and_hold_a_drive() -> None:
    assert pin_arm_strain() < 0.02
    # A 3.5 in drive on 10 mm rails: its weight hangs on the flat tops; popping it out takes a firm push.
    assert pin_release_force(10.0) > 2 * DRIVE_WEIGHT_N[DRIVE_3_5.name]


def test_pinned_sleds_take_no_drive_screws() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX, toolless_sleds=True)
    chassis.add_module(DriveBay(DRIVE_3_5), COLUMNS_3_5_19_INCH[0], 0)
    chassis.build()
    assert not any(DRIVE_3_5.screw in item for item in chassis.hardware)
    assert check(chassis).clean
