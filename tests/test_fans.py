# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fan grilles for every common spare fan: front fan bays, rear wall, cover, and free-standing plates."""

import pytest

from modularack.chassis import RackChassis
from modularack.checks import check
from modularack.fans import FanBay, FanPlate
from modularack.layout import MK3S_BED
from modularack.printability import fits_bed, overhangs
from modularack.reference import DEPTH_19_INCH
from modularack.standards import ATX, FAN_SCREW_CLEARANCE, FANS, RACK_19_INCH


@pytest.mark.parametrize("size", sorted(FANS))
def test_every_fans_screw_pattern_sits_on_its_frame(size: int) -> None:
    spec = FANS[size]
    for spacing in spec.spacings:
        # Each screw hole lies inside the frame's corners and outside the swept area it opens.
        corner = spacing / 2 + (FAN_SCREW_CLEARANCE + spec.tolerance) / 2
        assert corner < spec.frame / 2
        assert spacing / 2 * 2**0.5 > spec.blade_diameter / 2


@pytest.mark.parametrize("size", sorted(FANS))
def test_a_free_standing_grille_prints_for_every_size(size: int) -> None:
    part = FanPlate(f"fan_{size}", size).solids()["plate"]
    assert part.is_valid and len(part.solids()) == 1
    assert fits_bed(part, MK3S_BED)
    assert not overhangs(part)


def test_a_chassis_with_front_rear_and_cover_fans_prints_and_assembles() -> None:
    chassis = RackChassis(RACK_19_INCH, 2, DEPTH_19_INCH, ATX, rear_fans=(60, 40), cover_fans=(120, 92))
    chassis.add_module(FanBay(size=40), 0, 0)
    chassis.add_module(FanBay(rows=2, size=60), 4, 0)
    chassis.build()
    report = check(chassis)
    assert report.clean, report


def test_a_fan_that_cannot_fit_is_refused_with_the_room_there_is() -> None:
    with pytest.raises(ValueError, match="doesn't fit"):
        RackChassis(RACK_19_INCH, 2, DEPTH_19_INCH, ATX, rear_fans=(80,)).build()
    with pytest.raises(ValueError, match="FanPlate"):
        RackChassis(RACK_19_INCH, 4, DEPTH_19_INCH, ATX, cover_fans=(140,)).build()
    with pytest.raises(ValueError, match=r"FanBay doesn.t fit a 43\.7 mm face"):
        chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX)
        chassis.add_module(FanBay(size=60), 0, 0)
        chassis.build()


def test_a_fan_plate_takes_any_mix_of_fans_that_fits_the_bed() -> None:
    plate = FanPlate("mixed", (120, 92, 80, 40, 40))
    part = plate.solids()["plate"]
    assert part.is_valid and len(part.solids()) == 1
    assert fits_bed(part, MK3S_BED)
    assert not overhangs(part)
    assert sum(isinstance(f, type(plate.plate.features[0])) for f in plate.plate.features) == 5


def test_a_fan_plate_refuses_fans_that_do_not_fit() -> None:
    with pytest.raises(ValueError, match="bed takes"):
        FanPlate("too many", (200, 140))
