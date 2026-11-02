# SPDX-License-Identifier: AGPL-3.0-or-later
"""Published dimensional standards Zephyrack parts are built against, in millimetres.

Every value here comes from a cited source. Part code imports these instead of
restating numbers, so a correction lands in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

MM_PER_INCH = 25.4

# EIA-310 (via Wikipedia "19-inch rack" / "Rack unit", digital-loggers.com/rackspecs.html).
RACK_UNIT = 44.45
"""Height of 1U."""
PANEL_HEIGHT_DEDUCTION = 0.79
"""A front panel is this much shorter than its nU slot (1/32 in)."""
U_HOLE_OFFSETS = (6.35, 22.225, 38.1)
"""Mounting hole centres within one U, measured up from the U boundary (1/2-5/8-5/8 in pitch)."""


POST_INNER_EDGE_TO_HOLE = 7.55
"""19 in: hole columns are 465.1 apart and the clear opening is 450, so each post's inner edge sits
7.55 mm inside its hole column. Applied to 10 in racks too, which have no standard of their own."""


@dataclass(frozen=True)
class RackStandard:
    """Horizontal dimensions of one rack width."""

    name: str
    panel_width: float
    """Overall front panel width, ear to ear."""
    hole_spacing: float
    """Centre-to-centre distance between the left and right hole columns."""
    hole_spacing_tolerance: float
    """Variation in hole_spacing seen across real racks; mounting holes are slotted by this much."""

    @property
    def opening(self) -> float:
        """Clear width between the posts."""
        return self.hole_spacing - 2 * POST_INNER_EDGE_TO_HOLE


RACK_19_INCH = RackStandard(
    name="19in",
    panel_width=482.6,  # 19.00 in
    hole_spacing=465.1,  # 18 5/16 in; Wikipedia gives a 464.2-465.8 range
    hole_spacing_tolerance=0.8,
)
RACK_10_INCH = RackStandard(
    name="10in",
    panel_width=254.0,  # 10.00 in
    # No formal standard: 236.525 mm (9.312 in) is the de facto community figure and
    # brands vary by about 1 mm (geerlingguy/mini-rack issues 29 and 280).
    hole_spacing=236.525,
    hole_spacing_tolerance=1.0,
)


def panel_height(units: int) -> float:
    """Height of an nU front panel."""
    if units < 1:
        raise ValueError(f"A panel spans at least 1U, got {units}")
    return units * RACK_UNIT - PANEL_HEIGHT_DEDUCTION


def rack_hole_heights(units: int) -> list[float]:
    """Centre heights of every mounting hole in an nU slot, measured up from the slot's bottom edge."""
    if units < 1:
        raise ValueError(f"A slot spans at least 1U, got {units}")
    return [u * RACK_UNIT + offset for u in range(units) for offset in U_HOLE_OFFSETS]


class MountingHole(StrEnum):
    """Lettered motherboard mounting holes shared by the ATX family."""

    A = "A"
    B = "B"
    C = "C"
    F = "F"
    G = "G"
    H = "H"
    J = "J"
    K = "K"
    L = "L"
    M = "M"
    R = "R"
    S = "S"
    X = "X"
    Y = "Y"
    Z = "Z"
    F_ALT = "F'"
    H_ALT = "H'"
    J_ALT = "J'"
    K_ALT = "K'"
    L_ALT = "L'"
    M_ALT = "M'"
    Y_ALT = "Y'"


# Hole centres relative to hole C, +x toward hole F (along the rear I/O edge),
# +y toward the front of the board. Intel microATX 1.2 Figure 3 (datum B) and
# ATX 2.2 Figure 3 (datum A), converted from inches.
HOLE_POSITIONS_FROM_C: dict[MountingHole, tuple[float, float]] = {
    MountingHole.C: (0.0, 0.0),
    MountingHole.F: (157.48, 22.86),
    MountingHole.H: (0.0, 154.94),
    MountingHole.J: (157.48, 154.94),
    MountingHole.L: (0.0, 227.33),
    MountingHole.M: (157.48, 227.33),
    MountingHole.B: (-45.72, 0.0),
    MountingHole.S: (-45.72, 154.94),
    MountingHole.R: (-66.04, 154.94),
    MountingHole.A: (-124.46, 0.0),
    MountingHole.G: (-124.46, 154.94),
    MountingHole.K: (-124.46, 227.33),
    # SSI EEB 2011 v1.0.1 Figure 2 (datum A, the ATX datum): the extended rows and the
    # alternate ("prime") locations a board may use when a legacy hole is blocked.
    MountingHole.X: (-129.54, 312.42),
    MountingHole.Y: (0.0, 312.42),
    MountingHole.Z: (157.48, 312.42),
    MountingHole.Y_ALT: (-45.72, 312.42),
    MountingHole.F_ALT: (157.48, 0.0),
    MountingHole.H_ALT: (-45.72, 177.8),
    MountingHole.J_ALT: (157.48, 181.61),
    MountingHole.K_ALT: (-124.46, 250.19),
    MountingHole.L_ALT: (0.0, 250.19),
    MountingHole.M_ALT: (157.48, 250.19),
}
MOUNTING_HOLE_DIAMETER = 3.96
"""Board mounting hole diameter (0.156 in)."""

IO_APERTURE_WIDTH = 158.75
IO_APERTURE_HEIGHT = 44.45
IO_APERTURE_OFFSET_FROM_C = 7.52
"""Distance from hole C, toward hole F, to the near edge of the rear I/O aperture."""
IO_APERTURE_BELOW_BOARD_TOP = 3.81
"""The aperture's bottom edge sits this far below the top surface of a 1.57 mm board."""


@dataclass(frozen=True)
class MotherboardFormFactor:
    """A board outline, where its datum hole sits, and which holes it uses."""

    name: str
    width: float
    """Along the rear I/O edge."""
    depth: float
    """From the rear I/O edge to the front edge."""
    hole_c_from_corner: tuple[float, float]
    """Hole C measured from the rear-left corner, with the I/O edge at the top as in the specs."""
    holes: frozenset[MountingHole]

    def hole_positions(self) -> dict[MountingHole, tuple[float, float]]:
        """Hole centres measured from the rear-left corner (+x along the rear edge, +y toward the front)."""
        cx, cy = self.hole_c_from_corner
        return {
            hole: (cx + HOLE_POSITIONS_FROM_C[hole][0], cy + HOLE_POSITIONS_FROM_C[hole][1])
            for hole in sorted(self.holes)
        }


# Outlines: microATX 1.2 Table 3, Mini-ITX 1.1 Table 2. Hole sets: Mini-ITX 1.1 Table 3.
# Hole C offsets: Mini-ITX 1.1 Figure 3 (0.25 in, 0.40 in); microATX 1.2 Figure 3
# (hole B 1.350 in from the left edge, C 1.800 in past B); ATX 2.2 Figure 3 (hole A
# 0.650 in from the left edge, C 4.900 in past A).
MINI_ITX = MotherboardFormFactor(
    name="mini-itx",
    width=170.0,
    depth=170.0,
    hole_c_from_corner=(6.35, 10.16),
    holes=frozenset({MountingHole.C, MountingHole.F, MountingHole.H, MountingHole.J}),
)
MICRO_ATX = MotherboardFormFactor(
    name="micro-atx",
    width=243.84,
    depth=243.84,
    hole_c_from_corner=(80.01, 10.16),
    holes=frozenset(
        {
            MountingHole.B,
            MountingHole.C,
            MountingHole.F,
            MountingHole.H,
            MountingHole.J,
            MountingHole.L,
            MountingHole.M,
            MountingHole.R,
            MountingHole.S,
        }
    ),
)
ATX = MotherboardFormFactor(
    name="atx",
    width=304.8,
    depth=243.84,
    hole_c_from_corner=(140.97, 10.16),
    holes=frozenset(
        {
            MountingHole.A,
            MountingHole.C,
            MountingHole.F,
            MountingHole.G,
            MountingHole.H,
            MountingHole.J,
            MountingHole.K,
            MountingHole.L,
            MountingHole.M,
        }
    ),
)

_ATX_HOLES = ATX.holes
# SSI EEB 2011 v1.0.1 section 2.1: the ATX board "stretched" to 305 x 330 mm, same datum and
# hole C. Legacy ATX holes plus the X/Y/Z row. CEB is the 266.7 mm deep variant without that row.
EEB = MotherboardFormFactor(
    name="ssi-eeb",
    width=304.8,
    depth=330.2,
    hole_c_from_corner=(140.97, 10.16),
    holes=_ATX_HOLES | {MountingHole.X, MountingHole.Y, MountingHole.Z},
)
CEB = MotherboardFormFactor(
    name="ssi-ceb",
    width=304.8,
    depth=266.7,
    hole_c_from_corner=(140.97, 10.16),
    holes=_ATX_HOLES,
)
EEB_ALTERNATE_HOLES = frozenset(
    {
        MountingHole.F_ALT,
        MountingHole.H_ALT,
        MountingHole.J_ALT,
        MountingHole.K_ALT,
        MountingHole.L_ALT,
        MountingHole.M_ALT,
        MountingHole.Y_ALT,
    }
)
"""Alternates a specific EEB/CEB board may use instead of a legacy hole. The spec leaves unused
locations unpopulated, so a chassis adds only the ones its board actually has."""

STANDOFF_HEIGHT = 6.35
"""Board underside above the chassis floor: microATX 1.2 section 2.4.2 requires 0.250 in clearance."""
BOARD_THICKNESS = 1.57
HOLE_C_TO_REAR_PANEL = 12.27
"""Hole row C/B to the inside of the chassis rear panel (microATX 1.2 Figure 4, 0.483 in)."""


@dataclass(frozen=True)
class DriveFormFactor:
    """A drive's outline and its side mounting holes, from its SFF specification."""

    name: str
    width: float
    height: float
    length: float
    side_hole_offsets: tuple[float, float]
    """Side hole centres measured from the connector end."""
    side_hole_height: float
    """Side hole centre above the drive's base."""
    screw: str
    screw_clearance: float


# SFF-8301 Rev 1.9 Table 3-1: A3 width, A1 height (1 in class), A2 length max, A8 and A8+A9
# side holes from the connector end, A10 hole height, 6-32 UNC thread.
DRIVE_3_5 = DriveFormFactor(
    name="3.5in",
    width=101.6,
    height=26.10,
    length=147.0,
    side_hole_offsets=(28.50, 28.50 + 101.60),
    side_hole_height=6.35,
    screw="6-32 UNC x 1/4 in pan head",
    screw_clearance=3.66,  # close fit for #6 (0.144 in)
)
# SFF-8201 Rev 3.4 Table 3-1: A4 width, A1 height (15 mm class), A6 length max, A52/A53 side holes
# from the connector end, A23 hole height, M3 thread.
DRIVE_2_5 = DriveFormFactor(
    name="2.5in",
    width=69.85,
    height=15.0,
    length=100.45,
    side_hole_offsets=(14.0, 90.6),
    side_hole_height=3.0,
    screw="M3x4 pan head (ISO 7045)",
    screw_clearance=3.4,
)
# SFF-8201 Rev 3.4 Table 3-1 A1 heights; the outline and side holes are the same for every height.
DRIVE_2_5_9_5MM = replace(DRIVE_2_5, name="2.5in-9.5mm", height=9.5)
DRIVE_2_5_7MM = replace(DRIVE_2_5, name="2.5in-7mm", height=7.0)


@dataclass(frozen=True)
class FanSize:
    """A square axial fan's frame and screw pattern.

    `spacings` are the screw-hole patterns (centre to centre, square) a grille offers; `tolerance` widens
    the screw holes to take the spread between makers and any doubt in the figure.
    """

    frame: float
    spacings: tuple[float, ...]
    tolerance: float
    source: str

    @property
    def blade_diameter(self) -> float:
        """The swept area the grille opens: a little inside the frame."""
        return self.frame - 4.0


FAN_SCREW_CLEARANCE = 4.4
"""Fan screws (self-tapping #6-32 / M4-ish) and M3 both pass."""

# 120, 140 (square frame) and 200 mm are from Noctua's product pages and NF-A20 datasheet (2026-11-01);
# Noctua notes there is no industry standard at 200 mm, so both of its patterns are offered. 50 and 70 mm
# are from vendor listings (70 mm varies 60-61.5 between makers). 40, 60, 80 and 92 mm are the widely cited
# figures, not checked against a datasheet (Noctua's pages were rate-limited): their holes get extra room.
FANS: dict[int, FanSize] = {
    40: FanSize(40.0, (32.0,), 1.0, "commonly cited; unconfirmed"),
    50: FanSize(50.0, (40.0,), 0.6, "vendor listings, 40.0 +/- 0.3"),
    60: FanSize(60.0, (50.0,), 1.0, "commonly cited; unconfirmed"),
    70: FanSize(70.0, (60.75,), 1.5, "vendor listings, 60-61.5 by maker"),
    80: FanSize(80.0, (71.5,), 1.0, "commonly cited; unconfirmed"),
    92: FanSize(92.0, (82.5,), 1.0, "commonly cited; unconfirmed"),
    120: FanSize(120.0, (105.0,), 0.5, "Noctua NF-A12x25 / NF-A15 pages"),
    140: FanSize(140.0, (124.5,), 0.5, "Noctua (square-frame 140 mm, e.g. NF-A14)"),
    200: FanSize(200.0, (154.0, 170.0), 0.5, "Noctua NF-A20 page and datasheet; no industry standard"),
}
