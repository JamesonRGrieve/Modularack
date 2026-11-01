# SPDX-License-Identifier: AGPL-3.0-or-later
"""The chassis floor, drilled for every motherboard up to the largest it supports."""

from __future__ import annotations

from build123d import Box, Cylinder, Part, Pos, Vector

from .component import Component
from .standards import (
    ATX,
    HOLE_POSITIONS_FROM_C,
    MICRO_ATX,
    MINI_ITX,
    MotherboardFormFactor,
    MountingHole,
)

FORM_FACTORS_BY_SIZE = (MINI_ITX, MICRO_ATX, ATX)
"""Smallest to largest. A floor for one form factor also takes every smaller one."""
STANDOFF_HOLE_DIAMETER = 6.35
"""Through hole for each board standoff (1/4 in)."""


def supported_holes(largest: MotherboardFormFactor) -> frozenset[MountingHole]:
    """Every mounting hole needed to take `largest` and all smaller form factors."""
    if largest not in FORM_FACTORS_BY_SIZE:
        raise ValueError(f"Unsupported form factor {largest.name!r}")
    sizes = FORM_FACTORS_BY_SIZE[: FORM_FACTORS_BY_SIZE.index(largest) + 1]
    return frozenset().union(*(form_factor.holes for form_factor in sizes))


def standoff_positions(largest: MotherboardFormFactor, chassis_depth: float) -> dict[MountingHole, tuple[float, float]]:
    """Standoff centres in chassis X/Y, with the largest board centred and its I/O edge toward the back.

    Every ATX-family board shares hole positions relative to hole C, so the smaller
    boards' holes land on the same C datum as the largest board's.
    """
    rear_edge_x = chassis_depth / 2 + largest.depth / 2
    left_edge_y = largest.width / 2
    cx, cy = largest.hole_c_from_corner
    positions = {}
    for hole in sorted(supported_holes(largest)):
        dx, dy = HOLE_POSITIONS_FROM_C[hole]
        positions[hole] = (rear_edge_x - (cy + dy), left_edge_y - (cx + dx))
    return positions


class Floor(Component):
    """A plate spanning the chassis footprint, with standoff holes cut through it."""

    def __init__(
        self,
        chassis_width: float,
        chassis_depth: float,
        thickness: float,
        motherboard_support: MotherboardFormFactor,
        name: str = "floor",
    ) -> None:
        super().__init__(name)
        self.width = chassis_width
        self.depth = chassis_depth
        self.thickness = thickness
        self.motherboard_support = motherboard_support

    def solids(self) -> dict[str, Part]:
        plate = Pos(self.depth / 2, 0, self.thickness / 2) * Box(self.depth, self.width, self.thickness)
        for x, y in standoff_positions(self.motherboard_support, self.depth).values():
            if not (0 < x < self.depth and abs(y) < self.width / 2):
                raise ValueError(
                    f"{self.motherboard_support.name} standoff at ({x:.2f}, {y:.2f}) falls outside "
                    f"a {self.depth} x {self.width} floor"
                )
            plate -= Pos(x, y, self.thickness / 2) * Cylinder(STANDOFF_HOLE_DIAMETER / 2, self.thickness)
        return {"floor": plate}

    def explode_offset(self, distance: float) -> Vector:
        return Vector(0, 0, distance)
