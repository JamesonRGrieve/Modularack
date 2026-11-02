# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reference set: every rack width at every height, plus a printed rack of each width.

The build exports these and the test suite proves every one of them prints without
supports, fits the bed and assembles without interference.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from .cassette import DriveBay, Vent
from .chassis import GRID_COLUMNS, MAX_UNITS, MIN_UNITS, EarStyle, RackChassis
from .component import Component
from .rack import PrintedRack
from .servers import Sacrifice, ServerRails
from .standards import ATX, DRIVE_2_5, DRIVE_3_5, MINI_ITX, RACK_10_INCH, RACK_19_INCH
from .web import PostChannel

DEPTH_10_INCH = 380.0
REAR_SPAN_19_INCH = (520.0, 640.0)
"""Front posts' front face to rear posts' front face, shortest and longest."""
DEPTH_19_INCH = 470.0
RACK_10_INCH_UNITS = 6
RACK_10_INCH_DEPTH = 300.0
RACK_19_INCH_UNITS = 12
RACK_19_INCH_DEPTH = 600.0
COLUMNS_3_5_19_INCH = (0, 4, 8)
COLUMNS_2_5_19_INCH = (0, 3, 6, 9)


def chassis_19_inch(
    units: int,
    ear_style: EarStyle = EarStyle.SCREW,
    one_piece: bool = False,
    knee_brace_units: int | None = None,
    toolless_cover: bool = False,
    toolless_box: bool = False,
    toolless_modules: bool = False,
) -> RackChassis:
    """Even rows: three 3.5 in bays. Odd rows: four 2.5 in bays. ATX board behind."""
    chassis = RackChassis(
        RACK_19_INCH,
        units,
        DEPTH_19_INCH,
        ATX,
        ear_style=ear_style,
        one_piece=one_piece,
        knee_brace_units=knee_brace_units,
        toolless_cover=toolless_cover,
        toolless_box=toolless_box,
        toolless_modules=toolless_modules,
    )
    for row in range(units):
        if row % 2 == 0:
            for column in COLUMNS_3_5_19_INCH:
                chassis.add_module(DriveBay(DRIVE_3_5), column, row)
        else:
            for column in COLUMNS_2_5_19_INCH:
                chassis.add_module(DriveBay(DRIVE_2_5), column, row)
    chassis.build()
    return chassis


def chassis_10_inch(
    units: int,
    ear_style: EarStyle = EarStyle.SCREW,
    one_piece: bool = False,
    knee_brace_units: int | None = None,
    toolless_cover: bool = False,
    toolless_box: bool = False,
    toolless_modules: bool = False,
) -> RackChassis:
    """Each row: one bay (3.5 in on even rows, 2.5 in on odd) with a vent beside it. Mini-ITX board behind."""
    chassis = RackChassis(
        RACK_10_INCH,
        units,
        DEPTH_10_INCH,
        MINI_ITX,
        ear_style=ear_style,
        one_piece=one_piece,
        knee_brace_units=knee_brace_units,
        toolless_cover=toolless_cover,
        toolless_box=toolless_box,
        toolless_modules=toolless_modules,
    )
    for row in range(units):
        bay = chassis.add_module(DriveBay(DRIVE_3_5 if row % 2 == 0 else DRIVE_2_5), 0, row)
        chassis.add_module(Vent(), bay.columns, row, GRID_COLUMNS - bay.columns)
    chassis.build()
    return chassis


def chassis_19_inch_rear_supported() -> RackChassis:
    """Four-post: snap ears, the back carried on rear posts 520-640 mm behind the front posts."""
    chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX, ear_style=EarStyle.SNAP, rear_support=REAR_SPAN_19_INCH)
    for column in COLUMNS_3_5_19_INCH:
        chassis.add_module(DriveBay(DRIVE_3_5), column, 0)
    chassis.build()
    return chassis


def chassis_19_inch_web_clamped() -> RackChassis:
    """Two-post channel rack: one-piece hook corners clamped to the posts' side webs (common 3 in channel)."""
    chassis = RackChassis(
        RACK_19_INCH, 1, DEPTH_19_INCH, ATX, ear_style=EarStyle.HOOK, one_piece=True, web_clamp=PostChannel()
    )
    for column in COLUMNS_3_5_19_INCH:
        chassis.add_module(DriveBay(DRIVE_3_5), column, 0)
    chassis.build()
    return chassis


def chassis_19_inch_powered(units: int = 3) -> RackChassis:
    """A server chassis: Mini-ITX board, ATX power supply (flat from 3U, on its side in 4U with an ATX
    board), a row of 3.5 in bays and a 60 mm rear fan."""
    chassis = RackChassis(RACK_19_INCH, units, DEPTH_19_INCH, MINI_ITX, power_supply=True, rear_fans=(60,))
    for column in COLUMNS_3_5_19_INCH:
        chassis.add_module(DriveBay(DRIVE_3_5), column, 0)
    chassis.build()
    return chassis


def printed_rack_10_inch() -> PrintedRack:
    return PrintedRack(RACK_10_INCH, RACK_10_INCH_UNITS, RACK_10_INCH_DEPTH)


def printed_rack_19_inch() -> PrintedRack:
    return PrintedRack(RACK_19_INCH, RACK_19_INCH_UNITS, RACK_19_INCH_DEPTH)


def _coupons() -> Component:
    # Imported here: coupons are cut from this module's reference chassis.
    from .coupons import CouponSet

    return CouponSet()


def reference_builders() -> dict[str, Callable[[], Component]]:
    """Every reference design by name; each builder makes a fresh, fully built assembly."""
    builders: dict[str, Callable[[], Component]] = {}
    for units in range(MIN_UNITS, MAX_UNITS + 1):
        builders[f"chassis_10in_{units}U"] = partial(chassis_10_inch, units)
        builders[f"chassis_19in_{units}U"] = partial(chassis_19_inch, units)
    # Square-hole racks: tool-less hook ears, on the smallest (worst-case) chassis of each width.
    builders["chassis_10in_1U_hook"] = partial(chassis_10_inch, 1, EarStyle.HOOK)
    builders["chassis_19in_1U_hook"] = partial(chassis_19_inch, 1, EarStyle.HOOK)
    builders["chassis_10in_1U_snap"] = partial(chassis_10_inch, 1, EarStyle.SNAP)
    builders["chassis_19in_1U_snap"] = partial(chassis_19_inch, 1, EarStyle.SNAP)
    # The strongest two-post set-ups: one-piece upright corners propped by knee braces.
    builders["chassis_19in_1U_snap_braced"] = partial(chassis_19_inch, 1, EarStyle.SNAP, True, 2)
    builders["chassis_10in_2U_screw_braced"] = partial(chassis_10_inch, 2, EarStyle.SCREW, True, 1)
    builders["chassis_19in_1U_snap_rear"] = chassis_19_inch_rear_supported
    builders["chassis_19in_1U_hook_web"] = chassis_19_inch_web_clamped
    # Tool-less boxes: walls on floor dovetails, a latched rear wall, a sliding latched cover.
    builders["chassis_10in_2U_toolless"] = partial(chassis_10_inch, 2, EarStyle.HOOK, True, toolless_box=True)
    builders["chassis_19in_2U_toolless"] = partial(chassis_19_inch, 2, EarStyle.SNAP, toolless_box=True)
    builders["chassis_19in_1U_toolless"] = partial(chassis_19_inch, 1, EarStyle.HOOK, True, 2, toolless_box=True)
    builders["chassis_19in_3U_psu"] = chassis_19_inch_powered
    builders["rails_r720"] = ServerRails
    builders["rails_r720_hole"] = partial(ServerRails, sacrifice=Sacrifice.HOLE)
    builders["shelf_19in"] = partial(ServerRails, shelf=True)
    builders["coupons"] = _coupons
    builders[f"rack_10in_{RACK_10_INCH_UNITS}U"] = printed_rack_10_inch
    builders[f"rack_19in_{RACK_19_INCH_UNITS}U"] = printed_rack_19_inch
    return builders
