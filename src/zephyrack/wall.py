# SPDX-License-Identifier: AGPL-3.0-or-later
"""Chassis wall segments, stacked 1U/2U at a time to make an nU wall."""

from __future__ import annotations

from enum import StrEnum

from build123d import Box, Part, Vector

from .component import Component
from .standards import RACK_UNIT

SEGMENT_UNITS = (1, 2)
"""Heights a single wall segment can be, in U."""
STACK_EXPLODE_RATIO = 0.75
"""Extra upward spread per stacked segment, as a fraction of the explode distance."""


class WallSide(StrEnum):
    FRONT = "front"
    BACK = "back"
    LEFT = "left"
    RIGHT = "right"


EXPLODE_DIRECTIONS = {
    WallSide.FRONT: Vector(-1, 0, 0),
    WallSide.BACK: Vector(1, 0, 0),
    WallSide.LEFT: Vector(0, -1, 0),
    WallSide.RIGHT: Vector(0, 1, 0),
}


def stack_units(total_units: int) -> list[int]:
    """Split an nU wall into 2U segments, plus one 1U segment for an odd height."""
    if total_units < 1:
        raise ValueError(f"A wall is at least 1U tall, got {total_units}")
    return [2] * (total_units // 2) + [1] * (total_units % 2)


class WallSegment(Component):
    """One 1U or 2U slab of a chassis wall, centred on its own origin."""

    def __init__(
        self,
        side: WallSide,
        chassis_width: float,
        chassis_depth: float,
        units: int,
        thickness: float,
        stack_index: int,
        name: str,
    ) -> None:
        if units not in SEGMENT_UNITS:
            raise ValueError(f"A wall segment is {SEGMENT_UNITS} U tall, got {units}")
        super().__init__(name)
        self.side = side
        self.units = units
        self.height = units * RACK_UNIT
        self.thickness = thickness
        self.stack_index = stack_index
        if side in (WallSide.FRONT, WallSide.BACK):
            self.size = (thickness, chassis_width, self.height)
        else:
            self.size = (chassis_depth - 2 * thickness, thickness, self.height)

    def solids(self) -> dict[str, Part]:
        return {"wall": Box(*self.size)}

    def explode_offset(self, distance: float) -> Vector:
        lift = Vector(0, 0, self.stack_index * STACK_EXPLODE_RATIO * distance)
        return EXPLODE_DIRECTIONS[self.side] * distance + lift
