# SPDX-License-Identifier: AGPL-3.0-or-later
"""Side-web clamps: tie a chassis's side wall to the side web of a two-post channel post.

A two-post rack's uprights are channels: the drilled flange the ears bear on, and a side web running back
from its outer edge. Clamping each side wall to the web near its rear edge gives the chassis a second
support on the post, `PostChannel.web_depth` behind the ears, so the overturning moment is resisted over
that depth as well as the ears' height.

The clamp is a plate across the gap between the wall and the web, printed lying on its rear face. It hangs
on the wall by a tongue in a pocket (like the knee brace), and its outer end is a jaw around the web's
rear edge: an M5 screw through a captive nut in the jaw's outer leg presses a pad onto the web's outer
face, so the web is gripped between the jaw and the pad. Friction carries the chassis's weight into the
web, and the jaw's inner face bears on the web's inner face.

Post dimensions vary by make: `PostChannel` holds them, defaulting to a common 3 in (76 mm) channel of
2.5 mm steel. Measure your posts and pass your own.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Box, Location, Part, Plane, Pos, Vector

from .component import Component
from .layout import Panel
from .plate import edge_pocket, teardrop_prism

FRICTION = 0.3
"""PLA on painted steel, dry: a conservative coefficient."""
M5_PRELOAD = 1000.0
"""N: a hand-tight M5 thumbscrew into a nut, well under its proof load."""
M5_CLEARANCE = 5.5
M5_NUT_ACROSS_CORNERS = 9.24
M5_NUT_HEIGHT = 4.0
PLATE_THICKNESS = 8.0
"""Along the rack (the clamp's print height)."""
JAW = 6.0
"""The jaw's legs' thickness."""
JAW_REACH = 20.0
"""How far the jaw's legs run forward along the web's faces."""
LEG = 14.0
"""The outer leg's thickness across the rack: room for the M5 nut's slot."""
CLEARANCE = 0.4
TONGUE_DEPTH = 4.0
TONGUE_HEIGHT = 12.0
WALL_GAP = 0.5


@dataclass(frozen=True)
class PostChannel:
    """A two-post rack's channel upright, as it meets one side of the chassis."""

    flange_width: float = 20.0
    """From the rack opening's edge to the web's outer face."""
    web_depth: float = 76.2
    """The web's length front to back, from the post's front face (3 in)."""
    steel: float = 2.5


class WebClamp(Component):
    """One clamp, built in the rack frame (x rearward from the ears' front face, y across, z up)."""

    def __init__(
        self,
        name: str,
        side: float,
        wall_face_y: float,
        opening_y: float,
        post_face_x: float,
        floor_top: float,
        top: float,
        post: PostChannel,
    ) -> None:
        super().__init__(name)
        self.side, self.wall_face_y, self.opening_y = side, wall_face_y, opening_y
        self.post_face_x, self.floor_top, self.top, self.post = post_face_x, floor_top, top, post
        # Lying on its rear face: forward is up in the print.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))).inverse()

    @property
    def web(self) -> tuple[float, float]:
        """The web's inner and outer faces (rack y)."""
        outer = self.opening_y + self.side * self.post.flange_width
        return outer - self.side * self.post.steel, outer

    @property
    def rear_x(self) -> float:
        """The clamp plate's rear face: just behind the web's rear edge."""
        return self.post_face_x + self.post.web_depth + CLEARANCE + JAW

    @staticmethod
    def _y(a: float, b: float) -> tuple[float, float]:
        return min(a, b), max(a, b)

    def solids(self) -> dict[str, Part]:
        s, (web_in, web_out) = self, self.web
        x1 = s.rear_x
        x0, front = x1 - PLATE_THICKNESS, x1 - PLATE_THICKNESS - JAW_REACH
        z0, z1 = s.floor_top + 0.5, s.top
        start = s.wall_face_y + s.side * WALL_GAP
        inner_leg = (web_in - s.side * (CLEARANCE + JAW), web_in - s.side * CLEARANCE)
        outer_leg = (web_out + s.side * CLEARANCE, web_out + s.side * (CLEARANCE + LEG))
        # The plate across the gap behind the web, and the two legs forward along its faces.
        part = _box(x0, x1, *s._y(start, outer_leg[1]), z0, z1)
        part += _box(front, x1, *s._y(*inner_leg), z0, z1)
        part += _box(front, x1, *s._y(*outer_leg), z0, z1)
        # The slot the web's rear edge sits in.
        part -= _box(
            front - 1, x1 - JAW, *s._y(web_in - s.side * CLEARANCE, web_out + s.side * CLEARANCE), z0 - 1, z1 + 1
        )
        # The tongue into the wall's pocket.
        tongue = s._y(s.wall_face_y - s.side * (TONGUE_DEPTH - 0.2), start + s.side * 0.5)
        part += _box(x0, x1, *tongue, z0, s.floor_top + TONGUE_HEIGHT - 0.2)
        # The screw runs across the outer leg toward the web; its nut drops into a slot from the leg's front
        # end (the print's top), and the screw's tip presses the web against the inner leg.
        mid_x, mid_z = front + JAW_REACH / 2, (z0 + z1) / 2
        bore = Vector(mid_x, outer_leg[1] + s.side, mid_z)
        part -= teardrop_prism(bore, Vector(0, -s.side, 0), M5_CLEARANCE / 2, LEG + 2, Vector(-1, 0, 0))
        nut_y = (outer_leg[0] + outer_leg[1]) / 2
        across = M5_NUT_ACROSS_CORNERS + CLEARANCE
        part -= _box(
            front - 1,
            mid_x + across / 2,
            *s._y(nut_y - (M5_NUT_HEIGHT + CLEARANCE) / 2, nut_y + (M5_NUT_HEIGHT + CLEARANCE) / 2),
            mid_z - across / 2,
            mid_z + across / 2,
        )
        return {"part": part}

    def capacity(self) -> float:
        """N of vertical load the clamp's friction carries, on the pad and the jaw's inner face."""
        return 2 * FRICTION * M5_PRELOAD


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def clamp_pocket(wall: Panel, x: float, floor_top: float) -> None:
    """The pocket the clamp's tongue hangs in, open at the wall's bottom edge."""
    local = wall.frame.to_local(Vector(x, 0, floor_top))
    found = wall.segment_at(local.X, TONGUE_HEIGHT / 2)
    if found is None:
        raise ValueError(f"{wall.name}: the web clamp's pocket lands on a seam")
    plate, lu, _ = found
    plate.add(edge_pocket(plate, lu, PLATE_THICKNESS + 2 * CLEARANCE, TONGUE_HEIGHT, TONGUE_DEPTH))


def clamp_reaction(load: float, chassis_depth: float, clamp: WebClamp) -> float:
    """N the clamp must hold up: with the ears and the clamp as the two supports and the side's share
    of the weight at mid-depth, the clamp carries it on the shorter lever (the ears then hold the front down)."""
    lever = clamp.rear_x - PLATE_THICKNESS / 2 - clamp.post_face_x
    return load * (chassis_depth / 2 - clamp.post_face_x) / lever
