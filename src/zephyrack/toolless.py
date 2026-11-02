# SPDX-License-Identifier: AGPL-3.0-or-later
"""A tool-less box: side walls on floor dovetails, a rear wall that latches them, and the `lid` cover.

Assembly, and the reverse to take it apart:

1. The side walls drop onto the floor with the dovetail tabs on their bottom edges in windows in the
   floor's top face, then slide `lid.SLIDE` back into the floor's grooves, which hold the floor up and
   the walls' bottoms together. A wall prints outer face down, so its tabs sit flush with its outer face
   and widen outward; in this mode the walls stand `WALL_INSET` in from the floor's edges, so the floor
   keeps a solid lip outboard of every groove.
2. The rear wall drops in between them. Tenons on its bottom edge locate it in pockets in the floor, and
   an arm at each side, cut free in the wall's plane, springs a tooth into a pocket in the side wall:
   the rear wall can't lift, and the side walls can't slide back out of their grooves. It prints inner
   face down, so the tenons and teeth sit at its inner face, clear of the side walls' rear ends.
3. The cover (`lid`) drops in, slides forward and latches; it holds the rear wall's top down.

To open: release the cover's latch and lift it off; press each rear arm's top end inward and lift the
rear wall out; slide the side walls forward and lift. Everything prints without supports: tabs and teeth
stand on the bed or are in-plane profiles, and the floor's grooves undercut at 45 degrees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Box, Part, Plane, Polygon, Pos, extrude

from . import lid
from .plate import Feature, Plate

WALL_INSET = 3.0
"""The side walls stand this far in from the floor's edges: the floor's lip outboard of each groove."""
TENON_LENGTH = 12.0
TENON_REACH = 3.0
TENON_THICKNESS = 5.0
"""From the rear wall's inner face."""
TENON_PITCH = 120.0
REAR_ARM_WIDTH = 2.4
REAR_ARM_RELIEF = 2.0
REAR_ARM_ROOT = 3.0
"""The relief slot starts this far above the rear wall's bottom edge and runs out through its top."""
REAR_TOOTH = 1.2
REAR_TOOTH_HEIGHT = 4.0
REAR_TOOTH_THICKNESS = 5.0
REAR_TOOTH_TOP_MARGIN = 3.0
"""The tooth's top below the rear wall's top edge."""


def rear_latch_strain(wall_height: float) -> float:
    """Peak bending strain in a rear arm while its tooth rides the side wall: 3 b d / (2 L^2)."""
    top = wall_height - REAR_TOOTH_TOP_MARGIN
    lever = top - REAR_TOOTH_HEIGHT / 2 - REAR_ARM_ROOT
    return 3 * REAR_ARM_WIDTH * (REAR_TOOTH + lid.CLEARANCE) / (2 * lever**2)


def _prism_vw(points: list[tuple[float, float]], u0: float, u1: float) -> Part:
    plane = Plane(origin=(u0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    return extrude(plane * Polygon(*points, align=None), amount=u1 - u0, dir=(1, 0, 0))


def _box(u0: float, v0: float, w0: float, u1: float, v1: float, w1: float) -> Part:
    return Pos((u0 + u1) / 2, (v0 + v1) / 2, (w0 + w1) / 2) * Box(u1 - u0, v1 - v0, w1 - w0)


@dataclass
class FloorSocket(Feature):
    """In the floor's top face, for one wall tab: the dovetail groove (u `lock`) and the window it drops
    through (u `window`). `edge_v` is the wall's outer face in the floor's v; `sign` points from there
    into the wall (the direction the tab's profile measures its height in)."""

    lock: tuple[float, float]
    window: tuple[float, float]
    edge_v: float
    sign: float
    additive = False

    def _floor(self, plate: Plate, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """(depth into the floor, distance into the wall from its outer face) to the floor's (v, w)."""
        return [(self.edge_v + self.sign * z, plate.thickness - p) for p, z in points]

    def shape(self, plate: Plate) -> Part:
        c, u, reach = lid.CLEARANCE, lid.TAB_UNDERCUT, lid.TAB_REACH + lid.CLEARANCE
        drop = c * math.sqrt(2)
        groove = [
            (-1.0, u + 1 - drop),
            (u - drop + c, -c),
            (reach, -c),
            (reach, lid.TAB_TOP + c),
            (-1.0, lid.TAB_TOP + c),
        ]
        window = [(-1.0, -c), (reach, -c), (reach, lid.TAB_TOP + c), (-1.0, lid.TAB_TOP + c)]
        part = _prism_vw(self._floor(plate, groove), *sorted(self.lock))
        return part + _prism_vw(self._floor(plate, window), *sorted(self.window))

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        c = lid.CLEARANCE
        v0, v1 = sorted((self.edge_v - self.sign * c, self.edge_v + self.sign * (lid.TAB_TOP + c)))
        u0, u1 = min(*self.lock, *self.window), max(*self.lock, *self.window)
        t = plate.thickness
        return (u0, v0, u1, v1), (t - lid.TAB_REACH - c, t + 1)


@dataclass
class Tenon(Feature):
    """A straight tenon below the plate's bottom edge (v = 0), flush with its bed face."""

    u0: float
    u1: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        return _box(self.u0, -TENON_REACH, 0.0, self.u1, 0.5, TENON_THICKNESS)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return (self.u0, -TENON_REACH, self.u1, 0.5), (0.0, TENON_THICKNESS)


@dataclass
class SideTooth(Feature):
    """The rear latch's tooth standing out of the plate's end edge at u = `edge_u` toward `outward`, with
    a 45 degree lead-in on its underside: an in-plane profile, standing on the bed."""

    edge_u: float
    outward: float
    v0: float
    v1: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        t, o = REAR_TOOTH, self.outward
        points = [
            (self.edge_u - o * 0.5, self.v0),
            (self.edge_u, self.v0),
            (self.edge_u + o * t, self.v0 + t),
            (self.edge_u + o * t, self.v1),
            (self.edge_u - o * 0.5, self.v1),
        ]
        plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        return extrude(plane * Polygon(*points, align=None), amount=REAR_TOOTH_THICKNESS, dir=(0, 0, 1))

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        u0, u1 = sorted((self.edge_u - self.outward * 0.5, self.edge_u + self.outward * REAR_TOOTH))
        return (u0, self.v0, u1, self.v1), (0.0, REAR_TOOTH_THICKNESS)
