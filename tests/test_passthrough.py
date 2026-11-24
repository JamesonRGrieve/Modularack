# SPDX-License-Identifier: AGPL-3.0-or-later
"""SATA pass-through backplanes behind the hot-swap sleds."""

import pytest
from build123d import Vector

from modularack.cassette import REAR_GAP, Cassette, DriveBay
from modularack.chassis import RackChassis
from modularack.checks import check
from modularack.passthrough import CONNECTOR_FROM_Y_SIDE, PLACEHOLDER_ADAPTER, SataAdapter
from modularack.plate import Plate, RectCut, Rib
from modularack.reference import COLUMNS_2_5_19_INCH, COLUMNS_3_5_19_INCH, DEPTH_19_INCH
from modularack.sled import DRIVE_SIDE_CLEARANCE, Sled
from modularack.standards import ATX, DRIVE_2_5, DRIVE_2_5_7MM, DRIVE_3_5, RACK_19_INCH, DriveFormFactor


def _bay(drive: DriveFormFactor, columns: tuple[int, ...], units: int = 1) -> RackChassis:
    chassis = RackChassis(RACK_19_INCH, units, DEPTH_19_INCH, ATX)
    for column in columns:
        chassis.add_module(DriveBay(drive, levels=1, pass_through=PLACEHOLDER_ADAPTER), column, 0)
    chassis.build()
    return chassis


def test_the_connector_position_matches_both_sff_drawings() -> None:
    # A11 is datum B's offset from the drive's centreline: 4.80 mm (SFF-8223) and 20.68 mm (SFF-8323).
    assert DRIVE_2_5.width / 2 - CONNECTOR_FROM_Y_SIDE == pytest.approx(4.80, abs=0.01)
    assert DRIVE_3_5.width / 2 - CONNECTOR_FROM_Y_SIDE == pytest.approx(20.68, abs=0.01)


def test_the_placeholder_adapter_is_flagged_unmeasured() -> None:
    assert not PLACEHOLDER_ADAPTER.measured
    assert "PLACEHOLDER" in PLACEHOLDER_ADAPTER.name


@pytest.mark.parametrize(("drive", "columns"), [(DRIVE_3_5, COLUMNS_3_5_19_INCH), (DRIVE_2_5, COLUMNS_2_5_19_INCH)])
def test_each_sled_gets_a_collar_window_and_rail_stops(drive: DriveFormFactor, columns: tuple[int, ...]) -> None:
    chassis = _bay(drive, columns)
    report = check(chassis)
    assert report.clean, report
    for child in chassis.children.values():
        if not isinstance(child, Cassette):
            continue
        stop = child.children[f"{child.name}_rear_stop"]
        assert isinstance(stop, Plate)
        sleds = [c for c in child.children.values() if isinstance(c, Sled)]
        windows = [f for f in stop.features if isinstance(f, RectCut)]
        assert len(windows) == len(sleds)
        for window in windows:
            assert window.u1 - window.u0 == pytest.approx(PLACEHOLDER_ADAPTER.plug_width + 0.4)
        # The rail stops reach forward to the drive's connector end: the sled stops fully mated.
        stops = [f for f in stop.features if isinstance(f, Rib) and f.height > PLACEHOLDER_ADAPTER.body_depth]
        assert len(stops) == 2 * len(sleds)
        assert stops[0].height == pytest.approx(PLACEHOLDER_ADAPTER.body_depth + REAR_GAP)


def test_the_window_sits_behind_the_drives_connector() -> None:
    chassis = _bay(DRIVE_3_5, COLUMNS_3_5_19_INCH[:1])
    cassette = next(c for c in chassis.children.values() if isinstance(c, Cassette))
    stop = cassette.children[f"{cassette.name}_rear_stop"]
    sled = next(c for c in cassette.children.values() if isinstance(c, Sled))
    assert isinstance(stop, Plate)
    window = next(f for f in stop.features if isinstance(f, RectCut))
    rack = stop.frame.to_rack(Vector((window.u0 + window.u1) / 2, (window.v0 + window.v1) / 2, 0))
    drive_y = sled.placement.position.Y + sled.geometry.rail_width + DRIVE_SIDE_CLEARANCE
    assert pytest.approx(drive_y + CONNECTOR_FROM_Y_SIDE, abs=1e-6) == rack.Y


def test_adapters_too_tall_for_stacked_sleds_are_refused() -> None:
    # Raised on its receptacle so the lower one clears the floor; the two still collide.
    tall = SataAdapter("tall", 52, 12, 12, 46, 6, (0, -3), measured=True)
    chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX)
    chassis.add_module(DriveBay(DRIVE_2_5_7MM, levels=2, pass_through=tall), COLUMNS_2_5_19_INCH[0], 0)
    with pytest.raises(ValueError, match="taller than"):
        chassis.build()
