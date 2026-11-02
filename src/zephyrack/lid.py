# SPDX-License-Identifier: AGPL-3.0-or-later
"""A tool-less cover: interrupted dovetails along its edges and one printed spring latch.

The cover sits between the full-height side walls. Each of its long edges carries short dovetail tabs;
each side wall has, for every tab, a window open at its top edge and, just forward of it, a dovetail
groove. The cover drops in with its tabs in the windows, then slides forward `SLIDE` until its front
edge meets the ears' back face: the tabs run into the grooves, which hold the cover down and tie the
walls' tops together.

A cantilever arm at the cover's rear left corner, cut free by a slot through the cover, carries a tooth.
The tooth rides on the wall's inner face as the cover slides home, then springs into a pocket; its square
faces stop the cover sliding back. To open: press the arm's end inward, slide the cover back and lift.

Everything prints without supports:

- the cover prints inner face down, so the tabs' flanks rise at 45 degrees from a flat on the bed, and
  the tooth's lead-in chamfer rises from the bed the same way;
- the wall's windows, grooves and pocket are cut into its top face as it lies (inner face up); on a
  one-piece corner, printed standing on its top edge, the windows open onto the bed and the grooves' and
  pocket's ceilings slope at 45 degrees.

The arm bends in the cover's plane, so its strain runs along the layers (`latch_strain`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Part, Plane, Polygon, extrude

from .plate import Feature, Plate

TAB_LENGTH = 12.0
TAB_REACH = 3.0
"""How far a tab stands out from the cover's edge into the wall."""
TAB_FLAT = 1.0
"""The tab's tip rests on the bed this wide, so its first layers aren't a knife edge."""
TAB_UNDERCUT = TAB_REACH - TAB_FLAT
"""How much the 45 degree flank widens the tab toward its tip: the dovetail's hold."""
TAB_TOP = 5.0
"""The tab's top, above the cover's inner face; above it the wall keeps a lip of the rest."""
CLEARANCE = 0.25
SLIDE = TAB_LENGTH + 2 * CLEARANCE
"""How far the cover slides forward from its drop position to lock."""
STATION_PITCH = 60.0
STATION_MARGIN = 8.0
LATCH_ARM = 45.0
"""The arm's free length, from its root to the cover's rear edge."""
LATCH_WIDTH = 3.0
LATCH_RELIEF = 2.5
"""The slot that frees the arm: wider than the tooth's travel."""
TOOTH = 1.5
"""How far the tooth stands out into the wall's pocket."""
TOOTH_LENGTH = 6.0
TOOTH_HEIGHT = 4.0
TOOTH_FROM_END = 16.0
"""The tooth's rear face, ahead of the cover's rear edge: clear of the rear corner's joint."""
PLA_STRAIN_LIMIT = 0.02


def latch_strain() -> float:
    """Peak bending strain in the arm as the tooth rides on the wall: 3 b d / (2 L^2) for a cantilever
    of width b, tip deflection d and length L (the tooth sits near the free end, so L is the arm's)."""
    deflection = TOOTH + CLEARANCE
    lever = LATCH_ARM - TOOTH_FROM_END - TOOTH_LENGTH / 2
    return 3 * LATCH_WIDTH * deflection / (2 * lever**2)


def _section(points: list[tuple[float, float]], u0: float, u1: float) -> Part:
    """A polygon in the plate's (v, w) plane, extruded along u from u0 to u1."""
    plane = Plane(origin=(u0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    # Give the direction: a mirrored polygon's normal points the other way.
    return extrude(plane * Polygon(*points, align=None), amount=u1 - u0, dir=(1, 0, 0))


def _edge_points(points: list[tuple[float, float]], edge_v: float, outward: float) -> list[tuple[float, float]]:
    """(reach past the edge, w) points to (v, w) on the plate."""
    return [(edge_v + outward * p, w) for p, w in points]


@dataclass
class CoverTab(Feature):
    """A dovetail tab on the cover's edge at v = `edge_v`, standing out toward `outward` (+1 or -1)."""

    u0: float
    u1: float
    edge_v: float
    outward: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        u = TAB_UNDERCUT
        profile = [(-0.5, u + 0.5), (u, 0.0), (TAB_REACH, 0.0), (TAB_REACH, TAB_TOP), (-0.5, TAB_TOP)]
        return _section(_edge_points(profile, self.edge_v, self.outward), self.u0, self.u1)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        v0, v1 = sorted((self.edge_v - self.outward * 0.5, self.edge_v + self.outward * TAB_REACH))
        return (self.u0, v0, self.u1, v1), (0.0, TAB_TOP)


@dataclass
class LatchTooth(Feature):
    """The tooth on the latch arm's outer edge, with a 45 degree lead-in rising from the bed."""

    u0: float
    u1: float
    edge_v: float
    outward: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        profile = [(-0.5, 0.0), (0.0, 0.0), (TOOTH, TOOTH), (TOOTH, TOOTH_HEIGHT), (-0.5, TOOTH_HEIGHT)]
        return _section(_edge_points(profile, self.edge_v, self.outward), self.u0, self.u1)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        v0, v1 = sorted((self.edge_v - self.outward * 0.5, self.edge_v + self.outward * TOOTH))
        return (self.u0, v0, self.u1, v1), (0.0, TOOTH_HEIGHT)


@dataclass
class TabSocket(Feature):
    """In a side wall's inner face (w = thickness): a tab's groove from u `lock[0]` to `lock[1]` and its
    window, open at the wall's top edge, from `window[0]` to `window[1]`. `floor_v` is the cover's inner
    face in the wall's v."""

    lock: tuple[float, float]
    window: tuple[float, float]
    floor_v: float
    additive = False

    def _wall(self, plate: Plate, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """(depth into the wall, height above the cover's inner face) to the wall's (v, w)."""
        return [(self.floor_v + z, plate.thickness - p) for p, z in points]

    def shape(self, plate: Plate) -> Part:
        c, u, reach = CLEARANCE, TAB_UNDERCUT, TAB_REACH + CLEARANCE
        drop = c * math.sqrt(2)
        # The lower sides carry on down at 45 degrees rather than turning flat: on a corner printed
        # upright, standing on the wall's top edge, they are ceilings.
        groove = [(-1.0, u + 1 - drop), (reach, u - reach - drop), (reach, TAB_TOP + c), (-1.0, TAB_TOP + c)]
        top = plate.width + 1 - self.floor_v
        window = [(-1.0, -c), (reach, -c - reach - 1), (reach, top), (-1.0, top)]
        part = _section(self._wall(plate, groove), *sorted(self.lock))
        return part + _section(self._wall(plate, window), *sorted(self.window))

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        u0 = min(*self.lock, *self.window)
        u1 = max(*self.lock, *self.window)
        t = plate.thickness
        low = self.floor_v - 2 * CLEARANCE - TAB_REACH - 1
        return (u0, low, u1, plate.width + 1), (t - TAB_REACH - CLEARANCE, t + 1)


@dataclass
class LatchPocket(Feature):
    """The pocket in a side wall's inner face the latch tooth springs into; its lower side slopes at 45
    degrees like the tooth's lead-in."""

    u0: float
    u1: float
    floor_v: float
    additive = False

    def shape(self, plate: Plate) -> Part:
        c = CLEARANCE
        points = [(-1.0, -1.0 - c), (TOOTH + c, TOOTH), (TOOTH + c, TOOTH_HEIGHT + c), (-1.0, TOOTH_HEIGHT + c)]
        wall = [(self.floor_v + z, plate.thickness - p) for p, z in points]
        return _section(wall, self.u0, self.u1)

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        t = plate.thickness
        return (self.u0, self.floor_v - 1 - CLEARANCE, self.u1, self.floor_v + TOOTH_HEIGHT + CLEARANCE), (
            t - TOOTH - CLEARANCE,
            t + 1,
        )
