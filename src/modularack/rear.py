# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rear supports: in a four-post rack, carry the back of the chassis on the rear posts.

With its back held up, a chassis is no longer a cantilever from its front ears: the overturning moment
that limits every ear style goes away, leaving each end a share of the weight.

Each side has two arms, both flat plates beside the side wall, printed lying on their outer faces so
their bending runs along the layers:

- the front arm hangs on the wall by two tongues in pockets in the wall's outer face (open at its bottom
  edge, like a knee brace's socket), bearing up on the pockets' top faces;
- the rear arm overlaps it outboard and runs back to the rear post, where pegs in every hole of its
  height rest on the holes' bottom edges and its end face bears on the post;
- a printed diamond pin through both locks the length. The front arm's holes are `PIN_PITCH_FRONT`
  apart and the rear arm's `PIN_PITCH_REAR`, a vernier: some pair lines up every millimetre.

`rack_depth` is the front posts' front face to the rear posts' front face; the rear posts' mounting face
is taken to face the chassis. Both arms fit from the rear or side once the chassis is in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Box, Location, Part, Plane, Pos, RegularPolygon, Vector, extrude

from .component import Component
from .hooks import HOOK_VERTICAL_CLEARANCE, SQUARE_HOLE
from .layout import Panel
from .plate import edge_pocket
from .standards import PANEL_HEIGHT_DEDUCTION, RACK_UNIT, U_HOLE_OFFSETS

ARM_THICKNESS = 6.0
ARM_CLEARANCE = 0.3
WALL_GAP = 0.5
"""Between the wall's outer face and the front arm."""
TONGUE_DEPTH = 4.0
TONGUE_LENGTH = 16.0
TONGUE_HEIGHT = 12.0
TONGUE_SPACING = 80.0
"""Between the front arm's two tongues."""
TONGUE_CLEARANCE = 0.2
PIN_SIZE = 4.0
"""Across the diamond pin's flats."""
PIN_CLEARANCE = 0.2
PIN_PITCH_FRONT = 10.0
PIN_PITCH_REAR = 9.0
"""One millimetre less than the front arm's: a vernier, so some pair of holes lines up every millimetre."""
OVERLAP = 90.0
"""The arms' shortest overlap: room for a full vernier cycle of holes."""
PEG_WIDTH = 6.0
PEG_THROUGH = 2.66 + 1.0
"""Through the thickest (12 gauge) flange and a little beyond."""
REAR_BLOCK = 12.0
"""The rear arm's end block, which carries the pegs, along the rack."""
MAX_ARM = 235.0
"""The longest arm the bed takes, lying flat."""
FRONT_POST_CLEARANCE = 100.0
"""The arms stay this far behind the ears' front face, clear of the front posts' depth."""
TOP_MARGIN = 2.0
"""The arms stop this far under the chassis's top."""


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def _diamond(x: float, y0: float, y1: float, z: float, size: float) -> Part:
    """A square set on its corner (a diamond) running along y: as a hole it prints with no ceiling."""
    lo, hi = sorted((y0, y1))
    shape = Plane(origin=(x, lo, z), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * RegularPolygon(size / math.sqrt(2), 4)
    return extrude(shape, amount=hi - lo)


def _lying(side: float) -> Location:
    """Print frame for an arm lying on its outer face: inboard is up."""
    return Location(Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -side, 0))).inverse()


@dataclass(frozen=True)
class RearLayout:
    """Where one side's arms go, in the rack frame (x rearward from the ears' front face, y across, z up)."""

    side: float
    """+1 on the left, -1 on the right."""
    wall_face_y: float
    hole_y: float
    floor_top: float
    top: float
    tongues: tuple[float, float]
    """The rack x of the front arm's two tongues."""
    post_face: tuple[float, float]
    """The rear posts' front face at the shortest and longest rack depth; the parts are placed at the shortest."""

    def y(self, inner: float, outer: float) -> tuple[float, float]:
        return self.wall_face_y + self.side * inner, self.wall_face_y + self.side * outer

    @property
    def front_y(self) -> tuple[float, float]:
        return self.y(WALL_GAP, WALL_GAP + ARM_THICKNESS)

    @property
    def rear_y(self) -> tuple[float, float]:
        start = WALL_GAP + ARM_THICKNESS + ARM_CLEARANCE
        return self.y(start, start + ARM_THICKNESS)

    @property
    def span(self) -> float:
        return self.post_face[1] - self.post_face[0]

    @property
    def rear_length(self) -> float:
        """Long enough to overlap the front arm by OVERLAP at the longest depth."""
        return REAR_BLOCK + OVERLAP + self.span

    @property
    def front_end(self) -> float:
        """The front arm's rear end: overlapping the rear arm by OVERLAP at the longest depth."""
        return self.post_face[1] - REAR_BLOCK - (self.rear_length - REAR_BLOCK - OVERLAP)

    @property
    def front_start(self) -> float:
        return min(self.tongues) - TONGUE_LENGTH / 2

    def front_holes(self) -> list[float]:
        return [
            self.front_end - PIN_PITCH_FRONT / 2 - k * PIN_PITCH_FRONT for k in range(int(OVERLAP // PIN_PITCH_FRONT))
        ]

    def rear_holes(self) -> list[float]:
        """At the shortest depth the rear arm's first hole lines up with the front arm's first (the pin's
        place); the rest run forward along the whole arm, so a deeper rack still finds a pair that lines up."""
        first = self.front_holes()[0]
        start = self.post_face[0] - self.rear_length
        count = int((first - start - PIN_SIZE) // PIN_PITCH_REAR) + 1
        return [first - k * PIN_PITCH_REAR for k in range(count)]

    @property
    def mid(self) -> float:
        return (self.floor_top + self.top) / 2

    def hole_heights(self) -> list[float]:
        """Every rack hole within the arms' height."""
        heights = []
        unit = 0
        while unit * RACK_UNIT < self.top:
            for offset in U_HOLE_OFFSETS:
                z = unit * RACK_UNIT + offset - PANEL_HEIGHT_DEDUCTION / 2
                if self.floor_top + 0.5 <= z - SQUARE_HOLE / 2 and z + SQUARE_HOLE / 2 <= self.top:
                    heights.append(z)
            unit += 1
        return heights

    def check(self) -> None:
        """Both arms must fit the bed, and the rear arm must clear the front arm's tongues."""
        front = self.front_end - self.front_start
        if front > MAX_ARM or self.rear_length > MAX_ARM:
            raise ValueError(
                f"Rear support arms of {front:.0f} and {self.rear_length:.0f} mm don't fit the bed "
                f"(max {MAX_ARM:.0f}): narrow the rack-depth range"
            )
        if self.post_face[0] - self.rear_length < FRONT_POST_CLEARANCE:
            raise ValueError("The rear support's arm would reach forward into the front posts")
        if self.post_face[0] - REAR_BLOCK < self.front_start + 2 * PIN_PITCH_FRONT:
            raise ValueError("The rack's rear posts are too close to the chassis for a rear support")
        if not self.hole_heights():
            raise ValueError("A rear support needs at least one rack hole within the chassis's height")


class RearArm(Component):
    """One of a side's two arms, built in the rack frame at the rack's shortest depth."""

    def __init__(self, name: str, layout: RearLayout, rear: bool) -> None:
        super().__init__(name)
        self.layout, self.rear = layout, rear
        self.print_location = _lying(layout.side)

    def solids(self) -> dict[str, Part]:
        return {"part": self._rear() if self.rear else self._front()}

    def _front(self) -> Part:
        g = self.layout
        y0, y1 = g.front_y
        arm = _box(g.front_start, g.front_end, y0, y1, g.floor_top + 0.5, g.top)
        top = g.floor_top + TONGUE_HEIGHT - TONGUE_CLEARANCE
        for x in g.tongues:
            # Into the wall's pocket, bearing on its top face.
            ty = g.y(-(TONGUE_DEPTH - TONGUE_CLEARANCE), WALL_GAP + 0.5)
            arm += _box(
                x - TONGUE_LENGTH / 2 + TONGUE_CLEARANCE,
                x + TONGUE_LENGTH / 2 - TONGUE_CLEARANCE,
                *ty,
                g.floor_top + 0.5,
                top,
            )
        for x in g.front_holes():
            arm -= _diamond(x, min(y0, y1) - 1, max(y0, y1) + 1, g.mid, PIN_SIZE + PIN_CLEARANCE)
        return arm

    def _rear(self) -> Part:
        g = self.layout
        y0, y1 = g.rear_y
        face = g.post_face[0]
        arm = _box(face - g.rear_length, face, y0, y1, g.floor_top + 0.5, g.top)
        # The end block reaches inboard over the hole column; the pegs stand out of it into the post and
        # run out to the arm's outer face, so they print from the bed.
        inner = g.y(WALL_GAP, 0.0)[0]
        arm += _box(face - REAR_BLOCK, face, inner, y1, g.floor_top + 0.5, g.top)
        for z in g.hole_heights():
            bottom = z - SQUARE_HOLE / 2
            peg_y = (g.hole_y - g.side * PEG_WIDTH / 2, y1)
            arm += _box(face - 0.5, face + PEG_THROUGH, *peg_y, bottom, bottom + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE)
        for x in g.rear_holes():
            arm -= _diamond(x, min(y0, y1) - 1, max(y0, y1) + 1, g.mid, PIN_SIZE + PIN_CLEARANCE)
        return arm


class RearPin(Component):
    """The diamond pin that locks a side's arms together: printed lying on a flat face, so the plane it
    shears in cuts across its layers."""

    def __init__(self, name: str, layout: RearLayout) -> None:
        super().__init__(name)
        self.layout = layout
        # Its axis (rack y) along the bed, a flat face (normal (1, 0, 1) in the rack) down.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 1))).inverse()

    def solids(self) -> dict[str, Part]:
        g = self.layout
        (f0, _), (_, r1) = g.front_y, g.rear_y
        return {"part": _diamond(g.front_holes()[0], f0, r1 + g.side * 1.0, g.mid, PIN_SIZE)}


def pockets_for(wall: Panel, layout: RearLayout) -> None:
    """Cut the front arm's two pockets into the wall's outer face, open at its bottom edge."""
    for x in layout.tongues:
        local = wall.frame.to_local(Vector(x, 0, layout.floor_top))
        found = wall.segment_at(local.X, TONGUE_HEIGHT / 2)
        if found is None:
            raise ValueError(f"{wall.name}: a rear support pocket lands on a seam")
        plate, lu, _ = found
        plate.add(edge_pocket(plate, lu, TONGUE_LENGTH, TONGUE_HEIGHT, TONGUE_DEPTH))
