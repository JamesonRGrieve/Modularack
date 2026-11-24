# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reference set: every rack width at every height, plus a printed rack of each width.

10 in and 19 in chassis carry drive bays; the two Modularack widths (14.5 in, whose screwed box takes an
ATX board, and 15 in, whose tool-less box does) carry the compact ATX layout: the power supply on its edge
in front of the board with its fan facing out, an intake fan and a power button beside it. A 19 in E-ATX
server takes the deepest board.

The build exports these and the test suite proves every one of them prints without
supports, fits the bed and assembles without interference.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from .cassette import DriveBay, Vent, cells_for
from .chassis import GRID_COLUMNS, MAX_UNITS, MIN_UNITS, EarStyle, RackChassis
from .component import Component
from .fans import FanBay
from .power import PowerButton, PowerSupplyBay, psu_on_edge_fits
from .rack import PrintedRack
from .servers import Sacrifice, ServerRails
from .standards import (
    ATX,
    DRIVE_2_5,
    DRIVE_3_5,
    E_ATX,
    MINI_ITX,
    RACK_10_INCH,
    RACK_14_5_INCH,
    RACK_15_INCH,
    RACK_19_INCH,
    RackStandard,
)
from .web import PostChannel

DEPTH_10_INCH = 380.0
REAR_SPAN_19_INCH = (520.0, 640.0)
"""Front posts' front face to rear posts' front face, shortest and longest."""
DEPTH_19_INCH = 470.0
RACK_10_INCH_UNITS = 6
RACK_10_INCH_DEPTH = 300.0
RACK_19_INCH_UNITS = 12
RACK_19_INCH_DEPTH = 600.0
RACK_MID_UNITS = 12
RACK_MID_DEPTH = 600.0
"""The 14.5 in and 15 in printed racks: deep enough for the compact ATX chassis."""
COMPACT_FAN = 120
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
    toolless_sleds: bool = False,
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
        toolless_sleds=toolless_sleds,
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
    toolless_sleds: bool = False,
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
        toolless_sleds=toolless_sleds,
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


def chassis_compact_atx(
    rack: RackStandard,
    toolless_box: bool,
    ear_style: EarStyle = EarStyle.SCREW,
    one_piece: bool = False,
    toolless_modules: bool = False,
) -> RackChassis:
    """4U ATX: the supply on its edge in front of the board, fan facing out, a 120 mm intake fan and a power
    button beside it, and a 3.5 in bay above the fan. As short as that allows."""
    chassis = RackChassis(
        rack,
        MAX_UNITS,
        0.0,
        ATX,
        ear_style=ear_style,
        one_piece=one_piece,
        toolless_box=toolless_box,
        toolless_modules=toolless_modules,
        toolless_sleds=toolless_modules,
    )
    psu = PowerSupplyBay(rows=MAX_UNITS, on_edge=psu_on_edge_fits(chassis.inner_height))
    beside = chassis.add_module(psu, 0, 0).columns
    button = PowerButton()
    button_columns = cells_for(button, chassis.cell_width)
    chassis.add_module(button, GRID_COLUMNS - button_columns, MAX_UNITS - 1)
    chassis.add_module(FanBay(rows=MAX_UNITS - 1, size=COMPACT_FAN), beside, 0, GRID_COLUMNS - beside)
    chassis.add_module(
        DriveBay(DRIVE_3_5, pinned=toolless_modules), beside, MAX_UNITS - 1, GRID_COLUMNS - beside - button_columns
    )
    chassis.depth = chassis.minimum_depth()
    chassis.build()
    return chassis


def chassis_19_inch_eatx() -> RackChassis:
    """4U tool-less E-ATX server: the board at the rear, the supply on its side beside it at the rear wall,
    80 mm rear fan, and a 3.5 in bay wherever one fits in front, two rows of them; as short as that allows."""
    chassis = RackChassis(RACK_19_INCH, MAX_UNITS, 0.0, E_ATX, toolless_box=True, power_supply=True, rear_fans=(80,))
    for row in (0, 2):
        for column in COLUMNS_3_5_19_INCH:
            chassis.add_module(DriveBay(DRIVE_3_5), column, row)
    chassis.depth = chassis.minimum_depth()
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
    # Fully tool-less: one-piece hook corners (braced two units down for a two-post rack), and no screws
    # between panels, in the modules or on the drives.
    builders["chassis_19in_2U_drawers"] = partial(
        chassis_19_inch,
        2,
        EarStyle.HOOK,
        True,
        2,
        toolless_box=True,
        toolless_modules=True,
        toolless_sleds=True,
    )
    builders["chassis_10in_2U_drawers"] = partial(
        chassis_10_inch, 2, EarStyle.HOOK, True, toolless_box=True, toolless_modules=True, toolless_sleds=True
    )
    builders["chassis_19in_1U_toolless"] = partial(chassis_19_inch, 1, EarStyle.HOOK, True, 2, toolless_box=True)
    builders["chassis_19in_3U_psu"] = chassis_19_inch_powered
    builders["rails_r720"] = ServerRails
    builders["rails_r720_hole"] = partial(ServerRails, sacrifice=Sacrifice.HOLE)
    builders["shelf_19in"] = partial(ServerRails, shelf=True)
    builders["coupons"] = _coupons
    # The compact ATX layout: screwed at 14.5 in, tool-less at 15 in (fully: drawers, pinned sleds, one-piece
    # hook corners).
    builders["chassis_14.5in_4U_atx"] = partial(chassis_compact_atx, RACK_14_5_INCH, False)
    builders["chassis_15in_4U_atx_toolless"] = partial(
        chassis_compact_atx, RACK_15_INCH, True, EarStyle.HOOK, True, toolless_modules=True
    )
    builders["chassis_19in_4U_eatx"] = chassis_19_inch_eatx
    builders[f"rack_10in_{RACK_10_INCH_UNITS}U"] = printed_rack_10_inch
    builders[f"rack_14.5in_{RACK_MID_UNITS}U"] = partial(PrintedRack, RACK_14_5_INCH, RACK_MID_UNITS, RACK_MID_DEPTH)
    builders[f"rack_15in_{RACK_MID_UNITS}U"] = partial(PrintedRack, RACK_15_INCH, RACK_MID_UNITS, RACK_MID_DEPTH)
    builders[f"rack_19in_{RACK_19_INCH_UNITS}U"] = printed_rack_19_inch
    return builders
