# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reference set: every rack width at every height, plus a printed rack of each width.

The build exports these and the test suite proves every one of them prints without
supports, fits the bed and assembles without interference.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from .cassette import DriveBay, Vent
from .chassis import GRID_COLUMNS, MAX_UNITS, MIN_UNITS, RackChassis
from .component import Component
from .rack import PrintedRack
from .standards import ATX, DRIVE_2_5, DRIVE_3_5, MINI_ITX, RACK_10_INCH, RACK_19_INCH

DEPTH_10_INCH = 380.0
DEPTH_19_INCH = 470.0
RACK_10_INCH_UNITS = 6
RACK_10_INCH_DEPTH = 300.0
RACK_19_INCH_UNITS = 12
RACK_19_INCH_DEPTH = 600.0
COLUMNS_3_5_19_INCH = (0, 4, 8)
COLUMNS_2_5_19_INCH = (0, 3, 6, 9)


def chassis_19_inch(units: int) -> RackChassis:
    """Even rows: three 3.5 in bays. Odd rows: four 2.5 in bays. ATX board behind."""
    chassis = RackChassis(RACK_19_INCH, units, DEPTH_19_INCH, ATX)
    for row in range(units):
        if row % 2 == 0:
            for column in COLUMNS_3_5_19_INCH:
                chassis.add_module(DriveBay(DRIVE_3_5), column, row)
        else:
            for column in COLUMNS_2_5_19_INCH:
                chassis.add_module(DriveBay(DRIVE_2_5), column, row)
    chassis.build()
    return chassis


def chassis_10_inch(units: int) -> RackChassis:
    """Each row: one bay (3.5 in on even rows, 2.5 in on odd) with a vent beside it. Mini-ITX board behind."""
    chassis = RackChassis(RACK_10_INCH, units, DEPTH_10_INCH, MINI_ITX)
    for row in range(units):
        bay = chassis.add_module(DriveBay(DRIVE_3_5 if row % 2 == 0 else DRIVE_2_5), 0, row)
        chassis.add_module(Vent(), bay.columns, row, GRID_COLUMNS - bay.columns)
    chassis.build()
    return chassis


def printed_rack_10_inch() -> PrintedRack:
    return PrintedRack(RACK_10_INCH, RACK_10_INCH_UNITS, RACK_10_INCH_DEPTH)


def printed_rack_19_inch() -> PrintedRack:
    return PrintedRack(RACK_19_INCH, RACK_19_INCH_UNITS, RACK_19_INCH_DEPTH)


def reference_builders() -> dict[str, Callable[[], Component]]:
    """Every reference design by name; each builder makes a fresh, fully built assembly."""
    builders: dict[str, Callable[[], Component]] = {}
    for units in range(MIN_UNITS, MAX_UNITS + 1):
        builders[f"chassis_10in_{units}U"] = partial(chassis_10_inch, units)
        builders[f"chassis_19in_{units}U"] = partial(chassis_19_inch, units)
    builders[f"rack_10in_{RACK_10_INCH_UNITS}U"] = printed_rack_10_inch
    builders[f"rack_19in_{RACK_19_INCH_UNITS}U"] = printed_rack_19_inch
    return builders
