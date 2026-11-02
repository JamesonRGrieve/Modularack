# SPDX-License-Identifier: AGPL-3.0-or-later
"""Flat plates: the one kind of printed part every Zephyrack structure is made of.

A plate lives in its own frame (u, v, w): it spans u in [0, length], v in [0, width],
w in [0, thickness]. That frame *is* the print orientation: w = 0 is the face on the
bed, +w is up. Every plate is placed so +w points into the structure, so the bed face
is the clean outer face.

Printed flat, a plate carries loads in its own plane along the layers, which is where
FDM parts are strong. Every feature is cut so it prints without supports:

- holes through the plate are vertical in the print;
- holes that run in the plate's plane (edge inserts) are teardrops with a 45 degree roof;
- countersinks are 90 degree cones (45 degree walls);
- pockets, grooves, rebates and bosses are only on the top face.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from build123d import (
    Align,
    Box,
    Circle,
    Cone,
    Cylinder,
    Location,
    Part,
    Plane,
    Polygon,
    Pos,
    RegularPolygon,
    Vector,
    Wire,
    extrude,
)
from build123d import Face as BrepFace

from .component import Component
from .fasteners import M3_NUT_ACROSS_CORNERS, M3_NUT_ACROSS_FLATS, M3_NUT_HEIGHT, M3_NUT_POCKET_CLEARANCE

GEOMETRY_TOLERANCE = 1e-6
CONE_BASE = (Align.CENTER, Align.CENTER, Align.MIN)
"""Cones sit on their base: z = 0 at the bottom radius."""


class Face(StrEnum):
    BED = "bed"
    """w = 0, printed against the bed; the structure's outer face."""
    TOP = "top"
    """w = thickness, the structure's inner face."""


class Edge(StrEnum):
    U0 = "u0"
    U1 = "u1"
    V0 = "v0"
    V1 = "v1"


@dataclass(frozen=True)
class Frame:
    """Where a plate's (u, v, w) axes sit in the rack frame. v is w x u."""

    origin: Vector
    u: Vector
    w: Vector

    def __post_init__(self) -> None:
        if abs(self.u.length - 1) > GEOMETRY_TOLERANCE or abs(self.w.length - 1) > GEOMETRY_TOLERANCE:
            raise ValueError("Frame axes must be unit vectors")
        if abs(self.u.dot(self.w)) > GEOMETRY_TOLERANCE:
            raise ValueError("Frame u and w must be perpendicular")

    @property
    def v(self) -> Vector:
        return self.w.cross(self.u)

    @property
    def location(self) -> Location:
        return Location(Plane(origin=self.origin, x_dir=self.u, z_dir=self.w))

    def to_rack(self, point: Vector) -> Vector:
        return self.origin + self.u * point.X + self.v * point.Y + self.w * point.Z

    def direction_to_rack(self, direction: Vector) -> Vector:
        return self.u * direction.X + self.v * direction.Y + self.w * direction.Z

    def to_local(self, point: Vector) -> Vector:
        offset = point - self.origin
        return Vector(offset.dot(self.u), offset.dot(self.v), offset.dot(self.w))

    def direction_to_local(self, direction: Vector) -> Vector:
        return Vector(direction.dot(self.u), direction.dot(self.v), direction.dot(self.w))


class Feature(ABC):
    """Something added to or cut from a plate, built in the plate's frame."""

    additive = False

    @abstractmethod
    def shape(self, plate: Plate) -> Part: ...

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        """The (u, v) rectangle and w range this feature occupies, for features `feature_extent` doesn't know."""
        return None, (0.0, 0.0)


def teardrop_prism(start: Vector, direction: Vector, radius: float, length: float, up: Vector | None = None) -> Part:
    """A horizontal hole that prints without supports: a circle with a 45 degree roof toward `up`.

    `up` is the print's up direction in the plate's frame: +w for a plate printed flat.
    """
    up = Vector(0, 0, 1) if up is None else up
    along = abs(direction.dot(up))
    if abs(along - 1) < GEOMETRY_TOLERANCE:
        # A vertical hole in the print needs no roof.
        return extrude(Plane(origin=start, z_dir=direction) * Circle(radius), amount=length, dir=direction)
    if along > GEOMETRY_TOLERANCE:
        raise ValueError("Holes run either along the print's up direction or across it")
    plane = Plane(origin=start, x_dir=up, z_dir=direction)
    corner = radius / math.sqrt(2)
    roof = Polygon((0, 0), (corner, corner), (radius * math.sqrt(2), 0), (corner, -corner), align=None)
    round_part = extrude(plane * Circle(radius), amount=length, dir=direction)
    roof_part = extrude(plane * roof, amount=length, dir=direction)
    # One fused solid: Shape.cut() with a two-solid compound leaves the roof uncut.
    return round_part.fuse(roof_part).clean()


@dataclass
class ThroughHole(Feature):
    """A clearance hole through the plate, optionally countersunk on one face."""

    u: float
    v: float
    diameter: float
    countersink: Face | None = None
    countersink_diameter: float = 0.0

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        if plate.print_up is not None:
            return self._side_printed(plate)
        hole: Part = Pos(self.u, self.v, t / 2) * Cylinder(self.diameter / 2, t + 2)
        if self.countersink is not None:
            depth = (self.countersink_diameter - self.diameter) / 2
            if depth >= t:
                raise ValueError(f"{plate.name}: countersink deeper than the {t} mm plate")
            if self.countersink is Face.BED:
                cone = Pos(self.u, self.v, 0) * Cone(
                    self.countersink_diameter / 2, self.diameter / 2, depth, align=CONE_BASE
                )
            else:
                cone = Pos(self.u, self.v, t - depth) * Cone(
                    self.diameter / 2, self.countersink_diameter / 2, depth, align=CONE_BASE
                )
            hole += cone
        return hole

    def _side_printed(self, plate: Plate) -> Part:
        """In a plate printed on its edge the hole lies across the layers: a teardrop bore. A 90 degree
        countersink cone needs nothing extra, since none of its surface is steeper than 45 degrees."""
        assert plate.print_up is not None
        t = plate.thickness
        hole = teardrop_prism(Vector(self.u, self.v, -1), Vector(0, 0, 1), self.diameter / 2, t + 2, plate.print_up)
        if self.countersink is None:
            return hole
        depth = (self.countersink_diameter - self.diameter) / 2
        if self.countersink is Face.BED:
            cone = Pos(self.u, self.v, 0) * Cone(
                self.countersink_diameter / 2, self.diameter / 2, depth, align=CONE_BASE
            )
        else:
            cone = Pos(self.u, self.v, t - depth) * Cone(
                self.diameter / 2, self.countersink_diameter / 2, depth, align=CONE_BASE
            )
        return hole.fuse(cone).clean()


@dataclass
class EdgeInsert(Feature):
    """A heat-set insert bore running in from an edge, in the plate's plane."""

    edge: Edge
    position: float
    """Distance along the edge from its u = 0 / v = 0 end."""
    bore_diameter: float
    bore_depth: float
    relief_diameter: float
    relief_depth: float

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
        start, direction = self.start_and_direction(plate)
        overshoot = 1.0
        up = plate.print_up
        bore = teardrop_prism(
            start - direction * overshoot, direction, self.bore_diameter / 2, self.bore_depth + overshoot, up
        )
        relief_start = start + direction * self.bore_depth
        relief = teardrop_prism(relief_start, direction, self.relief_diameter / 2, self.relief_depth, up)
        return bore + relief


@dataclass
class EdgeNut(EdgeInsert):
    """A screw bore in from an edge, crossed by a T-slot from the top face that a hex nut drops into
    (flat side down). For plates too thin for an edge insert: the screw's pull bears on the slot's walls."""

    slot_depth: float = 4.0
    """From the edge to the nut's near face."""

    def shape(self, plate: Plate) -> Part:
        start, direction = self.start_and_direction(plate)
        bore = teardrop_prism(start - direction, direction, self.bore_diameter / 2, self.bore_depth + 1, plate.print_up)
        return bore.fuse(self._slot(plate, start, direction)).clean()

    def _slot(self, plate: Plate, start: Vector, direction: Vector) -> Part:
        t = plate.thickness
        along = M3_NUT_HEIGHT + M3_NUT_POCKET_CLEARANCE
        across = M3_NUT_ACROSS_CORNERS + M3_NUT_POCKET_CLEARANCE
        bottom = start.Z - self.floor_offset()
        centre = start + direction * (self.slot_depth + along / 2)
        size_u, size_v = (along, across) if abs(direction.X) > 0.5 else (across, along)
        return Pos(centre.X, centre.Y, (bottom + t + 1) / 2) * Box(size_u, size_v, t + 1 - bottom)

    @staticmethod
    def floor_offset() -> float:
        """How far below the bore's axis the slot's floor lies: half the nut across flats, plus clearance."""
        return M3_NUT_ACROSS_FLATS / 2 + M3_NUT_POCKET_CLEARANCE / 2


@dataclass
class TopPocket(Feature):
    """A blind round pocket opening on the top face (an insert bore), or right through."""

    u: float
    v: float
    diameter: float
    depth: float
    through: bool = False

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        if plate.print_up is not None:
            # Across the layers of an edge-printed plate: a teardrop, in from the top face.
            depth = t + 2 if self.through else self.depth + 1
            return teardrop_prism(
                Vector(self.u, self.v, t + 1), Vector(0, 0, -1), self.diameter / 2, depth, plate.print_up
            )
        if self.through:
            return Pos(self.u, self.v, t / 2) * Cylinder(self.diameter / 2, t + 2)
        return Pos(self.u, self.v, t - self.depth / 2 + 0.5) * Cylinder(self.diameter / 2, self.depth + 1)


@dataclass
class Rib(Feature):
    """A box standing on the top face (a guide or a stop)."""

    u0: float
    v0: float
    u1: float
    v1: float
    height: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        return Pos((self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2, t + self.height / 2 - 0.5) * Box(
            self.u1 - self.u0, self.v1 - self.v0, self.height + 1
        )


@dataclass
class BossPocket(Feature):
    """An insert bore down from the top of a boss standing `boss_height` above the top face."""

    u: float
    v: float
    diameter: float
    depth: float
    boss_height: float

    def shape(self, plate: Plate) -> Part:
        top = plate.thickness + self.boss_height
        return Pos(self.u, self.v, top - self.depth / 2 + 0.5) * Cylinder(self.diameter / 2, self.depth + 1)


@dataclass
class HexPocket(Feature):
    """A captive-nut pocket opening on the top face."""

    u: float
    v: float
    across_corners: float
    depth: float

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        prism = extrude(RegularPolygon(self.across_corners / 2, 6), amount=self.depth + 1)
        return Pos(self.u, self.v, t - self.depth) * prism


@dataclass
class RectCut(Feature):
    """A rectangular region removed from the top face down to `depth`, or right through."""

    u0: float
    v0: float
    u1: float
    v1: float
    depth: float | None = None
    """None cuts through the plate."""
    from_bed: bool = False
    """Cut the pocket in from the bed face (w = 0) instead of the top face."""

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        du, dv = self.u1 - self.u0, self.v1 - self.v0
        if du <= 0 or dv <= 0:
            raise ValueError(f"{plate.name}: empty cut")
        if self.depth is None:
            box = Pos((self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2, t / 2) * Box(du, dv, t + 2)
        else:
            centre = self.depth / 2 - 0.5 if self.from_bed else t - self.depth / 2 + 0.5
            box = Pos((self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2, centre) * Box(du, dv, self.depth + 1)
        if plate.print_up is None:
            return box
        return box.fuse(self._roof(plate)).clean()

    def _roof(self, plate: Plate) -> Part:
        """On an edge-printed plate the cut's upper side would be a ceiling: slope it at 45 degrees instead.

        A through cut gets a gable across the thickness; a pocket a single slope rising to its open face.
        """
        assert plate.print_up is not None
        t, up = plate.thickness, plate.print_up
        along_u = abs(up.X) > abs(up.Y)
        sign = (up.X if along_u else up.Y) > 0
        ceiling = (self.u1 if sign else self.u0) if along_u else (self.v1 if sign else self.v0)
        rise = 1.0 if sign else -1.0
        if self.depth is None:
            section = [(ceiling, -1.0), (ceiling, t + 1), (ceiling + rise * (t + 2) / 2, t / 2)]
        elif self.from_bed:
            section = [(ceiling, self.depth), (ceiling, -1.0), (ceiling + rise * (self.depth + 1), -1.0)]
        else:
            floor = t - self.depth
            section = [(ceiling, floor), (ceiling, t + 1), (ceiling + rise * (self.depth + 1), t + 1)]
        if along_u:
            points = [Vector(a, self.v0, w) for a, w in section]
            direction, length = Vector(0, 1, 0), self.v1 - self.v0
        else:
            points = [Vector(self.u0, a, w) for a, w in section]
            direction, length = Vector(1, 0, 0), self.u1 - self.u0
        return extrude(BrepFace(Wire.make_polygon(points, close=True)), amount=length, dir=direction)


def edge_pocket(plate: Plate, u: float, length: float, height: float, depth: float) -> RectCut:
    """A pocket in the bed face, open at the bottom (v = 0) edge, for a tongue to bear up into.

    On a plate printed upright the pocket's far side is roofed (RectCut._roof); on one printed flat a
    pocket in the bed face would be a ceiling, so it goes right through instead: a notch.
    """
    half = length / 2
    return RectCut(u - half, -1.0, u + half, height, None if plate.print_up is None else depth, from_bed=True)


@dataclass
class Slot(Feature):
    """A through slot with round ends, running along u."""

    u: float
    v: float
    diameter: float
    travel: float

    def shape(self, plate: Plate) -> Part:
        t = plate.thickness
        half = self.travel / 2
        parts: Part = Pos(self.u - half, self.v, t / 2) * Cylinder(self.diameter / 2, t + 2)
        parts += Pos(self.u + half, self.v, t / 2) * Cylinder(self.diameter / 2, t + 2)
        if self.travel > 0:
            parts += Pos(self.u, self.v, t / 2) * Box(self.travel, self.diameter, t + 2)
        if plate.print_up is None:
            return parts
        return parts.fuse(self._roof(plate)).clean()

    def _roof(self, plate: Plate) -> Part:
        """Upright, the slot's lower side (in the print) would be a ceiling: two 45 degree lines tangent to
        both end circles, meeting under its middle, like a teardrop's roof."""
        assert plate.print_up is not None
        up = plate.print_up
        if abs(up.X) > GEOMETRY_TOLERANCE:
            raise ValueError(f"{plate.name}: slots run across the print's up direction")
        sign = 1.0 if up.Y > 0 else -1.0
        t, r, half = plate.thickness, self.diameter / 2, self.travel / 2
        tangent = r / math.sqrt(2)
        base = self.v + sign * tangent
        apex = base + sign * (half + tangent)
        points = [
            Vector(self.u - half - tangent, base, -1),
            Vector(self.u + half + tangent, base, -1),
            Vector(self.u, apex, -1),
        ]
        return extrude(BrepFace(Wire.make_polygon(points, close=True)), amount=t + 2, dir=(0, 0, 1))


@dataclass
class Boss(Feature):
    """A cylinder standing on the top face."""

    u: float
    v: float
    diameter: float
    height: float
    additive = True

    def shape(self, plate: Plate) -> Part:
        return Pos(self.u, self.v, plate.thickness + self.height / 2) * Cylinder(self.diameter / 2, self.height)


@dataclass
class Plate(Component):
    """A printed flat plate placed in the rack frame."""

    name: str
    length: float
    width: float
    thickness: float
    frame: Frame
    explode_direction: Vector = field(default_factory=lambda: Vector(0, 0, 0))
    features: list[Feature] = field(default_factory=list)
    print_up: Vector | None = None
    """None: printed flat, bed face (w = 0) down. Otherwise the plate prints standing on an edge and
    this direction, in the plate's (u, v) plane, points up in the print."""

    def __post_init__(self) -> None:
        Component.__init__(self, self.name)
        if self.length <= 0 or self.width <= 0 or self.thickness <= 0:
            raise ValueError(f"{self.name}: plate dimensions must be positive")
        self.placement = self.frame.location
        self.merged: list[Plate] = []
        """Plates printed as one piece with this one (see `merge`)."""
        self.merged_into: Plate | None = None
        self._cache: tuple[int, Part] | None = None
        if self.print_up is not None:
            self.set_print_up(self.print_up)

    def set_print_up(self, up: Vector) -> None:
        """Print this plate standing on an edge, with `up` (a direction in its own plane) up in the print."""
        if abs(up.Z) > GEOMETRY_TOLERANCE:
            raise ValueError(f"{self.name}: an edge-printed plate's up direction lies in its plane")
        self.print_up = up
        # Express the plate in a frame whose +Z is print_up: that is its print orientation.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 0, 1), z_dir=up)).inverse()

    def merge(self, other: Plate) -> None:
        """Print `other` as one piece with this plate: its solid joins this one's and it has none of its own.

        Both keep their features, frames and joints; only what gets printed changes.
        """
        if other.merged_into is not None or other is self:
            raise ValueError(f"{other.name} is already part of another print")
        other.merged_into = self
        self.merged.append(other)

    def add(self, feature: Feature) -> Feature:
        self.features.append(feature)
        return feature

    def solids(self) -> dict[str, Part]:
        if self.merged_into is not None:
            return {}
        body = self.body()
        if not self.merged:
            return {"plate": body}
        relative = self.placement.inverse()
        others = [other.body().moved(relative * other.placement) for other in self.merged]
        return {"plate": body.fuse(*others).clean()}

    def body(self) -> Part:
        """This plate alone, in its own frame, whether or not it is printed as part of another."""
        key = len(self.features)
        if self._cache is None or self._cache[0] != key:
            body: Part = Pos(self.length / 2, self.width / 2, self.thickness / 2) * Box(
                self.length, self.width, self.thickness
            )
            additions = [f.shape(self) for f in self.features if f.additive]
            if additions:
                body = body.fuse(*additions).clean()
            cuts = [f.shape(self) for f in self.features if not f.additive]
            if cuts:
                body = body.cut(*cuts).clean()
            self._cache = (key, body)
        return self._cache[1]

    def explode_offset(self, distance: float) -> Vector:
        return self.explode_direction * distance

    def contains(self, u: float, v: float, margin: float = 0.0) -> bool:
        return margin <= u <= self.length - margin and margin <= v <= self.width - margin

    def blocked(self, region: tuple[float, float, float, float], w_low: float, w_high: float) -> bool:
        """Whether a new feature filling region (u0, v0, u1, v1) between w_low and w_high would hit an existing one."""
        u0, v0, u1, v1 = region
        for occupied, (f_low, f_high) in (feature_extent(f, self) for f in self.features):
            if occupied is None:
                continue
            a0, b0, a1, b1 = occupied
            if a0 < u1 and u0 < a1 and b0 < v1 and v0 < b1 and f_low < w_high and w_low < f_high:
                return True
        return False


def feature_extent(
    feature: Feature, plate: Plate
) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
    """The (u, v) rectangle and w range a feature occupies, for collision checks."""
    t = plate.thickness
    match feature:
        case RectCut(u0=u0, v0=v0, u1=u1, v1=v1, depth=depth, from_bed=from_bed):
            if depth is None:
                return (u0, v0, u1, v1), (-1.0, t + 1)
            return (u0, v0, u1, v1), (-1.0, depth) if from_bed else (t - depth, t + 1)
        case ThroughHole(u=u, v=v, diameter=d, countersink_diameter=c):
            r = max(d, c) / 2
            return (u - r, v - r, u + r, v + r), (-1.0, t + 1)
        case TopPocket(u=u, v=v, diameter=d, depth=depth, through=through):
            r = d / 2
            return (u - r, v - r, u + r, v + r), (-1.0 if through else t - depth, t + 1)
        case HexPocket(u=u, v=v, across_corners=d, depth=depth):
            r = d / 2
            return (u - r, v - r, u + r, v + r), (t - depth, t + 1)
        case Slot(u=u, v=v, diameter=d, travel=travel):
            r = d / 2
            return (u - travel / 2 - r, v - r, u + travel / 2 + r, v + r), (-1.0, t + 1)
        case EdgeNut():
            start, direction = feature.start_and_direction(plate)
            end = start + direction * feature.bore_depth
            r = (M3_NUT_ACROSS_CORNERS + M3_NUT_POCKET_CLEARANCE) / 2
            lo_u, hi_u = sorted((start.X, end.X))
            lo_v, hi_v = sorted((start.Y, end.Y))
            return (lo_u - r, lo_v - r, hi_u + r, hi_v + r), (start.Z - EdgeNut.floor_offset(), t + 1)
        case EdgeInsert():
            start, direction = feature.start_and_direction(plate)
            reach = feature.bore_depth + feature.relief_depth
            end = start + direction * reach
            r = feature.bore_diameter / 2
            lo_u, hi_u = sorted((start.X, end.X))
            lo_v, hi_v = sorted((start.Y, end.Y))
            return (lo_u - r, lo_v - r, hi_u + r, hi_v + r), (start.Z - r, start.Z + r * math.sqrt(2))
        case _:
            return feature.extent(plate)
