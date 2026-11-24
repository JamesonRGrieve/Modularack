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
from .plate import Feature, Plate, RectCut

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


@dataclass
class RailTab(Feature):
    """A drawer's tab on a side plate's bottom edge (v = 0). Its near face is flat on the bed and its far
    face widens at 45 degrees toward the tip (a slope that climbs with the layers, so it prints): the
    dovetail's hold is on the side away from the bed face. Neighbouring modules' plates stand back to back
    on their bed faces, so their tabs share one groove, each held by its own far lip."""

    u0: float
    u1: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        top, u, r = lid.TAB_TOP, lid.TAB_UNDERCUT, lid.TAB_REACH
        profile = [(-0.5, 0.0), (r, 0.0), (r, top + u), (u, top + u), (-0.5, top - 0.5)]
        points = [(-p, w) for p, w in profile]
        return _prism_vw(points, self.u0, self.u1)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return (self.u0, -lid.TAB_REACH, self.u1, 0.5), (0.0, lid.TAB_TOP + lid.TAB_UNDERCUT)


@dataclass
class RailGroove(Feature):
    """The rail a module's `RailTab`s slide in, cut into the floor's (or a shelf's) top face from u
    `lock[0]` to `lock[1]`. `edge_v` is the side plate's bed face in this plate's v; `sign` points from it
    into the plate the tabs stand on."""

    lock: tuple[float, float]
    edge_v: float
    sign: float
    additive = False

    def shape(self, plate: Plate) -> Part:
        c, u, top, reach = lid.CLEARANCE, lid.TAB_UNDERCUT, lid.TAB_TOP, lid.TAB_REACH + lid.CLEARANCE
        drop = c * math.sqrt(2)
        groove = [(-1.0, -c), (reach, -c), (reach, top + u + c), (u + c - drop, top + u + c), (-1.0, top - 1 + drop)]
        points = [(self.edge_v + self.sign * z, plate.thickness - p) for p, z in groove]
        return _prism_vw(points, *sorted(self.lock))

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        c = lid.CLEARANCE
        v0, v1 = sorted((self.edge_v - self.sign * c, self.edge_v + self.sign * (lid.TAB_TOP + lid.TAB_UNDERCUT + c)))
        t = plate.thickness
        return (min(self.lock), v0, max(self.lock), v1), (t - lid.TAB_REACH - c, t + 1)


SHELF_TENON_LENGTH = 10.0
SHELF_TENON_THICKNESS = 5.0


@dataclass
class ShelfTenon(Feature):
    """A short tenon up from a side plate's top edge (v = `edge_v`) into a slot through its shelf: it stops
    `reach` above the edge, just under the rail groove cut in the shelf's top, so a drawer above slides over
    it. Flush with the bed face, so it prints."""

    u0: float
    u1: float
    edge_v: float
    reach: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        return _box(self.u0, self.edge_v - 0.5, 0.0, self.u1, self.edge_v + self.reach, SHELF_TENON_THICKNESS)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return (self.u0, self.edge_v - 0.5, self.u1, self.edge_v + self.reach), (0.0, SHELF_TENON_THICKNESS)


@dataclass
class ShelfSlot(RectCut):
    """The slot through a shelf a `ShelfTenon` comes up into. A rail groove above may run over it."""


DETENT_DROP = 1.0
"""How far the detent's nose stands below a tab's tip: its drop into the notch."""
DETENT_LENGTH = 8.0
DETENT_ARM = 45.0
"""The detent arm's free length, from the module's front edge."""
DETENT_ARM_HEIGHT = 4.0
DETENT_RELIEF = 2.0
DETENT_FROM_FRONT = 14.0
"""The nose's front face behind the side plate's front edge (clear of where the floor starts)."""


DETENT_STRAIN = 0.015
"""The most a detent arm may strain; its drop shrinks on a short arm to stay under it."""
DETENT_MIN_DROP = lid.CLEARANCE + 0.3
"""A shallower notch wouldn't hold."""


def detent_strain(lever: float, drop: float = DETENT_DROP) -> float:
    """A detent arm's peak strain while its nose rides the groove floor: 3 b d / (2 L^2), with the lever
    from the arm's root to the nose."""
    return 3 * DETENT_ARM_HEIGHT * (drop - lid.CLEARANCE) / (2 * lever**2)


def detent_drop(lever: float) -> float:
    """The deepest drop (up to DETENT_DROP) an arm of this lever takes within DETENT_STRAIN."""
    return min(DETENT_DROP, lid.CLEARANCE + DETENT_STRAIN * 2 * lever**2 / (3 * DETENT_ARM_HEIGHT))


@dataclass
class DetentBump(Feature):
    """A rail tab on the side plate's bottom edge (v = 0) whose tip carries a nose DETENT_DROP deeper: square at
    its front (u0, holding the module in), ramped at 45 degrees at its leading rear end. All of it stands
    on the bed: the tab's profile, then an in-plane nose on the tip."""

    u0: float
    u1: float
    drop: float = DETENT_DROP
    front_low: bool = True
    """Whether the square (holding) face is at u0: the module's front end, when the plate's u runs back."""
    additive = True

    def shape(self, plate: Plate) -> Part:
        tab = RailTab(self.u0, self.u1).shape(plate)
        r, d = lid.TAB_REACH, self.drop
        if self.front_low:
            nose = [(self.u0, -r + 0.5), (self.u0, -r - d), (self.u1 - d, -r - d), (self.u1, -r), (self.u1, -r + 0.5)]
        else:
            nose = [(self.u0, -r + 0.5), (self.u0, -r), (self.u0 + d, -r - d), (self.u1, -r - d), (self.u1, -r + 0.5)]
        plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        return tab + extrude(plane * Polygon(*nose, align=None), amount=lid.TAB_TOP, dir=(0, 0, 1))

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return (self.u0, -lid.TAB_REACH - self.drop, self.u1, 0.5), (0.0, lid.TAB_TOP + lid.TAB_UNDERCUT)
