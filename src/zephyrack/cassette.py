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
from .plate import Edge, Frame, Plate, RectCut
from .sled import DETENT_BUMP, RAIL_MIN_WIDTH, Sled, SledGeometry
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

    def groove_top(self) -> float:
        """Height above a row's bottom that the side plates' inner faces are cut up to (0 = uncut)."""
        return 0.0

    def build(self, cassette: Cassette) -> Hardware:
        return Hardware([])


class Cassette(Component):
    def __init__(self, name: str, kind: ModuleKind, slot: CassetteSlot) -> None:
        super().__init__(name)
        if slot.width < kind.min_width() - 1e-6:
            raise ValueError(f"{name}: {slot.width:.1f} mm slot is narrower than the {kind.min_width():.1f} it needs")
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

    def add_shelf(self) -> Plate:
        """A plate across this cassette's top, carrying the cassette above."""
        s = self.slot
        # Shelves start behind the face-plate plane, so face plates in the rows above and below can meet over them.
        x0 = max(self.x_front, FACE_THICKNESS)
        self.shelf = Plate(
            f"{self.name}_shelf",
            self.x_back - x0,
            s.width,
            SHELF_THICKNESS,
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
    """A hot-swap bay: one sled per row, riding in grooves, stopped by a rear plate with a cable window."""

    drive: DriveFormFactor
    rows: int = 1

    def min_width(self) -> float:
        rail_in_groove = GROOVE_DEPTH - SLED_SIDE_CLEARANCE
        sled = self.drive.width + 2 * 0.5 + 2 * RAIL_MIN_WIDTH
        return sled - 2 * rail_in_groove + 2 * SIDE_THICKNESS

    def front_x(self) -> float:
        return 0.0

    def depth(self) -> float:
        return SledGeometry(self.drive, self.drive.width + 2 * RAIL_MIN_WIDTH + 1).length + REAR_GAP

    def sled_geometry(self, slot: CassetteSlot) -> SledGeometry:
        return SledGeometry(self.drive, slot.inner_width + 2 * (GROOVE_DEPTH - SLED_SIDE_CLEARANCE), GROOVE_DEPTH)

    def groove_top(self) -> float:
        g = SledGeometry(self.drive, self.drive.width + 2 * RAIL_MIN_WIDTH + 1)
        return SLED_LIFT + g.rail_height + GROOVE_CLEARANCE

    def build(self, cassette: Cassette) -> Hardware:
        s = cassette.slot
        geometry = self.sled_geometry(s)
        needed = SLED_LIFT + max(geometry.rail_height, geometry.bar_height) + SLED_TOP_CLEARANCE
        if needed > s.row_height:
            raise ValueError(
                f"{cassette.name}: a {self.drive.name} sled needs {needed:.1f} mm, the row has {s.row_height:.1f}"
            )
        length = cassette.left.length
        for plate, row_bottom in cassette.side_rows():
            low = row_bottom + SLED_LIFT - GROOVE_CLEARANCE
            high = row_bottom + SLED_LIFT + geometry.rail_height + GROOVE_CLEARANCE
            plate.add(RectCut(-1, low, length + 1, high, GROOVE_DEPTH))
        for row_bottom in s.row_bottoms:
            # The detent arm is on the sled's y = 0 rail, which sits against the right side plate.
            detent_u = length - geometry.detent_x
            local_bottom = row_bottom - s.z_bottom
            cassette.right.add(
                RectCut(
                    detent_u - DETENT_NOTCH_WIDTH / 2,
                    local_bottom + SLED_LIFT - GROOVE_CLEARANCE,
                    detent_u + DETENT_NOTCH_WIDTH / 2,
                    local_bottom + SLED_LIFT + geometry.rail_height + GROOVE_CLEARANCE,
                    GROOVE_DEPTH + DETENT_BUMP + 0.2,
                )
            )
            origin = Vector(0, s.y_right + SIDE_THICKNESS - GROOVE_DEPTH + SLED_SIDE_CLEARANCE, row_bottom + SLED_LIFT)
            index = s.row_bottoms.index(row_bottom)
            cassette.add_child(Sled(f"{cassette.name}_sled{index}", geometry, Pos(*origin)))
        stop = Plate(
            f"{cassette.name}_rear_stop",
            s.width,
            s.z_top - s.z_bottom,
            REAR_STOP_THICKNESS,
            Frame(
                Vector(cassette.x_back + REAR_STOP_THICKNESS, s.y_left, s.z_bottom), Vector(0, -1, 0), Vector(-1, 0, 0)
            ),
        )
        margin = SIDE_THICKNESS + geometry.rail_width + CABLE_WINDOW_MARGIN
        stop.add(RectCut(margin, CABLE_WINDOW_MARGIN, stop.length - margin, stop.width - CABLE_WINDOW_MARGIN))
        cassette.add_child(stop)
        hardware = edge_joint(stop, cassette.left, Edge.U1)
        hardware.items += edge_joint(stop, cassette.right, Edge.U0).items
        hardware.items += [f"{self.drive.screw}"] * (4 * len(s.row_bottoms))
        return hardware


def cells_for(kind: ModuleKind, cell_width: float) -> int:
    return max(1, math.ceil(kind.min_width() / cell_width - 1e-9))
