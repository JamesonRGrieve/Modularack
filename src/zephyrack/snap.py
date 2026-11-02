# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less joint parts: printed snap pins, in-plane dovetail seams and captive-nut T-slots.

Snap pin (corners and laps). A flat pin, printed lying down, with a wedge head and two prongs
that end in barbs. It passes through plate A (a slot with a 45 degree head pocket) and either:

- into plate B's edge, through a gabled throat, until its barbs spring out into a window cut
  right through B, catching the window's near wall (edge joint); or
- right through plate B, its barbs catching B's far face (lap joint).

The prongs flex in the pin's print plane and bear on vertical walls, so pin, A and B are all
loaded along their layers. Squeeze the prongs together through the window to take it out.

Dovetail seam (parts bigger than the bed). Trapezoid tabs on one segment's edge drop into
matching sockets in the next, all cut through the plate's thickness, so the seam locks in the
plate's plane with nothing but plastic.

T-slot nut trap (rack ears). A screw bore from B's edge crossed by a slot from B's top face that
a hex nut drops into: the screw's pull bears on the slot's vertical walls. No heat press.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Axis, Box, Face, Location, Part, Plane, Polygon, Pos, Vector, Wire, extrude

from .component import Component
from .fasteners import M3_CLEARANCE, M3_NUT_ACROSS_CORNERS, M3_NUT_HEIGHT
from .plate import Edge, Feature, Plate, teardrop_prism

PIN_THICKNESS = 2.4
PIN_SHANK_WIDTH = 4.0
PIN_HEAD_WIDTH = 7.0
PIN_HEAD_DEPTH = 1.5
"""45 degree wedge head: it narrows from PIN_HEAD_WIDTH to the shank over this depth."""
PIN_BARB = 0.9
PIN_SLOT_WIDTH = 1.6
PIN_SLOT_LENGTH = 4.0
"""How far the slot between the prongs runs back from the barbs."""
PIN_RAMP = 3.0
PIN_TIP_HALF_WIDTH = 1.2
PIN_CLEARANCE = 0.2
PIN_BARB_CLEARANCE = 0.3
PASSAGE_WIDTH = PIN_SHANK_WIDTH + 2 * PIN_CLEARANCE
PASSAGE_THICKNESS = PIN_THICKNESS + 2 * PIN_CLEARANCE
THROAT_LENGTH = 3.0
WINDOW_WIDTH = PIN_SHANK_WIDTH + 2 * PIN_BARB + 0.6
WINDOW_LENGTH = PIN_RAMP + 0.6
SNAP_PLATE_MIN_THICKNESS = 2 * (PASSAGE_THICKNESS / 2 + PASSAGE_WIDTH / 2) + 1.6
"""A gabled throat reaches half its width above its top; keep 0.8 mm of plastic above and below."""

DOVETAIL_ROOT = 10.0
DOVETAIL_TIP = 14.0
DOVETAIL_LENGTH = 8.0
DOVETAIL_CLEARANCE = 0.15
DOVETAIL_PITCH = 45.0

T_SLOT_DEPTH = 6.0
"""Edge to the near face of the nut slot."""
T_SLOT_CLEARANCE = 0.3


def pin_reach(clamp: float) -> float:
    """Head top to barb face for a pin that clamps `clamp` mm before its barbs catch."""
    return clamp + PIN_BARB_CLEARANCE


def pin_solid(reach: float) -> Part:
    """The pin in its print frame: insertion along +x, width along y, thickness along z."""
    head, shank, barb = PIN_HEAD_WIDTH / 2, PIN_SHANK_WIDTH / 2, PIN_SHANK_WIDTH / 2 + PIN_BARB
    tip, slot = reach + PIN_RAMP, PIN_SLOT_WIDTH / 2
    slot_start = reach - PIN_SLOT_LENGTH
    upper = [
        (0.0, head),
        (PIN_HEAD_DEPTH, shank),
        (reach, shank),
        (reach, barb),
        (tip, PIN_TIP_HALF_WIDTH),
        (tip, slot),
        (slot_start, slot),
    ]
    outline = upper + [(x, -y) for x, y in reversed(upper)]
    return extrude(Polygon(*outline, align=None), amount=PIN_THICKNESS, dir=(0, 0, 1))


@dataclass(frozen=True)
class PinGeometry:
    """Where a pin sits, in the rack frame: its head point, insertion direction and width direction."""

    head: Vector
    insertion: Vector
    width: Vector


class SnapPin(Component):
    """One placed pin. Every pin with the same reach is the same printed part."""

    shared = True

    def __init__(self, name: str, reach: float, geometry: PinGeometry) -> None:
        super().__init__(name)
        self.reach = reach
        self.part_name = f"snap_pin_{reach:.1f}mm"
        thickness_axis = geometry.insertion.cross(geometry.width)
        origin = geometry.head - thickness_axis * (PIN_THICKNESS / 2)
        self.placement = Location(Plane(origin=origin, x_dir=geometry.insertion, z_dir=thickness_axis))

    def solids(self) -> dict[str, Part]:
        return {"part": pin_solid(self.reach)}


def _in_plane(direction: Vector) -> Vector:
    return Vector(direction.X, direction.Y, 0).normalized()


@dataclass
class PinPassage(Feature):
    """A slot through plate A for a pin, with a 45 degree pocket for its head on the head face."""

    u: float
    v: float
    width_direction: Vector
    """The pin's width axis in the plate's (u, v) plane."""
    head_on_bed: bool

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        along = _in_plane(self.width_direction)
        across = Vector(0, 0, 1).cross(along)
        slot = Pos(self.u, self.v, t / 2) * _oriented_box(along, PASSAGE_WIDTH, PASSAGE_THICKNESS, t + 2)
        half_top, half_bottom = PIN_HEAD_WIDTH / 2 + PIN_CLEARANCE, PASSAGE_WIDTH / 2
        depth = half_top - half_bottom
        face = Vector(self.u, self.v, 0.0 if self.head_on_bed else t)
        into = Vector(0, 0, 1 if self.head_on_bed else -1)
        corner = face - across * (PASSAGE_THICKNESS / 2)
        # A 45 degree wedge: full head width at the face (and 0.5 mm outside it), shank width at `depth` in.
        wedge = [
            corner - along * half_top - into * 0.5,
            corner + along * half_top - into * 0.5,
            corner + along * half_top,
            corner + along * half_bottom + into * depth,
            corner - along * half_bottom + into * depth,
            corner - along * half_top,
        ]
        return slot + prism(wedge, across, PASSAGE_THICKNESS)


def prism(points: list[Vector], direction: Vector, length: float) -> Part:
    """A planar polygon given by its 3D corners, extruded `length` along `direction`."""
    return extrude(Face(Wire.make_polygon(points, close=True)), amount=length, dir=direction)


def _oriented_box(along: Vector, width: float, thickness: float, height: float) -> Part:
    """A box `width` along `along`, `thickness` across it in the plate's plane, `height` in w, centred."""
    angle = math.degrees(math.atan2(along.Y, along.X))
    return Box(width, thickness, height).rotate(Axis.Z, angle)


@dataclass
class PinThroat(Feature):
    """In plate B's edge: a gabled throat for the pin's shank, then a window through B for its barbs."""

    edge: Edge
    position: float

    def start_and_direction(self, plate: Plate) -> tuple[Vector, Vector]:
        w = plate.thickness / 2
        match self.edge:
            case Edge.U0:
                return Vector(0, self.position, w), Vector(1, 0, 0)
            case Edge.U1:
                return Vector(plate.length, self.position, w), Vector(-1, 0, 0)
            case Edge.V0:
                return Vector(self.position, 0, w), Vector(0, 1, 0)
            case Edge.V1:
                return Vector(self.position, plate.width, w), Vector(0, -1, 0)

    def shape(self, plate: Plate) -> Part:
        start, inward = self.start_and_direction(plate)
        along = Vector(0, 0, 1).cross(inward)
        up = Vector(0, 0, 1)
        half_w, half_t = PASSAGE_WIDTH / 2, PASSAGE_THICKNESS / 2
        mouth = start - inward
        # Gabled section: the roof's apex points up in the print, so no surface is flatter than 45 degrees.
        gable = [
            mouth - along * half_w - up * half_t,
            mouth + along * half_w - up * half_t,
            mouth + along * half_w + up * half_t,
            mouth + up * (half_t + half_w),
            mouth - along * half_w + up * half_t,
        ]
        throat = prism(gable, inward, THROAT_LENGTH + 1)
        centre = start + inward * (THROAT_LENGTH + WINDOW_LENGTH / 2)
        window = Pos(centre.X, centre.Y, plate.thickness / 2) * _oriented_box(
            along, WINDOW_WIDTH, WINDOW_LENGTH, plate.thickness + 2
        )
        return throat + window


@dataclass
class PinThroughSlot(Feature):
    """A plain slot through plate B for a lap pin; its barbs catch B's far face."""

    u: float
    v: float
    width_direction: Vector

    def shape(self, plate: Plate) -> Part:
        along = _in_plane(self.width_direction)
        return Pos(self.u, self.v, plate.thickness / 2) * _oriented_box(
            along, PASSAGE_WIDTH, PASSAGE_THICKNESS, plate.thickness + 2
        )


@dataclass
class NutTrap(Feature):
    """A screw bore from B's edge, crossed by a slot from B's top face that a hex nut drops into."""

    edge: Edge
    position: float
    bore_depth: float

    def start_and_direction(self, plate: Plate) -> tuple[Vector, Vector]:
        return PinThroat(self.edge, self.position).start_and_direction(plate)

    def shape(self, plate: Plate) -> Part:
        start, inward = self.start_and_direction(plate)
        bore = teardrop_prism(start - inward, inward, M3_CLEARANCE / 2, self.bore_depth + 1)
        along = Vector(0, 0, 1).cross(inward)
        slot_width = M3_NUT_ACROSS_CORNERS + T_SLOT_CLEARANCE
        slot_length = M3_NUT_HEIGHT + T_SLOT_CLEARANCE
        bottom = plate.thickness / 2 - slot_width / 2
        height = plate.thickness - bottom + 1
        centre = start + inward * (T_SLOT_DEPTH + slot_length / 2)
        slot = Pos(centre.X, centre.Y, bottom + height / 2) * _oriented_box(along, slot_width, slot_length, height)
        return bore + slot


@dataclass
class DovetailTab(Feature):
    """A trapezoid tab standing out past the plate's edge, wider at its tip."""

    edge: Edge
    position: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        return _dovetail(plate, self.edge, self.position, 0.0, outward=True)


@dataclass
class DovetailSocket(Feature):
    """The socket a neighbouring segment's DovetailTab drops into, with clearance all round."""

    edge: Edge
    position: float

    def shape(self, plate: Plate) -> Part:
        return _dovetail(plate, self.edge, self.position, DOVETAIL_CLEARANCE, outward=False)


def _dovetail(plate: Plate, edge: Edge, position: float, clearance: float, outward: bool) -> Part:
    start, inward = PinThroat(edge, position).start_and_direction(plate)
    direction = -inward if outward else inward
    along = Vector(0, 0, 1).cross(inward)
    root, tip, length = DOVETAIL_ROOT / 2 + clearance, DOVETAIL_TIP / 2 + clearance, DOVETAIL_LENGTH + clearance
    # Tabs are fused flush with the plate's faces; sockets overshoot them so the cut is clean.
    bottom, height = (0.0, plate.thickness) if outward else (-1.0, plate.thickness + 2)
    base = Vector(start.X, start.Y, bottom) - direction * (0.0 if outward else 1.0)
    corners = [
        base - along * root,
        base + along * root,
        base + along * tip + direction * (length + (0.0 if outward else 1.0)),
        base - along * tip + direction * (length + (0.0 if outward else 1.0)),
    ]
    return prism(corners, Vector(0, 0, 1), height)
