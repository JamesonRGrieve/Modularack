# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less mounting for racks with square (cage-nut) holes, printed upright.

Square-hole ears print standing up, upside down: the chassis's top edge is on the bed, so every layer
is a horizontal slice and the post's face (the plane the ear shears against) cuts across the layers.
A hook's pull and a peg's weight then reach the wall inside the layers they start in.

Printed that way, anything standing out behind the ear has a 45 degree top (a flat top would face the
bed) and a flat, upward-facing bottom: the face a peg bears on.

- `RackHook`: a rigid J-hook. Push it in through the hole, drop the chassis `HOOK_TRAVEL`, and its
  lip seats behind the flange. Taking it out needs that much free space above the chassis.
- `RackPeg`: a plain peg resting on the bottom edge of a hole: weight only.
- `SpringHook`: pushes straight in. A block on two upright blades moves sideways: a ramp on its lip
  rides over the hole's outboard edge, then the blades snap the lip behind the flange. The blades bend
  sideways, with their stress along the layers; the pull reaches them as tension. Push the outer blade
  inboard to release.

Everything is built in the ear's plate frame: u across the rack, v up, w rearward, the rear face at
w = thickness against the post. `band` is the hole column in u; `out` is +1 when outboard is +u.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Box, Face, Part, Pos, Vector, Wire, extrude

from .plate import Feature, Plate
from .standards import RackStandard

UPRIGHT = Vector(0, -1, 0)
"""print_up for upright parts: in an ear's or a wall's frame, v points up the rack, so the print is upside down."""

SQUARE_HOLE = 9.525
"""EIA-310 square mounting hole, 0.375 in."""
FLANGE_GAP = 3.0
"""Behind the ear to the lip: room for posts up to 12 gauge (2.66 mm) steel."""
HOOK_SIDE_CLEARANCE = 0.25
HOOK_VERTICAL_CLEARANCE = 0.6
HOOK_DROP = 2.0
"""How far a hook's lip reaches down behind the flange once seated."""
HOOK_PEG_HEIGHT = SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE - HOOK_DROP
HOOK_TRAVEL = HOOK_DROP + HOOK_VERTICAL_CLEARANCE / 2
"""How far a hook-eared chassis drops from inserted to seated, and must lift to come out."""
HOOK_HOLES_PER_UNIT = (0, 1, 2)
"""Every hole: the more hooks share the overturning pull, the less the top one carries."""
BACK_FACE = 1.0
"""A protrusion's 45 degree top stops this far above its bottom, leaving a short vertical back face."""

SPRING_HOLE_CLEARANCE = 0.7
"""Between the spring hook's outer face and the hole's edge: running clearance plus the spread in hole spacing."""
SPRING_LIP = 3.0
"""How far the lip reaches outboard of the block."""
SPRING_BODY_WIDTH = 4.6
SPRING_TRAVEL = SPRING_LIP + 0.5
"""How far the block moves inboard, over the hole's edge going in or pushed to release."""
SPRING_LIP_DEPTH = 5.0
BLADE_THICKNESS = 0.9
BLADE_LENGTH = 24.0
"""Long enough that the guided blades strain under 2 % at full travel."""
BLOCK_FRONT = 1.0
"""The block's front face, just inside the ear; the blades run forward from it."""
HOUSING_WALL = 2.0
SPRING_CLEARANCE = 0.5


def hook_width(rack: RackStandard) -> float:
    """Across the rack: the hole less the rack-to-rack spread in hole spacing and a running clearance."""
    return SQUARE_HOLE - rack.hole_spacing_tolerance - 2 * HOOK_SIDE_CLEARANCE


def blade_strain() -> float:
    """Peak strain in a guided (S-bending) blade at full travel."""
    return 3 * SPRING_TRAVEL * BLADE_THICKNESS / BLADE_LENGTH**2


def spring_housing_depth() -> float:
    """How far a spring hook's housing stands out in front of the ear."""
    return BLADE_LENGTH + HOUSING_WALL - BLOCK_FRONT


def _box(u0: float, u1: float, v0: float, v1: float, w0: float, w1: float) -> Part:
    (u0, u1), (v0, v1), (w0, w1) = sorted((u0, u1)), sorted((v0, v1)), sorted((w0, w1))
    return Pos((u0 + u1) / 2, (v0 + v1) / 2, (w0 + w1) / 2) * Box(u1 - u0, v1 - v0, w1 - w0)


def _prism(points: list[Vector], direction: Vector, length: float) -> Part:
    return extrude(Face(Wire.make_polygon(points, close=True)), amount=length, dir=direction)


def _column(band: tuple[float, float], profile: list[tuple[float, float]]) -> Part:
    """A (v, w) profile extruded across the hook column."""
    u0, u1 = band
    return _prism([Vector(u0, v, w) for v, w in profile], Vector(1, 0, 0), u1 - u0)


def _upright(plate: Plate) -> None:
    if plate.print_up is None or (plate.print_up - UPRIGHT).length > 1e-9:
        raise ValueError(f"{plate.name}: square-hole mounts are built for an upright (upside-down) print")


def _sloped(bottom: float, top: float, start: float) -> tuple[float, float]:
    """Where a 45 degree top falling rearward from (top, start) reaches BACK_FACE above `bottom`."""
    return bottom + BACK_FACE, start + (top - bottom - BACK_FACE)


@dataclass
class RackHook(Feature):
    """A rigid hook, seated: its peg rests on the hole's bottom edge, its lip behind the flange."""

    band: tuple[float, float]
    hole_v: float
    """Centre height of the rack hole, in the plate's v."""
    additive = True

    def shape(self, plate: Plate) -> Part:
        _upright(plate)
        t = plate.thickness
        bottom = self.hole_v - SQUARE_HOLE / 2
        top, lip, catch = bottom + HOOK_PEG_HEIGHT, bottom - HOOK_DROP, t + FLANGE_GAP
        start = t - 0.5
        back_v, back = _sloped(lip, top, start)
        if back < catch + 1.0:
            raise ValueError(f"{plate.name}: the hook's lip is too short")
        return _column(
            self.band, [(top, start), (back_v, back), (lip, back), (lip, catch), (bottom, catch), (bottom, start)]
        )


@dataclass
class RackPeg(Feature):
    """A plain peg resting on the bottom edge of a square hole: it carries weight, not pull."""

    band: tuple[float, float]
    hole_v: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        _upright(plate)
        t = plate.thickness
        bottom = self.hole_v - SQUARE_HOLE / 2
        top, start = bottom + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE, t - 0.5
        back_v, back = _sloped(bottom, top, start)
        return _column(self.band, [(top, start), (back_v, back), (bottom, back), (bottom, start)])


def hook_back(plate: Plate) -> float:
    """The w of a rigid hook's short vertical back face."""
    t = plate.thickness
    bottom = 0.0
    top, lip = bottom + HOOK_PEG_HEIGHT, bottom - HOOK_DROP
    return _sloped(lip, top, t - 0.5)[1]


def peg_back(plate: Plate) -> float:
    """The w of a peg's back face: how far it reaches behind the ear."""
    start = plate.thickness - 0.5
    return start + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE - BACK_FACE


@dataclass
class _SpringGeometry:
    band: tuple[float, float]
    hole_v: float
    out: float
    height: float
    """The ear's height: the block, blades and housing all stand on the bed at the chassis's top edge."""
    thickness: float

    @property
    def centre(self) -> float:
        return (self.band[0] + self.band[1]) / 2

    @property
    def outer(self) -> float:
        """The block's outer face at rest."""
        return self.centre + self.out * (SQUARE_HOLE / 2 - SPRING_HOLE_CLEARANCE)

    @property
    def inner(self) -> float:
        return self.outer - self.out * SPRING_BODY_WIDTH

    @property
    def bottom(self) -> float:
        return self.hole_v - SQUARE_HOLE / 2 + HOOK_VERTICAL_CLEARANCE / 2

    @property
    def catch(self) -> float:
        return self.thickness + FLANGE_GAP

    @property
    def back(self) -> float:
        return self.catch + SPRING_LIP_DEPTH

    @property
    def front_wall(self) -> tuple[float, float]:
        front = BLOCK_FRONT - BLADE_LENGTH
        return front - HOUSING_WALL, front

    @property
    def side_wall(self) -> tuple[float, float]:
        """The housing's inboard wall, clear of the block at full travel."""
        face = self.inner - self.out * (SPRING_TRAVEL + SPRING_CLEARANCE)
        return face - self.out * HOUSING_WALL, face

    def _profile_clip(self) -> Part:
        """Behind the ear the block must fit the hole and print: its top falls rearward at 45 degrees."""
        t = self.thickness
        top = self.hole_v + SQUARE_HOLE / 2 - HOOK_VERTICAL_CLEARANCE / 2
        far = self.back + 1
        profile = [
            (self.bottom - 1, self.front_wall[0] - 1),
            (self.height + 1, self.front_wall[0] - 1),
            (self.height + 1, t),
            (top, t),
            (top - (far - t), far),
            (self.bottom - 1, far),
        ]
        lo, hi = sorted((self.inner, self.outer + self.out * SPRING_LIP))
        return _column((lo - 1, hi + 1), profile)

    def block(self) -> Part:
        """The block from its front face to behind the flange, with the lip and its lead-in ramp."""
        v0, v1 = self.bottom, self.height
        body = _box(self.inner, self.outer, v0, v1, BLOCK_FRONT, self.back)
        tip = self.outer + self.out * SPRING_LIP
        # The lip's rear edge is a ramp: going in, it rides over the hole's outboard edge.
        ramp = [Vector(self.outer, v0, self.catch), Vector(tip, v0, self.catch), Vector(self.outer, v0, self.back)]
        lip = _prism(ramp, Vector(0, 1, 0), v1 - v0)
        common = (body + lip) & self._profile_clip()
        assert isinstance(common, Part)
        return common

    def blades(self, overlap: float) -> Part:
        """Two upright blades at the block's sides, running forward to the housing's front wall."""
        v0, v1 = self.bottom, self.height
        w0, w1 = self.front_wall[1] - overlap, BLOCK_FRONT + overlap
        step = self.out * BLADE_THICKNESS
        return _box(self.inner, self.inner + step, v0, v1, w0, w1) + _box(self.outer - step, self.outer, v0, v1, w0, w1)

    def housing(self) -> Part:
        """The front wall the blades stand on, tied back to the ear by the inboard side wall."""
        v0, v1 = self.bottom, self.height
        (f0, f1), (s0, s1) = self.front_wall, self.side_wall
        front = _box(s0, self.outer + self.out * SPRING_CLEARANCE, v0, v1, f0, f1)
        side = _box(s0, s1, v0, v1, f0, 0.5)
        return front + side

    def channel(self) -> Part:
        """The space the block moves in through the ear: open to the bed, roofed at 45 degrees below."""
        t = self.thickness
        lo = self.inner - self.out * (SPRING_TRAVEL + SPRING_CLEARANCE)
        hi = self.outer + self.out * SPRING_CLEARANCE
        v0 = self.bottom - SPRING_CLEARANCE
        box = _box(lo, hi, v0, self.height + 1, -0.01, t + 1)
        rise = (t + 1.01) / 2
        u0, u1 = sorted((lo, hi))
        roof = [Vector(u0, v0, -0.01), Vector(u0, v0, t + 1), Vector(u0, v0 - rise, (t + 1 - 0.01) / 2)]
        return box + _prism(roof, Vector(1, 0, 0), u1 - u0)

    def moving(self) -> Part:
        return self.block() + self.blades(0.1)

    def extent(self) -> tuple[tuple[float, float, float, float], tuple[float, float]]:
        tip = self.outer + self.out * (SPRING_LIP + SPRING_CLEARANCE)
        lo, hi = min(*self.side_wall, tip), max(*self.side_wall, tip)
        return (lo, self.bottom - SPRING_CLEARANCE - self.thickness, hi, self.height), (self.front_wall[0], self.back)


def _spring(feature: SpringHook | SpringHookCut, plate: Plate) -> _SpringGeometry:
    _upright(plate)
    return _SpringGeometry(feature.band, feature.hole_v, feature.out, plate.width, plate.thickness)


@dataclass
class SpringHook(Feature):
    """The spring hook's block, lip, blades and housing (added to the ear)."""

    band: tuple[float, float]
    hole_v: float
    out: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        geometry = _spring(self, plate)
        return geometry.housing() + geometry.moving()

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return _spring(self, plate).extent()


@dataclass
class SpringHookCut(Feature):
    """Frees the spring hook's block from the ear around it."""

    band: tuple[float, float]
    hole_v: float
    out: float

    def shape(self, plate: Plate) -> Part:
        geometry = _spring(self, plate)
        return geometry.channel() - geometry.moving()

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        return _spring(self, plate).extent()


def spring_blades(feature: SpringHook, plate: Plate) -> Part:
    """For tests: a spring hook's blades, oversized so removing them leaves no sliver."""
    return _spring(feature, plate).blades(0.3)


def spring_catch(feature: SpringHook, plate: Plate) -> tuple[float, float]:
    """The u range of a spring hook's catch face: from the block's outer face to the lip's tip."""
    geometry = _spring(feature, plate)
    return geometry.outer, geometry.outer + geometry.out * SPRING_LIP
