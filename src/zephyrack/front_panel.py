# SPDX-License-Identifier: AGPL-3.0-or-later
"""Modules that occupy cells of a chassis's front-panel grid."""

from __future__ import annotations

from build123d import Box, Part, Pos, Vector

from .component import Component

MODULE_EXPLODE_RATIO = 1.5
"""Front modules pull forward this many explode distances, clear of the front wall."""


class FrontPanelModule(Component):
    """A block spanning width_segments x height_segments grid cells, `depth` deep along X.

    The chassis sizes it with `fit` once it knows its grid cell size.
    """

    def __init__(self, width_segments: int, height_segments: int, depth: float, name: str) -> None:
        if width_segments < 1 or height_segments < 1:
            raise ValueError(f"{name} must span at least one grid cell")
        super().__init__(name)
        self.width_segments = width_segments
        self.height_segments = height_segments
        self.depth = depth
        self.width = 0.0
        self.height = 0.0

    def fit(self, segment_width: float, segment_height: float) -> None:
        self.width = self.width_segments * segment_width
        self.height = self.height_segments * segment_height

    def body(self) -> Part:
        if self.width == 0.0:
            raise RuntimeError(f"{self.name} has not been fitted to a chassis grid")
        return Box(self.depth, self.width, self.height)

    def solids(self) -> dict[str, Part]:
        return {"panel": self.body()}

    def explode_offset(self, distance: float) -> Vector:
        return Vector(-MODULE_EXPLODE_RATIO * distance, 0, 0)


BAY_3_5_WIDTH_SEGMENTS = 3
BAY_3_5_HEIGHT_SEGMENTS = 1
BAY_3_5_DEPTH = 38.1
HANDLE_WIDTH_RATIO = 0.8
HANDLE_HEIGHT_RATIO = 0.6
HANDLE_DEPTH_RATIO = 0.3


class Bay35(FrontPanelModule):
    """A 3.5 in drive bay face: three cells wide, one high, with a handle recess in its front face."""

    def __init__(self, name: str = "bay_3_5") -> None:
        super().__init__(BAY_3_5_WIDTH_SEGMENTS, BAY_3_5_HEIGHT_SEGMENTS, BAY_3_5_DEPTH, name)

    def body(self) -> Part:
        handle_depth = self.depth * HANDLE_DEPTH_RATIO
        handle = Box(handle_depth, self.width * HANDLE_WIDTH_RATIO, self.height * HANDLE_HEIGHT_RATIO)
        return super().body() - Pos(-self.depth / 2 + handle_depth / 2, 0, 0) * handle
