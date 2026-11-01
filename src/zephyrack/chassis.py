# SPDX-License-Identifier: AGPL-3.0-or-later
"""An nU rack chassis: four walls, a floor, and a grid of front-panel modules."""

from __future__ import annotations

from build123d import Part, Vector

from .component import Component
from .floor import Floor
from .front_panel import BAY_3_5_WIDTH_SEGMENTS, Bay35, FrontPanelModule
from .standards import MINI_ITX, RACK_UNIT, MotherboardFormFactor
from .wall import WallSegment, WallSide, stack_units

GRID_COLUMNS = 12
GRID_ROWS_PER_UNIT = 2
FRONT_MODULE_GAP = 0.254
"""Clearance between the front wall's inner face and a module's centre plane (0.01 in)."""
DEFAULT_WALL_THICKNESS = 6.35
DEFAULT_FLOOR_THICKNESS = 3.175


class GridOccupiedError(ValueError):
    """A front module was placed over cells that are taken or off the grid."""


class RackChassis(Component):
    def __init__(
        self,
        depth: float,
        width: float,
        units: int,
        wall_thickness: float = DEFAULT_WALL_THICKNESS,
        floor_thickness: float = DEFAULT_FLOOR_THICKNESS,
        motherboard_support: MotherboardFormFactor = MINI_ITX,
    ) -> None:
        super().__init__(f"rack_chassis_{units}U")
        self.depth = depth
        self.width = width
        self.units = units
        self.height = units * RACK_UNIT
        self.wall_thickness = wall_thickness
        self.rows = GRID_ROWS_PER_UNIT * units
        self.segment_width = width / GRID_COLUMNS
        self.segment_height = self.height / self.rows
        self.occupied = [[False] * GRID_COLUMNS for _ in range(self.rows)]
        self.add_child("floor", Floor(width, depth, floor_thickness, motherboard_support), Vector(0, 0, 0))
        self._add_walls()

    def solids(self) -> dict[str, Part]:
        return {}

    def _add_walls(self) -> None:
        t = self.wall_thickness
        centres = {
            WallSide.FRONT: (t / 2, 0.0),
            WallSide.BACK: (self.depth - t / 2, 0.0),
            WallSide.LEFT: (self.depth / 2, -self.width / 2 + t / 2),
            WallSide.RIGHT: (self.depth / 2, self.width / 2 - t / 2),
        }
        for side, (x, y) in centres.items():
            z = 0.0
            for index, units in enumerate(stack_units(self.units)):
                name = f"{side}_wall_{units}U_{index}"
                segment = WallSegment(side, self.width, self.depth, units, t, index, name)
                self.add_child(name, segment, Vector(x, y, z + segment.height / 2))
                z += segment.height

    def is_available(self, column: int, row: int, width_segments: int, height_segments: int) -> bool:
        if column < 0 or row < 0 or column + width_segments > GRID_COLUMNS or row + height_segments > self.rows:
            return False
        return not any(
            self.occupied[r][c]
            for r in range(row, row + height_segments)
            for c in range(column, column + width_segments)
        )

    def add_front_module(self, module: FrontPanelModule, column: int, row: int) -> None:
        if not self.is_available(column, row, module.width_segments, module.height_segments):
            raise GridOccupiedError(
                f"{module.name} ({module.width_segments}x{module.height_segments}) does not fit at "
                f"column {column}, row {row} of {self.name}"
            )
        for r in range(row, row + module.height_segments):
            for c in range(column, column + module.width_segments):
                self.occupied[r][c] = True
        module.fit(self.segment_width, self.segment_height)
        y = -self.width / 2 + self.segment_width * (column + module.width_segments / 2)
        z = self.segment_height * (row + module.height_segments / 2)
        self.add_child(f"front_module_{column}_{row}", module, Vector(self.wall_thickness + FRONT_MODULE_GAP, y, z))

    def fill_with_drive_bays(self) -> None:
        """Fill every free run of three cells, row by row, with a 3.5 in bay."""
        for row in range(self.rows):
            for column in range(0, GRID_COLUMNS, BAY_3_5_WIDTH_SEGMENTS):
                bay = Bay35(f"hdd_bay_{column}_{row}")
                if self.is_available(column, row, bay.width_segments, bay.height_segments):
                    self.add_front_module(bay, column, row)
