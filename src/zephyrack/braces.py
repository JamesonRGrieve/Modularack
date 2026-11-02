# SPDX-License-Identifier: AGPL-3.0-or-later
"""Knee braces: struts that prop a chassis's side wall from a square hole lower down the post.

Hung from two front posts a chassis is a cantilever, and its whole overturning moment lands on the ears.
A knee brace props each side wall a good way back, from a square hole one or two units below the chassis:
FEA of a 19 in 1U corner put the hook and snap styles at about x6 and x4.7 (from x2.1 and x1.0) with the
strut two units down (`fea.Brace.STRUT`).

The strut fits from the side, so it suits open-frame racks or racks with a side panel off, with the
chassis already in place:

- its front end sits behind the post's flange; a peg goes forward through the anchor hole and rests on
  the hole's bottom edge, and the strut's end face bears on the back of the flange;
- its rear end has a tongue that slides sideways into a pocket in the wall's outer face, open at the
  wall's bottom edge, and bears up and back on the pocket's top and rear faces.

Nothing stands outside the chassis's width, so the chassis still slides in past the posts. Every unit
the strut spans (the anchor's and any between) must have its hole column free: an empty or blanked U.

The strut prints lying on its outer face, so its compression runs along the layers.
"""

from __future__ import annotations

from build123d import Box, Face, Location, Part, Plane, Pos, Vector, Wire, extrude

from .component import Component
from .hooks import HOOK_VERTICAL_CLEARANCE, SQUARE_HOLE
from .layout import Panel
from .plate import edge_pocket
from .standards import PANEL_HEIGHT_DEDUCTION, RACK_UNIT, U_HOLE_OFFSETS

STRUT_WIDTH = 12.0
"""Across the rack."""
STRUT_DEPTH = 12.0
"""Across the strut, in its own plane."""
STRUT_SIDE_CLEARANCE = 0.5
"""Between the wall's outer face and the strut."""
FLANGE_BACK = 2.66 + 0.3
"""Behind the post's front face to the strut's end: the thickest (12 gauge) flange, plus clearance."""
PEG_WIDTH = 6.0
PEG_PROUD = 1.0
"""How far the peg stands out in front of the post."""
SOCKET_LENGTH = 16.0
SOCKET_HEIGHT = 12.0
SOCKET_DEPTH = 4.0
"""Into the wall from its outer face."""
SOCKET_CLEARANCE = 0.2
SOCKET_SLIDE = 1.0
"""Spare length in front of the tongue: a thinner flange lets the strut sit further forward."""
KNEE_DEPTH_FRACTION = 0.8
"""The socket's place along the wall's first segment, as a fraction of its length."""


def anchor_height(units_below: int) -> float:
    """Centre height of the anchor hole (the top hole of the U `units_below` under the chassis), in chassis z."""
    return -units_below * RACK_UNIT + U_HOLE_OFFSETS[-1] - PANEL_HEIGHT_DEDUCTION / 2


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


class KneeBrace(Component):
    """One strut, built in the rack frame for the left side (`side` = +1) or the right (-1)."""

    def __init__(
        self,
        name: str,
        side: float,
        wall_face_y: float,
        hole_y: float,
        post_face_x: float,
        socket_x: float,
        floor_top: float,
        units_below: int,
    ) -> None:
        super().__init__(name)
        self.side, self.wall_face_y, self.hole_y = side, wall_face_y, hole_y
        self.post_face_x, self.socket_x, self.floor_top = post_face_x, socket_x, floor_top
        self.units_below = units_below
        # Printed lying on its outer face: rack -y (left) or +y (right) is up in the print.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -side, 0))).inverse()

    def _y(self, inner: float, outer: float) -> tuple[float, float]:
        """A y range given as distances outboard of the wall's outer face."""
        return self.wall_face_y + self.side * inner, self.wall_face_y + self.side * outer

    def solids(self) -> dict[str, Part]:
        s = self
        y0, y1 = s._y(STRUT_SIDE_CLEARANCE, STRUT_SIDE_CLEARANCE + STRUT_WIDTH)
        if not (min(y0, y1) <= s.hole_y - PEG_WIDTH / 2 and s.hole_y + PEG_WIDTH / 2 <= max(y0, y1)):
            raise ValueError(f"{s.name}: the strut doesn't reach the hole column")
        end_x = s.post_face_x + FLANGE_BACK
        hole_z = anchor_height(s.units_below)
        hole_bottom = hole_z - SQUARE_HOLE / 2
        # The block that carries the tongue, at the wall's bottom edge.
        block_x0 = s.socket_x - SOCKET_LENGTH / 2
        block_x1 = s.socket_x + SOCKET_LENGTH / 2 - SOCKET_CLEARANCE
        block_z1 = s.floor_top + SOCKET_HEIGHT - SOCKET_CLEARANCE
        block = _box(block_x0, block_x1, y0, y1, s.floor_top + 0.5, block_z1)
        # The bar, from its flat end against the flange up and back to the block.
        # Keep the front end no taller than the hole: just above it, the chassis's lowest mounts reach back
        # behind the flange.
        top_front = hole_bottom + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE
        bar_profile = [
            Vector(end_x, y0, hole_bottom - 0.5),
            Vector(end_x, y0, top_front),
            Vector(block_x0, y0, block_z1),
            Vector(block_x1, y0, block_z1),
            Vector(block_x1, y0, s.floor_top + 0.5),
            Vector(block_x1 - STRUT_DEPTH, y0, s.floor_top + 0.5),
        ]
        bar = extrude(Face(Wire.make_polygon(bar_profile, close=True)), amount=abs(y1 - y0), dir=(0, 1, 0))
        if y1 < y0:
            bar = Pos(0, y1 - y0, 0) * bar
        # The peg runs out to the strut's outer face, so it prints from the bed.
        outer = max(y0, y1) if s.side > 0 else min(y0, y1)
        peg = _box(
            s.post_face_x - PEG_PROUD,
            end_x + 0.5,
            s.hole_y - s.side * PEG_WIDTH / 2,
            outer,
            hole_bottom,
            hole_bottom + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE,
        )
        # The tongue reaches into the wall's pocket, bearing on its top and rear faces.
        tongue_y = s._y(-(SOCKET_DEPTH - SOCKET_CLEARANCE), STRUT_SIDE_CLEARANCE + 0.5)
        tongue = _box(block_x0 + SOCKET_SLIDE, block_x1, *tongue_y, s.floor_top + 0.5, block_z1)
        return {"part": bar + block + peg + tongue}


def socket_for(wall: Panel, socket_x: float, floor_top: float) -> None:
    """Cut the strut's pocket into the wall segment at `socket_x` (rack x), open at the wall's bottom edge."""
    corners = [
        wall.frame.to_local(Vector(x, 0, z))
        for x in (socket_x - SOCKET_LENGTH / 2, socket_x + SOCKET_LENGTH / 2)
        for z in (floor_top, floor_top + SOCKET_HEIGHT)
    ]
    us = [c.X for c in corners]
    found = wall.segment_at((min(us) + max(us)) / 2, SOCKET_HEIGHT / 2)
    if found is None:
        raise ValueError(f"{wall.name}: the knee brace's socket lands on a seam")
    plate, lu, _ = found
    plate.add(edge_pocket(plate, lu, max(us) - min(us), SOCKET_HEIGHT, SOCKET_DEPTH))
