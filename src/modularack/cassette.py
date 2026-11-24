# SPDX-License-Identifier: AGPL-3.0-or-later
"""Front modules: self-contained boxes of plates that fill a chassis's front grid.

A cassette spans a block of grid columns and rows. Its two side plates stand on the
floor (or the shelf of the cassette below) and carry everything else. Blank and vent
cassettes close the front with a face plate; drive bays leave it open for sleds,
which ride in grooves cut into the side plates' inner faces.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from build123d import Part, Pos, Vector

from .component import Component
from .joints import Hardware, edge_joint
from .passthrough import (
    COLLAR_CLEARANCE,
    COLLAR_SHORT,
    COLLAR_WALL,
    CONNECTOR_FROM_Y_SIDE,
    CONNECTOR_HEIGHT,
    SataAdapter,
)
from .plate import Edge, Frame, Plate, RectCut, Rib
from .sled import DETENT_BUMP, DRIVE_SIDE_CLEARANCE, RAIL_MIN_WIDTH, Sled, SledGeometry
from .standards import DriveFormFactor

SIDE_THICKNESS = 9.0
FACE_THICKNESS = 6.0
REAR_STOP_THICKNESS = 4.0
SHELF_THICKNESS = 4.0
PANEL_DEPTH = 40.0
"""Front-to-back depth of blank and vent cassettes."""
GROOVE_DEPTH = 1.5
GROOVE_CLEARANCE = 0.3
SLED_SIDE_CLEARANCE = 0.3
SLED_LIFT = 1.0
"""Gap between the bottom of a sled and the floor or shelf under it."""
SLED_TOP_CLEARANCE = 0.5
REAR_GAP = 1.0
DETENT_NOTCH_WIDTH = 4.0
VENT_SLOT_WIDTH = 4.0
VENT_SLOT_PITCH = 8.0
VENT_MARGIN = 8.0
CABLE_WINDOW_MARGIN = 3.0
EXPLODE_RATIO = 1.5


@dataclass(frozen=True)
class CassetteSlot:
    """Where a cassette sits: its outer extent in the rack frame and the bottoms of the rows it spans."""

    y_left: float
    y_right: float
    z_bottom: float
    z_top: float
    row_bottoms: tuple[float, ...]
    row_height: float
    face_bottom: float
    face_top: float
    row: int = 0
    column: int = 0
    columns: int = 1

    @property
    def width(self) -> float:
        return self.y_left - self.y_right

    @property
    def inner_width(self) -> float:
        return self.width - 2 * SIDE_THICKNESS


class ModuleKind(ABC):
    """What a cassette holds."""

    rows: int = 1

    @abstractmethod
    def min_width(self) -> float:
        """Smallest outer width, in mm, this module fits in."""

    @abstractmethod
    def front_x(self) -> float:
        """Where the side plates start: behind a face plate, or at the front for sleds."""

    @abstractmethod
    def depth(self) -> float:
        """Side plate length."""

    def groove_top(self, row_height: float) -> float:
        """Height above a row's bottom that the side plates' inner faces are cut up to (0 = uncut)."""
        return 0.0

    def fits(self, slot: CassetteSlot) -> bool:
        """Whether what this module holds fits a slot of this height (its width is `min_width`)."""
        return True

    def build(self, cassette: Cassette) -> Hardware:
        return Hardware([])


class Cassette(Component):
    def __init__(self, name: str, kind: ModuleKind, slot: CassetteSlot) -> None:
        super().__init__(name)
        if slot.width < kind.min_width() - 1e-6:
            raise ValueError(f"{name}: {slot.width:.1f} mm slot is narrower than the {kind.min_width():.1f} it needs")
        if not kind.fits(slot):
            raise ValueError(
                f"{name}: a {type(kind).__name__} doesn't fit a {slot.face_top - slot.face_bottom:.1f} mm face"
            )
        self.kind = kind
        self.slot = slot
        x0, length, height = kind.front_x(), kind.depth(), slot.z_top - slot.z_bottom
        self.x_front = x0
        self.x_back = x0 + length
        self.left = Plate(
            f"{name}_left",
            length,
            height,
            SIDE_THICKNESS,
            Frame(Vector(x0, slot.y_left, slot.z_bottom), Vector(1, 0, 0), Vector(0, -1, 0)),
        )
        self.right = Plate(
            f"{name}_right",
            length,
            height,
            SIDE_THICKNESS,
            Frame(Vector(x0 + length, slot.y_right, slot.z_bottom), Vector(-1, 0, 0), Vector(0, 1, 0)),
        )
        self.add_child(self.left)
        self.add_child(self.right)
        self.shelf: Plate | None = None
        self.hardware = kind.build(self).items

    def solids(self) -> dict[str, Part]:
        return {}

    def explode_offset(self, distance: float) -> Vector:
        return Vector(-EXPLODE_RATIO * distance, 0, 0)

    def add_shelf(self, thickness: float = SHELF_THICKNESS) -> Plate:
        """A plate across this cassette's top, carrying the cassette above."""
        s = self.slot
        # Shelves start behind the face-plate plane, so face plates in the rows above and below can meet over them.
        x0 = max(self.x_front, FACE_THICKNESS)
        self.shelf = Plate(
            f"{self.name}_shelf",
            self.x_back - x0,
            s.width,
            thickness,
            Frame(Vector(x0, s.y_right, s.z_top), Vector(1, 0, 0), Vector(0, 0, 1)),
        )
        self.add_child(self.shelf)
        return self.shelf

    def side_rows(self) -> list[tuple[Plate, float]]:
        """Each side plate with the local v of each row's bottom."""
        return [(plate, b - self.slot.z_bottom) for plate in (self.left, self.right) for b in self.slot.row_bottoms]

    def add_face(self, name: str) -> Plate:
        s = self.slot
        face = Plate(
            name,
            s.width,
            s.face_top - s.face_bottom,
            FACE_THICKNESS,
            Frame(Vector(0, s.y_right, s.face_bottom), Vector(0, 1, 0), Vector(1, 0, 0)),
        )
        self.add_child(face)
        return face


@dataclass
class Blank(ModuleKind):
    """A plain face plate."""

    rows: int = 1
    width: float = 0.0

    def min_width(self) -> float:
        return self.width or 2 * SIDE_THICKNESS + 2 * VENT_MARGIN

    def front_x(self) -> float:
        return FACE_THICKNESS

    def depth(self) -> float:
        return PANEL_DEPTH - FACE_THICKNESS

    def decorate(self, face: Plate) -> None:
        """Hook for subclasses to cut the face plate."""

    def build(self, cassette: Cassette) -> Hardware:
        face = cassette.add_face(f"{cassette.name}_face")
        self.decorate(face)
        hardware = edge_joint(face, cassette.left, Edge.U0)
        hardware.items += edge_joint(face, cassette.right, Edge.U1).items
        return hardware


@dataclass
class Vent(Blank):
    """A face plate with vertical vent slots between its fixings."""

    def decorate(self, face: Plate) -> None:
        start = SIDE_THICKNESS + VENT_MARGIN
        end = face.length - SIDE_THICKNESS - VENT_MARGIN
        count = int((end - start) // VENT_SLOT_PITCH)
        for k in range(count):
            u = start + k * VENT_SLOT_PITCH
            face.add(RectCut(u, VENT_MARGIN, u + VENT_SLOT_WIDTH, face.width - VENT_MARGIN))


@dataclass
class DriveBay(ModuleKind):
    """A hot-swap bay: sleds riding in grooves, stacked as many to a row as fit, stopped by a rear plate.

    `levels` fixes how many sleds share a row; by default the bay fits as many as the row height
    allows (one 3.5 in or 15 mm 2.5 in drive, two 7 mm 2.5 in drives in a 1U row).
    """

    drive: DriveFormFactor
    rows: int = 1
    levels: int | None = None
    pinned: bool = False
    """Tool-less sleds (`sled.SledGeometry.pinned`): printed pins into the drive's side holes, no screws."""
    pass_through: SataAdapter | None = None
    """A SATA pass-through adapter behind each sled (`passthrough`): the rear stop becomes a backplane."""

    def min_width(self) -> float:
        rail_in_groove = GROOVE_DEPTH - SLED_SIDE_CLEARANCE
        rail = RAIL_MIN_WIDTH
        if self.pinned:
            rail = max(rail, self._nominal(pinned=True).pinned_rail_width())
        sled = self.drive.width + 2 * 0.5 + 2 * rail
        return sled - 2 * rail_in_groove + 2 * SIDE_THICKNESS

    def front_x(self) -> float:
        return 0.0

    def _nominal(self, pinned: bool = False) -> SledGeometry:
        """Sled heights and length don't depend on the bay's width."""
        return SledGeometry(self.drive, self.drive.width + 2 * RAIL_MIN_WIDTH + 1, pinned=pinned)

    def depth(self) -> float:
        adapter = 0.0 if self.pass_through is None else self.pass_through.body_depth
        return self._nominal().length + REAR_GAP + adapter

    def pitch(self) -> float:
        """Height one sled level takes in a row."""
        g = self._nominal()
        return SLED_LIFT + max(g.rail_height, g.bar_height) + SLED_TOP_CLEARANCE

    def levels_in(self, row_height: float) -> int:
        fit = int(row_height // self.pitch())
        wanted = fit if self.levels is None else self.levels
        if wanted < 1 or wanted > fit:
            raise ValueError(
                f"{self.drive.name} bay: {wanted} sled level(s) of {self.pitch():.1f} mm don't fit a "
                f"{row_height:.1f} mm row (room for {fit})"
            )
        return wanted

    def sled_geometry(self, slot: CassetteSlot) -> SledGeometry:
        return SledGeometry(
            self.drive, slot.inner_width + 2 * (GROOVE_DEPTH - SLED_SIDE_CLEARANCE), GROOVE_DEPTH, self.pinned
        )

    def groove_top(self, row_height: float) -> float:
        top_level = self.levels_in(row_height) - 1
        return top_level * self.pitch() + SLED_LIFT + self._nominal().rail_height + GROOVE_CLEARANCE

    def build(self, cassette: Cassette) -> Hardware:
        s = cassette.slot
        geometry = self.sled_geometry(s)
        levels = self.levels_in(s.row_height)
        length = cassette.left.length
        detent_u = length - geometry.detent_x
        sleds = 0
        sled_origins: list[Vector] = []
        for row_index, row_bottom in enumerate(s.row_bottoms):
            for level in range(levels):
                base = row_bottom + level * self.pitch()
                local = base - s.z_bottom
                low = local + SLED_LIFT - GROOVE_CLEARANCE
                high = local + SLED_LIFT + geometry.rail_height + GROOVE_CLEARANCE
                for plate in (cassette.left, cassette.right):
                    plate.add(RectCut(-1, low, length + 1, high, GROOVE_DEPTH))
                # The detent arm is on the sled's y = 0 rail, which sits against the right side plate.
                cassette.right.add(
                    RectCut(
                        detent_u - DETENT_NOTCH_WIDTH / 2,
                        low,
                        detent_u + DETENT_NOTCH_WIDTH / 2,
                        high,
                        GROOVE_DEPTH + DETENT_BUMP + 0.2,
                    )
                )
                origin = Vector(0, s.y_right + SIDE_THICKNESS - GROOVE_DEPTH + SLED_SIDE_CLEARANCE, base + SLED_LIFT)
                cassette.add_child(Sled(f"{cassette.name}_sled{row_index}{level}", geometry, Pos(*origin)))
                sled_origins.append(origin)
                sleds += 1
        stop = Plate(
            f"{cassette.name}_rear_stop",
            s.width,
            s.z_top - s.z_bottom,
            REAR_STOP_THICKNESS,
            Frame(
                Vector(cassette.x_back + REAR_STOP_THICKNESS, s.y_left, s.z_bottom), Vector(0, -1, 0), Vector(-1, 0, 0)
            ),
        )
        if self.pass_through is None:
            margin = SIDE_THICKNESS + geometry.rail_width + CABLE_WINDOW_MARGIN
            stop.add(RectCut(margin, CABLE_WINDOW_MARGIN, stop.length - margin, stop.width - CABLE_WINDOW_MARGIN))
        else:
            self._backplane(stop, s, geometry, sled_origins, self.pass_through)
        cassette.add_child(stop)
        hardware = edge_joint(stop, cassette.left, Edge.U1)
        hardware.items += edge_joint(stop, cassette.right, Edge.U0).items
        if not self.pinned:
            hardware.items += [f"{self.drive.screw}"] * (4 * sleds)
        return hardware

    def _backplane(
        self, stop: Plate, s: CassetteSlot, geometry: SledGeometry, origins: list[Vector], adapter: SataAdapter
    ) -> None:
        """Per sled: a collar locating the adapter, a window for its plug, and blocks that stop the rails."""
        c, wall = COLLAR_CLEARANCE, COLLAR_WALL
        height = adapter.body_depth

        def local(y: float, z: float) -> tuple[float, float]:
            return s.y_left - y, z - s.z_bottom

        bodies: list[tuple[float, float]] = []
        for origin in origins:
            drive_y = origin.Y + geometry.rail_width + DRIVE_SIDE_CLEARANCE
            drive_z = origin.Z + geometry.drive_base
            # The receptacle offset runs toward the drive's datum-Y side, which is rack -y.
            body_y = drive_y + CONNECTOR_FROM_Y_SIDE + adapter.receptacle_offset[0]
            body_z = drive_z + CONNECTOR_HEIGHT - adapter.receptacle_offset[1]
            if any(abs(body_z - z) < adapter.body_height + 2 * c for _, z in bodies):
                raise ValueError(
                    f"{self.drive.name} bay: {adapter.name} bodies ({adapter.body_height:.1f} mm) are taller than "
                    f"the {self.pitch():.1f} mm between stacked sleds; use one sled level (levels=1)"
                )
            bodies.append((body_y, body_z))
            u, v = local(body_y, body_z)
            hw, hh = adapter.body_width / 2 + c, adapter.body_height / 2 + c
            if v - hh < 0 or v + hh > stop.width or u - hw < 0 or u + hw > stop.length:
                raise ValueError(f"{self.drive.name} bay: {adapter.name} doesn't fit behind the sled")
            collar = height - COLLAR_SHORT
            for u0, v0, u1, v1 in (
                (u - hw - wall, v - hh - wall, u + hw + wall, v - hh),
                (u - hw - wall, v + hh, u + hw + wall, v + hh + wall),
                (u - hw - wall, v - hh, u - hw, v + hh),
                (u + hw, v - hh, u + hw + wall, v + hh),
            ):
                # Against the bay's floor the floor itself locates the adapter: a wall without room is left out.
                u0, v0, u1, v1 = max(u0, 0.0), max(v0, 0.0), min(u1, stop.length), min(v1, stop.width)
                if u1 - u0 >= wall / 2 and v1 - v0 >= wall / 2:
                    stop.add(Rib(u0, v0, u1, v1, collar))
            pw, ph = adapter.plug_width / 2 + c, adapter.plug_height / 2 + c
            stop.add(RectCut(u - pw, v - ph, u + pw, v + ph))
            # The sled's rails stop against these just as the drive is fully mated.
            for rail_y in (origin.Y, origin.Y + geometry.width - geometry.rail_width):
                a = local(rail_y + geometry.rail_width, origin.Z)
                b = local(rail_y, origin.Z + geometry.rail_height)
                stop.add(Rib(max(a[0], 0.0), a[1], min(b[0], stop.length), b[1], height + REAR_GAP))


def cells_for(kind: ModuleKind, cell_width: float) -> int:
    return max(1, math.ceil(kind.min_width() / cell_width - 1e-9))
