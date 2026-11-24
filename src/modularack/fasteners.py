# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fastener geometry every joint is cut for, in millimetres.

Insert, nut and clearance values are read from bd_warehouse 0.4 (tests re-measure
them, so a library update that changes them fails loudly instead of drifting).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

STANDARD_SCREW_LENGTHS = (6, 8, 10, 12, 14, 16, 20, 25, 30)
"""Metric screw lengths the bill of materials rounds to."""


@dataclass(frozen=True)
class InsertSpec:
    """A heat-set insert and the hole it is pressed into."""

    name: str
    bore_diameter: float
    length: float
    relief_diameter: float
    """Clearance continuing past the insert, for the screw tip."""


# bd_warehouse InsertHole for CNC Kitchen inserts, measured: bore x depth, then a 3.4 mm relief.
INSERT_M3_LONG = InsertSpec("M3x5.7 heat-set insert (CNC Kitchen)", 4.089, 5.7, 3.4)
INSERT_M3_SHORT = InsertSpec("M3x3 heat-set insert (CNC Kitchen)", 4.089, 3.0, 3.4)

M3_CLEARANCE = 3.4
"""ISO normal clearance (bd_warehouse)."""
M3_COUNTERSINK_DIAMETER = 6.0
"""ISO 10642 M3 head is 5.64 mm across (bd_warehouse); the 90 degree seat is cut slightly over."""
M3_NUT_ACROSS_CORNERS = 6.35
"""ISO 4032 M3 hex nut, 5.5 mm across flats."""
M3_NUT_ACROSS_FLATS = 5.5
M3_NUT_HEIGHT = 2.4
M3_NUT_POCKET_CLEARANCE = 0.3

RACK_SCREW_CLEARANCE = 6.6
"""ISO normal clearance for M6, which also passes 10-32 and 12-24 rack screws."""
M6_NUT_ACROSS_CORNERS = 11.547
"""ISO 4032 M6 hex nut, 10 mm across flats."""
M6_NUT_HEIGHT = 5.2

DRIVE_SCREW_HEAD_RECESS_DIAMETER = 7.4
"""Counterbore that clears common #6 and M3 pan and cheese heads; prove it with a test coupon."""
DRIVE_SCREW_HEAD_RECESS_DEPTH = 2.8

EDGE_INSERT = INSERT_M3_LONG
EDGE_INSERT_WALL = 1.4
"""Plastic left on each side of an edge insert bore."""
EDGE_INSERT_MIN_THICKNESS = 2 * (EDGE_INSERT.bore_diameter / 2 * math.sqrt(2) + EDGE_INSERT_WALL)
"""A centred teardrop bore reaches r*sqrt(2) up to its roof; keep a wall above that and the same below."""
EDGE_INSERT_RELIEF_DEPTH = 4.0


def screw_length(clamped_thickness: float, engagement: float, relief: float) -> int:
    """The shortest standard screw that passes the clamped part and fully engages its thread."""
    for length in STANDARD_SCREW_LENGTHS:
        if clamped_thickness + engagement <= length <= clamped_thickness + engagement + relief:
            return length
    raise ValueError(
        f"No standard screw between {clamped_thickness + engagement:.1f} and "
        f"{clamped_thickness + engagement + relief:.1f} mm"
    )
