# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ATX power supply bay: screws through the rear wall, guide ribs on the floor, room beside the board."""

import pytest

from modularack.cassette import DriveBay
from modularack.chassis import WALL_THICKNESS, RackChassis
from modularack.checks import check
from modularack.plate import RectCut, Rib, ThroughHole
from modularack.reference import COLUMNS_3_5_19_INCH, DEPTH_19_INCH
from modularack.standards import ATX, ATX_PSU, DRIVE_3_5, MINI_ITX, RACK_19_INCH, MotherboardFormFactor


def _chassis(board: MotherboardFormFactor | None, units: int) -> RackChassis:
    chassis = RackChassis(RACK_19_INCH, units, DEPTH_19_INCH, board, power_supply=True)
    chassis.add_module(DriveBay(DRIVE_3_5), COLUMNS_3_5_19_INCH[0], 0)
    chassis.build()
    return chassis


@pytest.mark.parametrize(("board", "units", "on_side"), [(MINI_ITX, 3, False), (ATX, 4, True)])
def test_the_supply_screws_to_the_rear_wall_inside_its_own_footprint(
    board: MotherboardFormFactor, units: int, on_side: bool
) -> None:
    chassis = _chassis(board, units)
    psu = chassis._psu_layout()
    assert psu is not None and psu.on_side is on_side
    inside = chassis.width / 2 - WALL_THICKNESS
    holes, openings = [], []
    for (i, j), plate in chassis.rear_wall.segments.items():
        pu, pv = chassis.rear_wall.u_bounds[i], chassis.rear_wall.v_bounds[j]
        holes += [
            (f.u + pu, f.v + pv)
            for f in plate.features
            if isinstance(f, ThroughHole) and f.diameter == ATX_PSU.screw_clearance
        ]
        openings += [f for f in plate.features if isinstance(f, RectCut)]
    assert len(holes) == len(ATX_PSU.holes)
    for u, v in holes:
        y = inside - u
        assert psu.y0 < y < psu.y1
        assert 0 < v < psu.height
    assert openings
    assert check(chassis).clean


def test_guide_ribs_run_along_both_sides_of_the_longest_supply() -> None:
    chassis = _chassis(MINI_ITX, 3)
    ribs = [f for plate in chassis.floor.segments.values() for f in plate.features if isinstance(f, Rib)]
    assert len(ribs) >= 2
    reach = sum(r.u1 - r.u0 for r in ribs) / 2
    assert reach > ATX_PSU.lengths[1] * 0.7  # less only where a floor seam's splice zone interrupts them


def test_the_board_moves_aside_for_the_supply() -> None:
    chassis = _chassis(MINI_ITX, 3)
    psu = chassis._psu_layout()
    assert psu is not None
    assert all(y < psu.y0 for _, y in chassis._standoffs().values())


def test_a_supply_too_tall_for_the_chassis_is_refused() -> None:
    with pytest.raises(ValueError, match="no room for an ATX power supply"):
        _chassis(MINI_ITX, 2)
