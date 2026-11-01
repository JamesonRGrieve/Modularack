# SPDX-License-Identifier: AGPL-3.0-or-later
"""Published dimensional standards Zephyrack parts are built against, in millimetres.

Every value here comes from a cited source. Part code imports these instead of
restating numbers, so a correction lands in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MM_PER_INCH = 25.4

# EIA-310 (via Wikipedia "19-inch rack" / "Rack unit", digital-loggers.com/rackspecs.html).
RACK_UNIT = 44.45
"""Height of 1U."""
PANEL_HEIGHT_DEDUCTION = 0.79
"""A front panel is this much shorter than its nU slot (1/32 in)."""
U_HOLE_OFFSETS = (6.35, 22.225, 38.1)
"""Mounting hole centres within one U, measured up from the U boundary (1/2-5/8-5/8 in pitch)."""


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
RACK_STANDARDS = {standard.name: standard for standard in (RACK_19_INCH, RACK_10_INCH)}


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
FORM_FACTORS = {form_factor.name: form_factor for form_factor in (MINI_ITX, MICRO_ATX, ATX)}
