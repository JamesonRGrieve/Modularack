# SPDX-License-Identifier: AGPL-3.0-or-later
"""A 1U-4U rack chassis for 10 in or 19 in racks, built entirely from printed plates.

Structure and load path:

- The floor and cover are panels. The side walls and the rear wall stand on the floor; the side
  walls run up to the chassis's top, the cover sits between them on the rear wall. Edge joints
  (inserts in an edge) join them: floor into the walls' bottom edges, walls into the cover's edges.
- Rack ears bolt to the side walls' front edges. Chassis weight goes floor -> wall
  inserts -> wall -> ear -> rack screws, along the layers of every part on the way.
- The front is a grid (12 columns by one row per U) filled with cassettes. Every cassette
  stands on the floor or the shelf of the cassette below, is screwed down to it and up
  into the cover or the shelf above, and is bolted to its neighbours and to the walls.
- A motherboard sits behind the cassettes on standoff bosses at the Intel hole positions,
  its I/O facing the rear wall's aperture.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from build123d import Part, Vector

from . import lid, toolless
from .braces import KNEE_DEPTH_FRACTION, KneeBrace, socket_for
from .cassette import (
    SHELF_THICKNESS,
    SIDE_THICKNESS,
    Blank,
    Cassette,
    CassetteSlot,
    ModuleKind,
    cells_for,
)
from .component import Component
from .fans import FanGrille
from .fans import needs as fan_room
from .fasteners import INSERT_M3_LONG, RACK_SCREW_CLEARANCE
from .hooks import (
    HOOK_HOLES_PER_UNIT,
    UPRIGHT,
    RackHook,
    RackPeg,
    SpringHook,
    SpringHookCut,
    hook_width,
    spring_housing_depth,
)
from .joints import EDGE_JOINT_END_MARGIN, Hardware, LapFastening, edge_joint, edge_positions, lap_joint
from .layout import MK3S_BED, Bed, Panel
from .plate import Boss, BossPocket, Edge, Feature, Frame, Plate, RectCut, Rib, Slot, ThroughHole, feature_extent
from .print_settings import SOLID
from .rear import TONGUE_SPACING, RearArm, RearLayout, RearPin, pockets_for
from .rear import TOP_MARGIN as REAR_TOP_MARGIN
from .standards import (
    ATX_PSU,
    BOARD_THICKNESS,
    CEB,
    EEB,
    EEB_ALTERNATE_HOLES,
    HOLE_C_TO_REAR_PANEL,
    HOLE_POSITIONS_FROM_C,
    IO_APERTURE_BELOW_BOARD_TOP,
    IO_APERTURE_HEIGHT,
    IO_APERTURE_OFFSET_FROM_C,
    IO_APERTURE_WIDTH,
    PANEL_HEIGHT_DEDUCTION,
    RACK_UNIT,
    STANDOFF_HEIGHT,
    U_HOLE_OFFSETS,
    MotherboardFormFactor,
    MountingHole,
    RackStandard,
    panel_height,
)
from .web import PLATE_THICKNESS as WEB_PLATE_THICKNESS
from .web import PostChannel, WebClamp, clamp_pocket

MIN_UNITS = 1
MAX_UNITS = 4
GRID_COLUMNS = 12
WALL_THICKNESS = 9.0
FLOOR_THICKNESS = 7.0
COVER_THICKNESS = FLOOR_THICKNESS
"""The cover sits between the full-height side walls, which screw into captive nuts in its edges."""
COVER_RECESS = 1.0
CORNER_RESERVE_MARGIN = 2.0
PSU_MARGIN = 2.0
"""Between the board (or the power supply's rib) and a side wall."""
PSU_RIB = 4.0
PSU_RIB_HEIGHT = 8.0
PSU_CLEARANCE = 2.0
PSU_OPENING_INSET = 12.0
"""The rear wall's opening for the supply's fan and inlet stops this far inside its face, clear of the screws."""
REAR_TONGUE_INSET = 30.0
"""The rear support's rear tongue sits this far in front of the chassis's back."""
"""The cover's top sits this far below the walls' top, so the walls' screws into it clear their top edge."""
EAR_THICKNESS = 9.0
"""Thicker than the 6 mm face plates: the ears take the overturning moment through their countersunk screws."""
SIDE_CLEARANCE = 1.0
"""Gap between each side of the chassis and the rack posts."""
EAR_HOLES_PER_UNIT = (0, 2)
"""Which of a U's three EIA holes the ears use: the outer pair, as standard ears do."""
STANDOFF_BOSS_DIAMETER = 9.0
BOARD_FRONT_CLEARANCE = 5.0
"""Space between the back of the deepest cassette and the front edge of the motherboard."""
SEAM_STAGGER = 40.0
"""Wall seams keep this far from floor and cover seams, so no seam plane cuts the whole box."""
LAP_COUNT = 2
LAP_MIN_SPACING = 20.0
LAP_GROOVE_CLEARANCE = 4.5
"""Lap screws sit this far above the top of any sled groove, so their heads never meet a rail."""
LAP_TOP_CLEARANCE = 5.0


@dataclass(frozen=True)
class PsuLayout:
    y0: float
    y1: float
    """The power supply's sides (rack y)."""
    height: float
    on_side: bool


@dataclass
class Placement:
    kind: ModuleKind
    column: int
    row: int
    columns: int


class EarStyle(StrEnum):
    """How the chassis mounts in the rack."""

    SCREW = "screw"
    """Slotted ears for M6 rack screws: round, threaded or cage-nut holes."""
    HOOK = "hook"
    """Square-hole racks: rigid hooks, printed upright. Push in, drop HOOK_TRAVEL and the hooks seat;
    taking the chassis out needs that much free space above it."""
    SNAP = "snap"
    """Square-hole racks, push straight in: pegs carry the weight and a spring hook in the top U's top
    hole snaps sideways behind the flange; push it inboard to release. Works in a full rack."""


@dataclass
class RackChassis(Component):
    rack: RackStandard
    units: int
    depth: float
    motherboard: MotherboardFormFactor | None = None
    bed: Bed = MK3S_BED
    alternate_holes: frozenset[MountingHole] = frozenset()
    """SSI EEB/CEB alternate locations (F', H', ...) the chosen board uses, added to its legacy holes."""
    ear_style: EarStyle = EarStyle.SCREW
    one_piece: bool = False
    rear_support: tuple[float, float] | None = None
    """Four-post racks: carry the chassis's back on the rear posts (`rear`), adjustable between these rack
    depths (front posts' front face to rear posts' front face, mm). None: no rear support."""
    knee_brace_units: int | None = None
    web_clamp: PostChannel | None = None
    toolless_box: bool = False
    """Tool-less side walls and rear wall too (`toolless`): floor dovetails and spring latches, no screws
    between panels. Implies `toolless_cover`; the side walls stand `toolless.WALL_INSET` in from the
    floor's edges."""
    toolless_cover: bool = False
    """A tool-less cover (`lid`): dovetail tabs in the side walls and a spring latch, instead of screws.
    It prints inner face down and isn't screwed to the rear wall or the top row of modules."""
    power_supply: bool = False
    """An ATX power supply bay at the rear wall (`standards.ATX_PSU`): its rear face screws to the wall, its
    body (any length up to the spec's longest) rests between ribs on the floor beside the board, flat or on
    its side, whichever fits. The board moves to the far side to make room."""
    rear_fans: tuple[int, ...] = ()
    """Fan grilles in the rear wall, by fan size (mm), placed clear of the I/O aperture and seams."""
    cover_fans: tuple[int, ...] = ()
    """Fan grilles in the cover, by fan size, placed from the rear forward."""
    """Two-post channel racks: clamp each side wall to the post's side web (`web`). None: no clamps."""
    """Prop each side wall with a knee brace (`braces`) from the top hole of the U this many units below
    (1 or 2; 2 is much stiffer). Those units' hole columns must be free. None: no braces."""
    """Print each ear and the front segment of its side wall as one upright piece, with no joint between them."""
    placements: list[Placement] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.alternate_holes <= EEB_ALTERNATE_HOLES:
            raise ValueError(f"Not SSI alternate locations: {sorted(self.alternate_holes - EEB_ALTERNATE_HOLES)}")
        if self.alternate_holes and self.motherboard not in (EEB, CEB):
            raise ValueError("Alternate mounting locations are defined only for SSI EEB and CEB boards")
        if not MIN_UNITS <= self.units <= MAX_UNITS:
            raise ValueError(f"Zephyrack chassis are {MIN_UNITS}U-{MAX_UNITS}U, got {self.units}U")
        Component.__init__(self, f"chassis_{self.rack.name}_{self.units}U")
        if self.toolless_box:
            self.toolless_cover = True
        self.floor_width = self.rack.opening - 2 * SIDE_CLEARANCE
        self.wall_inset = toolless.WALL_INSET if self.toolless_box else 0.0
        self.width = self.floor_width - 2 * self.wall_inset
        """Outside the side walls: the floor is `floor_width`, wider by the walls' inset."""
        self.height = panel_height(self.units)
        self.inner_width = self.width - 2 * WALL_THICKNESS
        self.inner_height = self.height - FLOOR_THICKNESS - COVER_THICKNESS - COVER_RECESS
        self.cell_width = self.inner_width / GRID_COLUMNS
        self.row_height = (self.inner_height - (self.units - 1) * SHELF_THICKNESS) / self.units
        self.occupied = [[False] * GRID_COLUMNS for _ in range(self.units)]
        self.max_module_columns = int(max(self.bed.usable_x, self.bed.usable_y) // self.cell_width)
        self.built = False

    def solids(self) -> dict[str, Part]:
        return {}

    # Grid -----------------------------------------------------------------------------------

    def row_bottom(self, row: int) -> float:
        return FLOOR_THICKNESS + row * (self.row_height + SHELF_THICKNESS)

    def is_available(self, column: int, row: int, columns: int, rows: int) -> bool:
        if column < 0 or row < 0 or column + columns > GRID_COLUMNS or row + rows > self.units:
            return False
        return not any(self.occupied[r][c] for r in range(row, row + rows) for c in range(column, column + columns))

    def add_module(self, kind: ModuleKind, column: int, row: int, columns: int | None = None) -> Placement:
        if self.built:
            raise RuntimeError(f"{self.name} is already built")
        span = columns if columns is not None else cells_for(kind, self.cell_width)
        if span * self.cell_width < kind.min_width() - 1e-6:
            raise ValueError(f"{type(kind).__name__} needs {cells_for(kind, self.cell_width)} columns, got {span}")
        if span > self.max_module_columns:
            raise ValueError(
                f"{type(kind).__name__} would be {span * self.cell_width:.1f} mm wide; the bed prints modules up to "
                f"{self.max_module_columns} columns ({self.max_module_columns * self.cell_width:.1f} mm)"
            )
        if not self.is_available(column, row, span, kind.rows):
            raise ValueError(
                f"{type(kind).__name__} ({span}x{kind.rows}) does not fit at column {column}, row {row} of {self.name}"
            )
        for r in range(row, row + kind.rows):
            for c in range(column, column + span):
                self.occupied[r][c] = True
        placement = Placement(kind, column, row, span)
        self.placements.append(placement)
        return placement

    def fill_blanks(self) -> None:
        """Close every free run of cells, row by row, with a blank face."""
        for row in range(self.units):
            column = 0
            while column < GRID_COLUMNS:
                if self.occupied[row][column]:
                    column += 1
                    continue
                end = column
                while end < GRID_COLUMNS and not self.occupied[row][end]:
                    end += 1
                # Split long runs into blanks the bed can print, as evenly as the cells allow.
                run = end - column
                pieces = math.ceil(run / self.max_module_columns)
                for k in range(pieces):
                    width = run // pieces + (1 if k < run % pieces else 0)
                    self.add_module(Blank(), column, row, width)
                    column += width

    # Building ---------------------------------------------------------------------------------

    def build(self) -> Hardware:
        """Lay out every plate and joint. Call once, after placing modules."""
        if self.built:
            raise RuntimeError(f"{self.name} is already built")
        self.fill_blanks()
        self.built = True
        hardware = Hardware([])
        cassettes = self._cassettes()
        self._check_board_clearance(cassettes)
        standoffs = self._standoffs()
        self._panels(cassettes, standoffs)
        for cassette in cassettes.values():
            self.add_child(cassette)
            hardware.items += cassette.hardware
        # Joints are laid tightest-first: each later joint's stations slide clear of earlier ones.
        if not self.toolless_box:
            hardware.items += self._rear_corner_joints().items
        hardware.items += self._ears().items
        self._psu_bay()
        if self.toolless_cover:
            self._cover_latch()
        self._place_fans(self.rear_wall, self.rear_fans, from_end=False)
        self._place_fans(self.cover, self.cover_fans, from_end=True)
        hardware.items += self._floor_cover_joints().items
        hardware.items += self._cassette_joints(cassettes).items
        self._board(standoffs)
        for panel in (self.floor, self.cover, self.left_wall, self.right_wall, self.rear_wall):
            hardware.items += panel.screws
        self.hardware = hardware.items
        return hardware

    def bill_of_materials(self) -> Counter[str]:
        return Counter(self.hardware)

    def _slot(self, placement: Placement) -> CassetteSlot:
        y_left = self.inner_width / 2 - placement.column * self.cell_width
        y_right = y_left - placement.columns * self.cell_width
        top_row = placement.row + placement.kind.rows - 1
        z_bottom = self.row_bottom(placement.row)
        z_top = self.row_bottom(top_row) + self.row_height
        face_bottom = 0.0 if placement.row == 0 else z_bottom - SHELF_THICKNESS / 2
        face_top = self.height if top_row == self.units - 1 else z_top + SHELF_THICKNESS / 2
        rows = tuple(self.row_bottom(r) for r in range(placement.row, top_row + 1))
        return CassetteSlot(
            y_left,
            y_right,
            z_bottom,
            z_top,
            rows,
            self.row_height,
            face_bottom,
            face_top,
            placement.row,
            placement.column,
            placement.columns,
        )

    def _cassettes(self) -> dict[tuple[int, int], Cassette]:
        cassettes: dict[tuple[int, int], Cassette] = {}
        for placement in sorted(self.placements, key=lambda p: (p.row, p.column)):
            name = f"{self.name}_r{placement.row}c{placement.column}"
            cassette = Cassette(name, placement.kind, self._slot(placement))
            if placement.row + placement.kind.rows < self.units:
                cassette.add_shelf()
            cassettes[(placement.row, placement.column)] = cassette
        return cassettes

    def _check_board_clearance(self, cassettes: dict[tuple[int, int], Cassette]) -> float:
        deepest = max(c.x_back for c in cassettes.values()) + SHELF_THICKNESS
        if self.motherboard is None:
            if deepest > self.depth - WALL_THICKNESS:
                raise ValueError(f"{self.name}: cassettes are {deepest:.1f} mm deep, the chassis only {self.depth}")
            return deepest
        board_front = self._board_rear_x() - self.motherboard.depth
        if board_front < deepest + BOARD_FRONT_CLEARANCE:
            raise ValueError(
                f"{self.name}: a {self.motherboard.name} board needs the chassis "
                f"{deepest + BOARD_FRONT_CLEARANCE - board_front:.1f} mm deeper"
            )
        if self.motherboard.width > self.inner_width:
            raise ValueError(
                f"{self.motherboard.name} is wider than the {self.inner_width:.1f} mm {self.rack.name} chassis"
            )
        return board_front

    def _board_rear_x(self) -> float:
        assert self.motherboard is not None
        hole_c_x = self.depth - WALL_THICKNESS - HOLE_C_TO_REAR_PANEL
        return hole_c_x + self.motherboard.hole_c_from_corner[1]

    def _standoffs(self) -> dict[MountingHole, tuple[float, float]]:
        """Rack X/Y of every hole of the board, with its I/O edge toward the rear wall and centred left-right."""
        if self.motherboard is None:
            return {}
        board = self.motherboard
        rear_x = self._board_rear_x()
        left_y = board.width / 2 + self._board_shift()
        cx, cy = board.hole_c_from_corner
        return {
            hole: (rear_x - (cy + HOLE_POSITIONS_FROM_C[hole][1]), left_y - (cx + HOLE_POSITIONS_FROM_C[hole][0]))
            for hole in sorted(board.holes | self.alternate_holes)
        }

    def _panels(
        self, cassettes: dict[tuple[int, int], Cassette], standoffs: dict[MountingHole, tuple[float, float]]
    ) -> None:
        w, h, d, t = self.width, self.height, self.depth, WALL_THICKNESS
        e, f = EAR_THICKNESS, FLOOR_THICKNESS
        boss = STANDOFF_BOSS_DIAMETER / 2 + 2
        side_lines = sorted({y for c in cassettes.values() for y in (c.slot.y_left, c.slot.y_right)})
        # Floor/cover v runs from -w/2 (floor) or +w/2 (cover); keep seams off cassette side plates and bosses.
        fw = self.floor_width
        floor_keep_v = [(y - SIDE_THICKNESS - 4 + fw / 2, y + SIDE_THICKNESS + 4 + fw / 2) for y in side_lines]
        floor_keep_v += [(y + fw / 2 - boss, y + fw / 2 + boss) for _, y in standoffs.values()]
        floor_keep_u = [(x - e - boss, x - e + boss) for x, _ in standoffs.values()]
        inside = w / 2 - t
        cover_keep_v = [(inside - y - SIDE_THICKNESS - 4, inside - y + SIDE_THICKNESS + 4) for y in side_lines]
        self.floor = Panel(
            f"{self.name}_floor",
            d - e,
            fw,
            f,
            Frame(Vector(e, -fw / 2, 0), Vector(1, 0, 0), Vector(0, 0, 1)),
            self.bed,
            floor_keep_u,
            floor_keep_v,
            Vector(0, 0, -1),
        )
        # The side walls run the chassis's full height, so a corner can print upright in one piece with
        # its ear (one_piece); the cover sits between them.
        cover_frame = Frame(Vector(e, inside, h - COVER_RECESS), Vector(1, 0, 0), Vector(0, 0, -1))
        cover_bed = self.bed
        if self.toolless_cover:
            # Inner face down, so the dovetails' flanks rise from the bed; the tabs stand out past the edges.
            cover_frame = Frame(
                Vector(e, -inside, h - COVER_RECESS - COVER_THICKNESS), Vector(1, 0, 0), Vector(0, 0, 1)
            )
            cover_keep_v = [(2 * inside - b, 2 * inside - a) for a, b in cover_keep_v]
            cover_bed = replace(self.bed, margin=self.bed.margin + lid.TAB_REACH)
        self.cover = Panel(
            f"{self.name}_cover",
            d - e,
            w - 2 * t,
            COVER_THICKNESS,
            cover_frame,
            cover_bed,
            [],
            cover_keep_v,
            Vector(0, 0, 1),
        )
        # Stagger wall seams against floor and cover seams so every seam is bridged by a continuous panel.
        box_seams = self.floor.seams_u + self.cover.seams_u
        left_keep = [(s - SEAM_STAGGER, s + SEAM_STAGGER) for s in box_seams]
        right_keep = [(d - e - s - SEAM_STAGGER, d - e - s + SEAM_STAGGER) for s in box_seams]
        # A one-piece corner prints its ear (and a spring hook's housing) in front of the wall's first segment.
        reserve = 0.0
        if self.one_piece:
            reserve = e + (spring_housing_depth() if self.ear_style is EarStyle.SNAP else 0.0) + CORNER_RESERVE_MARGIN
        self.left_wall = Panel(
            f"{self.name}_left_wall",
            d - e,
            h - f,
            t,
            Frame(Vector(e, w / 2, f), Vector(1, 0, 0), Vector(0, -1, 0)),
            self.bed,
            left_keep,
            explode_direction=Vector(0, 1, 0),
            reserve_start=reserve,
        )
        self.right_wall = Panel(
            f"{self.name}_right_wall",
            d - e,
            h - f,
            t,
            Frame(Vector(d, -w / 2, f), Vector(-1, 0, 0), Vector(0, 1, 0)),
            self.bed,
            right_keep,
            explode_direction=Vector(0, -1, 0),
            reserve_end=reserve,
        )
        self.rear_wall = Panel(
            f"{self.name}_rear_wall",
            w - 2 * t,
            h - f - COVER_THICKNESS - COVER_RECESS,
            t,
            self._rear_frame(),
            self.bed,
            self._aperture_keepout(),
            explode_direction=Vector(1, 0, 0),
        )
        for panel in (self.floor, self.cover, self.left_wall, self.right_wall, self.rear_wall):
            self.add_child(panel)
        self._cut_aperture()

    def _rear_frame(self) -> Frame:
        """The rear wall prints outer face down, or inner face down in a tool-less box (its tenons and
        latch teeth then sit at its inner face)."""
        inside = self.width / 2 - WALL_THICKNESS
        if self.toolless_box:
            return Frame(
                Vector(self.depth - WALL_THICKNESS, -inside, FLOOR_THICKNESS), Vector(0, 1, 0), Vector(1, 0, 0)
            )
        return Frame(Vector(self.depth, inside, FLOOR_THICKNESS), Vector(0, -1, 0), Vector(-1, 0, 0))

    def _rear_u(self, y0: float, y1: float) -> tuple[float, float]:
        """A rack y range as a sorted u range on the rear wall."""
        inside = self.width / 2 - WALL_THICKNESS
        a, b = ((y + inside) if self.toolless_box else (inside - y) for y in (y0, y1))
        return min(a, b), max(a, b)

    def _aperture_span(self) -> tuple[float, float, float, float] | None:
        """The rear I/O aperture as (u0, v0, u1, v1) in the rear wall's frame, clipped to the wall."""
        if self.motherboard is None:
            return None
        board = self.motherboard
        near_y = board.width / 2 + self._board_shift() - board.hole_c_from_corner[0] - IO_APERTURE_OFFSET_FROM_C
        far_y = near_y - IO_APERTURE_WIDTH
        u0, u1 = self._rear_u(near_y, far_y)
        board_top = FLOOR_THICKNESS + STANDOFF_HEIGHT + BOARD_THICKNESS
        v0 = board_top - IO_APERTURE_BELOW_BOARD_TOP - FLOOR_THICKNESS
        v1 = min(v0 + IO_APERTURE_HEIGHT, self.inner_height)
        return u0, max(v0, 0.0), u1, v1

    def _aperture_keepout(self) -> list[tuple[float, float]]:
        span = self._aperture_span()
        keep = [] if span is None else [(span[0] - 4, span[2] + 4)]
        psu = self._psu_layout()
        if psu is not None:
            u0, u1 = self._rear_u(psu.y0, psu.y1)
            keep.append((u0 - 4, u1 + 4))
        return keep

    # Power supply -------------------------------------------------------------------------------------

    # Tool-less box -----------------------------------------------------------------------------------

    def _wall_tabs(self, wall: Panel) -> None:
        """Dovetail tabs along a side wall's bottom edge and their grooves in the floor; the wall slides
        back to lock, so each window is in front of its groove."""
        e = EAR_THICKNESS
        left = wall is self.left_wall
        edge_v = self.floor_width / 2 + (self.width / 2 if left else -self.width / 2)
        sign = -1.0 if left else 1.0
        x0 = e + lid.STATION_MARGIN + lid.SLIDE
        last = self.depth - WALL_THICKNESS - lid.TAB_LENGTH - lid.STATION_MARGIN
        placed = 0
        while x0 <= last:
            if self._wall_station(wall, x0, edge_v, sign):
                placed += 1
                x0 += lid.STATION_PITCH
            else:
                x0 += 1.0
        if placed < 2:
            raise ValueError(f"{self.name}: only {placed} floor dovetails fit under {wall.name}; it needs two")

    def _wall_station(self, wall: Panel, x0: float, edge_v: float, sign: float) -> bool:
        c, e, floor = lid.CLEARANCE, EAR_THICKNESS, self.floor
        us = sorted(wall.frame.to_local(Vector(x, 0, 0)).X for x in (x0, x0 + lid.TAB_LENGTH))
        mid = (us[0] + us[1]) / 2
        if wall.in_splice_zone(mid, wall.width / 2, lid.TAB_LENGTH / 2 + 1):
            return False
        found = wall.segment_at(mid, wall.width / 2, margin=lid.TAB_LENGTH / 2 + 1)
        if found is None:
            return False
        plate, lu, _ = found
        tab = lid.CoverTab(us[0] - mid + lu, us[1] - mid + lu, 0.0, -1.0)
        region, (low, high) = feature_extent(tab, plate)
        assert region is not None
        if plate.blocked((region[0], 0.0, region[2], region[3]), low, high):
            return False
        # The floor: the groove under the locked tab, the window under it one slide forward.
        lock = (x0 - c - e, x0 + lid.TAB_LENGTH + c - e)
        window = (lock[0] - lid.SLIDE, lock[0])
        span = (window[0], lock[1])
        probe_v = edge_v + sign * lid.TAB_TOP / 2
        half = (span[1] - span[0]) / 2
        if floor.in_splice_zone((span[0] + span[1]) / 2, probe_v, half):
            return False
        located = floor.segment_at((span[0] + span[1]) / 2, probe_v, margin=0.0)
        if located is None:
            return False
        fplate, fu, fv = located
        du, dv = fu - (span[0] + span[1]) / 2, fv - probe_v
        if not (span[0] + du > 0 and span[1] + du < fplate.length):
            return False
        socket = toolless.FloorSocket((lock[0] + du, lock[1] + du), (window[0] + du, window[1] + du), edge_v + dv, sign)
        fregion, (flow, fhigh) = feature_extent(socket, fplate)
        if fregion is None or fplate.blocked(fregion, flow, fhigh):
            return False
        plate.add(tab)
        fplate.add(socket)
        return True

    def _rear_wall_joints(self) -> None:
        """Tenons from the rear wall's bottom edge into floor pockets, and a sprung tooth at each end into
        the side walls."""
        rear, c = self.rear_wall, lid.CLEARANCE
        wall_x = self.depth - WALL_THICKNESS
        # Tenons: spread along the wall, each sliding to a clear spot.
        targets = edge_positions(rear.length, toolless.TENON_PITCH, toolless.TENON_LENGTH)
        placed = 0
        for target in targets:
            for offset in sorted(range(-40, 41), key=abs):
                u0 = target + offset - toolless.TENON_LENGTH / 2
                if self._rear_tenon(u0, wall_x):
                    placed += 1
                    break
        if placed < 2:
            raise ValueError(f"{self.name}: only {placed} rear wall tenons fit; it needs two")
        # Latches at both ends.
        height = rear.width
        v1 = height - toolless.REAR_TOOTH_TOP_MARGIN
        v0 = v1 - toolless.REAR_TOOTH_HEIGHT
        for edge_u, outward in ((0.0, -1.0), (rear.length, 1.0)):
            probe = edge_u - outward * 1.0
            found = rear.segment_at(probe, height / 2)
            assert found is not None
            plate, lu, _ = found
            du = lu - probe
            arm_inner = edge_u - outward * toolless.REAR_ARM_WIDTH
            relief = sorted((arm_inner, arm_inner - outward * toolless.REAR_ARM_RELIEF))
            plate.add(RectCut(relief[0] + du, toolless.REAR_ARM_ROOT, relief[1] + du, plate.width + 1))
            plate.add(toolless.SideTooth(edge_u + du, outward, v0, v1))
            # The pocket in the side wall the tooth springs into.
            y = rear.frame.to_rack(Vector(edge_u, 0, 0)).Y
            side = self.left_wall if y > 0 else self.right_wall
            x_range = (wall_x - c, wall_x + toolless.REAR_TOOTH_THICKNESS + c)
            us = sorted(side.frame.to_local(Vector(x, 0, 0)).X for x in x_range)
            mid = (us[0] + us[1]) / 2
            hit = side.segment_at(mid, side.width / 2)
            if hit is None or side.in_splice_zone(mid, side.width / 2, (us[1] - us[0]) / 2 + 1):
                raise ValueError(f"{self.name}: the rear latch's pocket lands on a seam of {side.name}")
            splate, su, _ = hit
            pocket = RectCut(us[0] - mid + su, v0 - c, us[1] - mid + su, v1 + c, toolless.REAR_TOOTH + c)
            sregion, (slow, shigh) = feature_extent(pocket, splate)
            if sregion is None or splate.blocked(sregion, slow, shigh):
                raise ValueError(f"{self.name}: no room for the rear latch's pocket in {side.name}")
            splate.add(pocket)

    def _rear_tenon(self, u0: float, wall_x: float) -> bool:
        rear, floor, c = self.rear_wall, self.floor, lid.CLEARANCE
        u1 = u0 + toolless.TENON_LENGTH
        mid = (u0 + u1) / 2
        if u0 < toolless.REAR_ARM_WIDTH + toolless.REAR_ARM_RELIEF + 4:
            return False
        if u1 > rear.length - toolless.REAR_ARM_WIDTH - toolless.REAR_ARM_RELIEF - 4:
            return False
        if rear.in_splice_zone(mid, rear.width / 2, toolless.TENON_LENGTH / 2 + 1):
            return False
        found = rear.segment_at(mid, rear.width / 2, margin=toolless.TENON_LENGTH / 2 + 1)
        if found is None:
            return False
        plate, lu, _ = found
        tenon = toolless.Tenon(u0 - mid + lu, u1 - mid + lu)
        if plate.blocked((tenon.u0, 0.0, tenon.u1, 2.0), 0.0, toolless.TENON_THICKNESS):
            return False
        ys = sorted(rear.frame.to_rack(Vector(u, 0, 0)).Y for u in (u0, u1))
        fu0 = wall_x - c - EAR_THICKNESS
        fu1 = wall_x + toolless.TENON_THICKNESS + c - EAR_THICKNESS
        fv0, fv1 = ys[0] - c + self.floor_width / 2, ys[1] + c + self.floor_width / 2
        located = floor.segment_at((fu0 + fu1) / 2, (fv0 + fv1) / 2, margin=0.0)
        if located is None or floor.in_splice_zone((fu0 + fu1) / 2, (fv0 + fv1) / 2, toolless.TENON_LENGTH / 2 + 1):
            return False
        fplate, fu, fv = located
        du, dv = fu - (fu0 + fu1) / 2, fv - (fv0 + fv1) / 2
        pocket = RectCut(fu0 + du, fv0 + dv, fu1 + du, fv1 + dv, toolless.TENON_REACH + c)
        fregion, (flow, fhigh) = feature_extent(pocket, fplate)
        if fregion is None or fplate.blocked(fregion, flow, fhigh) or fu1 + du > fplate.length:
            return False
        plate.add(tenon)
        fplate.add(pocket)
        return True

    # Tool-less cover ---------------------------------------------------------------------------------

    @property
    def _cover_floor_z(self) -> float:
        """The cover's inner face (rack z)."""
        return self.height - COVER_RECESS - COVER_THICKNESS

    def _cover_edges(self) -> list[tuple[Panel, float, float]]:
        """Each side: its wall, the cover's edge v and the outward direction in the cover's v."""
        width = self.cover.width
        return [(self.left_wall, width, 1.0), (self.right_wall, 0.0, -1.0)]

    def _wall_cut(self, wall: Panel, x0: float, x1: float, feature_at: Callable[[float, float], Feature]) -> bool:
        """Add a cut spanning rack x0..x1 above z0 to `wall`, given as `feature_at(u0, u1)` in the plate's u,
        if it stays clear of seams and the wall's other features."""
        us = sorted(wall.frame.to_local(Vector(x, 0, 0)).X for x in (x0, x1))
        # Walls are never split along their height (4U is under the bed's depth), so probe at mid-height.
        mid_u, mid_v = (us[0] + us[1]) / 2, wall.width / 2
        half = (us[1] - us[0]) / 2 + 1
        if wall.in_splice_zone(mid_u, mid_v, half):
            return False
        found = wall.segment_at(mid_u, mid_v, margin=half)
        if found is None:
            return False
        plate, lu, _ = found
        feature = feature_at(us[0] - mid_u + lu, us[1] - mid_u + lu)
        region, (low, high) = feature_extent(feature, plate)
        if region is None or plate.blocked(region, low, high):
            return False
        plate.add(feature)
        return True

    def _cover_latch(self) -> None:
        """The spring arm at the cover's rear left corner and the pocket its tooth springs into."""
        cover, z0 = self.cover, self._cover_floor_z
        wall, edge_v, outward = self._cover_edges()[0]
        tooth_x1 = self.depth - lid.TOOTH_FROM_END
        tooth_x0 = tooth_x1 - lid.TOOTH_LENGTH
        floor_v = z0 - FLOOR_THICKNESS
        c = lid.CLEARANCE
        if not self._wall_cut(wall, tooth_x0 - c, tooth_x1 + c, lambda a, b: lid.LatchPocket(a, b, floor_v)):
            raise ValueError(f"{self.name}: no room for the cover latch's pocket in {wall.name}")
        arm_u0 = cover.length - lid.LATCH_ARM
        arm_v = edge_v - outward * lid.LATCH_WIDTH
        relief_v = sorted((arm_v, arm_v - outward * lid.LATCH_RELIEF))
        reach = lid.LATCH_ARM / 2 + 1
        if cover.in_splice_zone(cover.length - reach, edge_v, reach):
            raise ValueError(f"{self.name}: the cover latch's arm lands on a cover seam")
        found = cover.segment_at(cover.length - lid.LATCH_ARM / 2, edge_v - outward * 1.0)
        assert found is not None
        plate, lu, lv = found
        du, dv = lu - (cover.length - lid.LATCH_ARM / 2), lv - (edge_v - outward * 1.0)
        plate.add(RectCut(arm_u0 + du, relief_v[0] + dv, cover.length + 1 + du, relief_v[1] + dv))
        t0, t1 = tooth_x0 - EAR_THICKNESS + du, tooth_x1 - EAR_THICKNESS + du
        plate.add(lid.LatchTooth(t0, t1, edge_v + dv, outward))

    def _cover_tabs(self) -> None:
        """Dovetail tabs along both cover edges, each with its groove and window in the wall."""
        floor_v = self._cover_floor_z - FLOOR_THICKNESS
        last = self.depth - lid.LATCH_ARM - lid.LATCH_RELIEF - 2 * lid.SLIDE - lid.STATION_MARGIN
        x0 = EAR_THICKNESS + lid.STATION_MARGIN
        placed = 0
        while x0 <= last:
            if self._cover_station(x0, floor_v):
                placed += 1
                x0 += lid.STATION_PITCH
            else:
                x0 += 1.0
        if placed < 2:
            raise ValueError(f"{self.name}: only {placed} tool-less cover stations fit; it needs two")

    def _cover_station(self, x0: float, floor_v: float) -> bool:
        """One tab pair at rack x0 (the tabs' front ends, locked), if both walls and the cover have room."""
        cover, c, e = self.cover, lid.CLEARANCE, EAR_THICKNESS
        u0, u1 = x0 - e, x0 - e + lid.TAB_LENGTH
        targets = []
        for wall, edge_v, outward in self._cover_edges():
            probe_v = edge_v - outward * 1.0
            if cover.in_splice_zone((u0 + u1) / 2, probe_v, lid.TAB_LENGTH / 2 + 1):
                return False
            found = cover.segment_at((u0 + u1) / 2, probe_v, margin=0.0)
            if found is None:
                return False
            plate, lu, lv = found
            du, dv = lu - (u0 + u1) / 2, lv - probe_v
            if not (u0 + du > 0 and u1 + du < plate.length):
                return False
            tab = lid.CoverTab(u0 + du, u1 + du, edge_v + dv, outward)
            region, (low, high) = feature_extent(tab, plate)
            assert region is not None
            inner = (region[0], max(region[1], 0.0), region[2], min(region[3], plate.width))
            if plate.blocked(inner, low, high):
                return False
            targets.append((wall, plate, tab))
        lock = (x0 - c, x0 + lid.TAB_LENGTH + c)
        window = (lock[1], lock[1] + lid.SLIDE)
        cuts: list[tuple[Panel, Plate, Feature]] = []
        for wall, _, _ in targets:
            us = sorted(wall.frame.to_local(Vector(x, 0, 0)).X for x in (lock[0], window[1]))
            mid_u, mid_v = (us[0] + us[1]) / 2, wall.width / 2
            half = (us[1] - us[0]) / 2 + 1
            if wall.in_splice_zone(mid_u, mid_v, half):
                return False
            found = wall.segment_at(mid_u, mid_v, margin=half)
            if found is None:
                return False
            plate, lu, _ = found

            def local(x: float, wall: Panel = wall, shift: float = lu - mid_u) -> float:
                return wall.frame.to_local(Vector(x, 0, 0)).X + shift

            socket = lid.TabSocket((local(lock[0]), local(lock[1])), (local(window[0]), local(window[1])), floor_v)
            region, (low, high) = feature_extent(socket, plate)
            if region is None or plate.blocked(region, low, high):
                return False
            cuts.append((wall, plate, socket))
        for _, plate, tab in targets:
            plate.add(tab)
        for _, plate, cut in cuts:
            plate.add(cut)
        return True

    def _psu_layout(self) -> PsuLayout | None:
        """Where the power supply sits: beside the board, at the left wall, flat if it fits, else on its side."""
        if not self.power_supply:
            return None
        board = self.motherboard.width if self.motherboard is not None else 0.0
        free = self.inner_width - board - 2 * PSU_MARGIN - PSU_RIB - PSU_CLEARANCE
        spec = ATX_PSU
        for across, tall, on_side in ((spec.width, spec.height, False), (spec.height, spec.width, True)):
            if across <= free and tall + PSU_CLEARANCE <= self.inner_height:
                y1 = self.inner_width / 2 - PSU_MARGIN - PSU_RIB
                return PsuLayout(y1 - across, y1, tall, on_side)
        raise ValueError(
            f"{self.name}: no room for an ATX power supply: {free:.0f} mm beside the board and "
            f"{self.inner_height:.0f} mm of height, against 150 x 86 (flat) or 86 x 150 (on its side)"
        )

    def _board_shift(self) -> float:
        """With a power supply, the board moves against the right wall to leave the left side free."""
        if not self.power_supply or self.motherboard is None:
            return 0.0
        return -(self.inner_width / 2 - PSU_MARGIN - self.motherboard.width / 2)

    def _psu_bay(self) -> None:
        psu = self._psu_layout()
        if psu is None:
            return
        spec = ATX_PSU
        reach = self.depth - WALL_THICKNESS - spec.lengths[1]
        deepest = max((c.x_back for c in self.children.values() if isinstance(c, Cassette)), default=0.0)
        if reach < deepest + SHELF_THICKNESS:
            raise ValueError(f"{self.name}: a {spec.lengths[1]:.0f} mm power supply reaches the front modules")

        def rear_uv(face_x: float, face_y: float) -> tuple[float, float]:
            # Viewed from behind, the face's x runs toward +y; on its side the face turns a quarter.
            x, y = (spec.height - face_y, face_x) if psu.on_side else (face_x, face_y)
            return self._rear_u(psu.y0 + x, psu.y0 + x)[0], y

        for hx, hy in spec.holes:
            u, v = rear_uv(hx, hy)
            found = self.rear_wall.segment_at(u, v)
            if found is None:
                raise ValueError(f"{self.name}: a power supply screw lands on a rear wall seam")
            plate, lu, lv = found
            plate.add(ThroughHole(lu, lv, spec.screw_clearance))
        # The opening for its fan and inlet, inside the screw holes.
        corners = [
            rear_uv(PSU_OPENING_INSET, PSU_OPENING_INSET + 6),
            rear_uv(spec.width - PSU_OPENING_INSET, spec.height - PSU_OPENING_INSET),
        ]
        us, vs = sorted(c[0] for c in corners), sorted(c[1] for c in corners)
        found = self.rear_wall.segment_at((us[0] + us[1]) / 2, (vs[0] + vs[1]) / 2)
        assert found is not None
        plate, lu, lv = found
        du, dv = (us[1] - us[0]) / 2, (vs[1] - vs[0]) / 2
        plate.add(RectCut(lu - du, lv - dv, lu + du, lv + dv))
        # Guide ribs on the floor along each side of the longest body, split around any floor seams.
        x0, x1 = self.depth - WALL_THICKNESS - spec.lengths[1], self.depth - WALL_THICKNESS
        for ya, yb in (
            (psu.y0 - PSU_CLEARANCE / 2 - PSU_RIB, psu.y0 - PSU_CLEARANCE / 2),
            (psu.y1 + PSU_CLEARANCE / 2, psu.y1 + PSU_CLEARANCE / 2 + PSU_RIB),
        ):
            self._floor_rib(x0, x1, ya, yb)

    def _floor_rib(self, x0: float, x1: float, y0: float, y1: float) -> None:
        floor = self.floor
        u0, u1 = x0 - EAR_THICKNESS, x1 - EAR_THICKNESS
        v0, v1 = y0 + self.floor_width / 2, y1 + self.floor_width / 2
        zone = floor.splice.zone
        for (i, j), plate in floor.segments.items():
            pu0, pu1 = floor.u_bounds[i], floor.u_bounds[i + 1]
            pv0, pv1 = floor.v_bounds[j], floor.v_bounds[j + 1]
            a = max(u0, pu0 + (zone if i > 0 else 0.0))
            b = min(u1, pu1 - (zone if i < len(floor.u_bounds) - 2 else 0.0))
            if (
                a >= b
                or v1 <= pv0 + (zone if j > 0 else 0.0)
                or v0 >= pv1 - (zone if j < len(floor.v_bounds) - 2 else 0.0)
            ):
                continue
            plate.add(Rib(a - pu0, v0 - pv0, b - pu0, v1 - pv0, PSU_RIB_HEIGHT))

    def _cut_aperture(self) -> None:
        span = self._aperture_span()
        if span is None:
            return
        u0, v0, u1, v1 = span
        for (i, j), plate in self.rear_wall.segments.items():
            pu, pv = self.rear_wall.u_bounds[i], self.rear_wall.v_bounds[j]
            cu0, cu1 = max(u0 - pu, -1.0), min(u1 - pu, plate.length + 1)
            cv0, cv1 = max(v0 - pv, -1.0), min(v1 - pv, plate.width + 1)
            if cu0 < cu1 and cv0 < cv1:
                plate.add(RectCut(cu0, cv0, cu1, cv1))

    def _rear_corner_joints(self) -> Hardware:
        hardware = edge_joint(self.left_wall, self.rear_wall, Edge.U0)
        hardware.items += edge_joint(self.right_wall, self.rear_wall, Edge.U1).items
        return hardware

    def _floor_cover_joints(self) -> Hardware:
        hardware = Hardware([])
        if self.toolless_box:
            for wall in (self.left_wall, self.right_wall):
                self._wall_tabs(wall)
            self._rear_wall_joints()
            self._cover_tabs()
            return hardware
        for wall in (self.left_wall, self.right_wall, self.rear_wall):
            # An I/O aperture can take most of a narrow rear wall; its corners then carry the joint.
            minimum = 1 if wall is self.rear_wall and self.motherboard is not None else None
            hardware.items += edge_joint(self.floor, wall, Edge.V0, minimum=minimum).items
        if self.toolless_cover:
            self._cover_tabs()
            return hardware
        # The cover sits on the rear wall and between the side walls, which screw into its edges.
        hardware.items += edge_joint(self.cover, self.rear_wall, Edge.V1, minimum=1 if self.motherboard else None).items
        # The cover is as thin as the floor (a 1U row must still take a 3.5 in sled): captive nuts, not inserts.
        nut = LapFastening.NUT
        hardware.items += edge_joint(self.left_wall, self.cover, Edge.V0, fastening=nut).items
        hardware.items += edge_joint(self.right_wall, self.cover, Edge.V1, fastening=nut).items
        return hardware

    def _cassette_joints(self, cassettes: dict[tuple[int, int], Cassette]) -> Hardware:
        # Side laps have the least room (above the sled grooves), so they go first and the
        # floor/shelf/cover stations slide clear of them.
        hardware = self._side_laps(cassettes)
        shelves_by_row: dict[int, list[Plate]] = {}
        for (row, _), cassette in cassettes.items():
            if cassette.shelf is not None:
                top = row + cassette.kind.rows - 1
                shelves_by_row.setdefault(top, []).append(cassette.shelf)
        for (row, _), cassette in cassettes.items():
            below: Panel | list[Panel | Plate]
            below = self.floor if row == 0 else list(shelves_by_row.get(row - 1, []))
            above: Panel | Plate = self.cover if cassette.shelf is None else cassette.shelf
            for plate in (cassette.left, cassette.right):
                hardware.items += edge_joint(below, plate, Edge.V0).items
                # A tool-less cover lifts off: the top row is held by its floor joints and side laps.
                if not (self.toolless_cover and above is self.cover):
                    hardware.items += edge_joint(above, plate, Edge.V1, _offset_stations(plate.length)).items
        return hardware

    def _lap_z(self, *cassettes: Cassette) -> float | None:
        """Lap screw height above every sled groove on the shared face, or None when grooves fill the face.

        Bays stacked with several sled levels are grooved nearly to their top; they stay anchored by
        their floor, shelf and cover joints instead.
        """
        first = cassettes[0].slot
        groove = max(c.kind.groove_top(c.slot.row_height) for c in cassettes)
        lowest = first.z_bottom + groove + LAP_GROOVE_CLEARANCE
        highest = first.z_bottom + first.row_height - LAP_TOP_CLEARANCE
        if lowest > highest:
            return None
        return min(max(lowest, first.z_bottom + first.row_height / 2), highest)

    def _place_laps(
        self,
        resolve: Callable[[Vector], Plate | None],
        side: Plate,
        y: float,
        z: float,
        x_from: float,
        x_to: float,
        fastening: LapFastening,
    ) -> Hardware:
        """Up to LAP_COUNT lap screws along a shared face, each slid to the nearest clear spot."""
        hardware = Hardware([])
        chosen: list[float] = []
        span = x_to - x_from
        for k in range(LAP_COUNT):
            target = x_from + span * (k + 0.5) / LAP_COUNT
            for offset in sorted(range(-int(span / 2), int(span / 2) + 1), key=abs):
                x = target + offset
                if not x_from < x < x_to or any(abs(x - c) < LAP_MIN_SPACING for c in chosen):
                    continue
                point = Vector(x, y, z)
                a = resolve(point)
                if a is None:
                    continue
                made = lap_joint(a, side, [point], fastening, minimum=0)
                if made.items:
                    hardware.items += made.items
                    chosen.append(x)
                    break
        if not chosen:
            raise ValueError(f"No clear spot to bolt {side.name} along x {x_from:.1f}-{x_to:.1f}")
        return hardware

    def _side_laps(self, cassettes: dict[tuple[int, int], Cassette]) -> Hardware:
        """Bolt neighbouring cassettes together, and the outer ones to the walls."""
        hardware = Hardware([])
        for cassette in cassettes.values():
            record = cassette.slot
            x0, x1 = max(cassette.x_front, EAR_THICKNESS), cassette.x_back
            z = self._lap_z(cassette)
            if z is not None and record.column == 0:
                hardware.items += self._place_laps(
                    _wall_resolver(self.left_wall), cassette.left, record.y_left, z, x0, x1, LapFastening.INSERT
                ).items
            if z is not None and record.column + record.columns == GRID_COLUMNS:
                hardware.items += self._place_laps(
                    _wall_resolver(self.right_wall), cassette.right, record.y_right, z, x0, x1, LapFastening.INSERT
                ).items
            neighbour = cassettes.get((record.row, record.column + record.columns))
            shared_z = None if neighbour is None else self._lap_z(cassette, neighbour)
            if neighbour is not None and shared_z is not None:
                lo, hi = max(x0, neighbour.x_front), min(x1, neighbour.x_back)
                hardware.items += self._place_laps(
                    _always(cassette.right), neighbour.left, record.y_right, shared_z, lo, hi, LapFastening.NUT
                ).items
        return hardware

    def _board(self, standoffs: dict[MountingHole, tuple[float, float]]) -> None:
        for x, y in standoffs.values():
            u, v = x - EAR_THICKNESS, y + self.floor_width / 2
            located = self.floor.segment_at(u, v, STANDOFF_BOSS_DIAMETER / 2)
            if located is None:
                raise ValueError(f"Standoff at ({x:.1f}, {y:.1f}) lands on a floor seam")
            plate, lu, lv = located
            plate.add(Boss(lu, lv, STANDOFF_BOSS_DIAMETER, STANDOFF_HEIGHT))
            plate.add(BossPocket(lu, lv, INSERT_M3_LONG.bore_diameter, INSERT_M3_LONG.length, STANDOFF_HEIGHT))

    def _ears(self) -> Hardware:
        hardware = Hardware([])
        p, w, t, e = self.rack.panel_width, self.width, WALL_THICKNESS, EAR_THICKNESS
        ear_length = p / 2 - (w / 2 - t)
        hole_u = self.rack.hole_spacing / 2 - (w / 2 - t)
        # Square-hole ears and one-piece corners print upright (see hooks), screw ears flat.
        upright = self.ear_style is not EarStyle.SCREW or self.one_piece
        holes = [
            (u, index, u * RACK_UNIT + offset - PANEL_HEIGHT_DEDUCTION / 2)
            for u in range(self.units)
            for index, offset in enumerate(U_HOLE_OFFSETS)
        ]
        # The spring hook stands on the bed at the chassis's top edge: the top U's top hole.
        spring_hole = (self.units - 1, len(U_HOLE_OFFSETS) - 1)
        for side, origin, wall, edge in (
            ("left", Vector(0, w / 2 - t, 0), self.left_wall, Edge.U0),
            ("right", Vector(0, -p / 2, 0), self.right_wall, Edge.U1),
        ):
            ear = Plate(
                f"{self.name}_{side}_ear",
                ear_length,
                self.height,
                e,
                Frame(origin, Vector(0, 1, 0), Vector(1, 0, 0)),
                Vector(-1, 0, 0),
                print_up=UPRIGHT if upright else None,
            )
            # Printed with sparse infill the ears fall below twice their two-post load (fea, infill).
            ear.print_settings = SOLID
            u = hole_u if side == "left" else ear_length - hole_u
            out = 1.0 if side == "left" else -1.0
            half = hook_width(self.rack) / 2
            band = (u - half, u + half)
            for unit, index, z in holes:
                match self.ear_style:
                    case EarStyle.SNAP if (unit, index) == spring_hole:
                        ear.add(SpringHook(band, z, out))
                        ear.add(SpringHookCut(band, z, out))
                    case EarStyle.SNAP:
                        ear.add(RackPeg(band, z))
                    case EarStyle.HOOK if index in HOOK_HOLES_PER_UNIT:
                        ear.add(RackHook(band, z))
                    case EarStyle.SCREW if index in EAR_HOLES_PER_UNIT:
                        ear.add(Slot(u, z, RACK_SCREW_CLEARANCE, 2 * self.rack.hole_spacing_tolerance))
            self.add_child(ear)
            if self.one_piece:
                self._merge_corner(ear, wall, edge)
            else:
                hardware.items += edge_joint(ear, wall, edge).items
            if self.knee_brace_units is not None:
                self._knee_brace(side, wall, edge)
            if self.rear_support is not None:
                self._rear_support(side, wall)
            if self.web_clamp is not None:
                self._web_clamp(side, wall)
        return hardware

    def _place_fans(self, panel: Panel, sizes: tuple[int, ...], from_end: bool) -> None:
        """Each fan's grille at the first spot (from one end of the panel) clear of seams and every feature."""
        for size in sizes:
            half = fan_room(size) / 2
            if panel.width < 2 * half:
                raise ValueError(f"A {size} mm fan doesn't fit the {panel.width:.0f} mm {panel.name}")
            us = [half + k for k in range(int(panel.length - 2 * half) + 1)]
            vs = sorted(
                (half + k for k in range(int(panel.width - 2 * half) + 1)), key=lambda v: abs(v - panel.width / 2)
            )
            for u in reversed(us) if from_end else us:
                placed = False
                for v in vs:
                    if panel.in_splice_zone(u, v, half):
                        continue
                    found = panel.segment_at(u, v, margin=half)
                    if found is None:
                        continue
                    plate, lu, lv = found
                    if plate.blocked((lu - half, lv - half, lu + half, lv + half), -1.0, plate.thickness + 1):
                        continue
                    plate.add(FanGrille(lu, lv, size))
                    placed = True
                    break
                if placed:
                    break
            else:
                raise ValueError(
                    f"No room for a {size} mm fan in {panel.name}: a grille may not cross a seam, and its "
                    f"bed-sized segments are {_segment_sizes(panel)} (for bigger fans see fans.FanPlate)"
                )

    def _web_clamp(self, side: str, wall: Panel) -> None:
        assert self.web_clamp is not None
        sign = 1.0 if side == "left" else -1.0
        clamp = WebClamp(
            f"{self.name}_{side}_web_clamp",
            sign,
            sign * self.width / 2,
            sign * self.rack.opening / 2,
            EAR_THICKNESS,
            FLOOR_THICKNESS,
            self.height - REAR_TOP_MARGIN,
            self.web_clamp,
        )
        clamp_pocket(wall, clamp.rear_x - WEB_PLATE_THICKNESS / 2, FLOOR_THICKNESS)
        self.add_child(clamp)

    def _rear_support(self, side: str, wall: Panel) -> None:
        assert self.rear_support is not None
        shortest, longest = self.rear_support
        if longest < shortest:
            raise ValueError(f"Rear support range {self.rear_support} runs backwards")
        sign = 1.0 if side == "left" else -1.0
        back = self.depth - REAR_TONGUE_INSET
        layout = RearLayout(
            sign,
            sign * self.width / 2,
            sign * self.rack.hole_spacing / 2,
            FLOOR_THICKNESS,
            self.height - REAR_TOP_MARGIN,
            (back - TONGUE_SPACING, back),
            (EAR_THICKNESS + shortest, EAR_THICKNESS + longest),
        )
        layout.check()
        pockets_for(wall, layout)
        self.add_child(RearArm(f"{self.name}_{side}_rear_arm_front", layout, rear=False))
        self.add_child(RearArm(f"{self.name}_{side}_rear_arm_rear", layout, rear=True))
        self.add_child(RearPin(f"{self.name}_{side}_rear_pin", layout))

    def _knee_brace(self, side: str, wall: Panel, edge: Edge) -> None:
        if self.knee_brace_units not in (1, 2):
            raise ValueError(f"Knee braces anchor 1 or 2 units below, not {self.knee_brace_units}")
        bounds = wall.u_bounds
        front = bounds[1] - bounds[0] if edge is Edge.U0 else bounds[-1] - bounds[-2]
        socket_x = EAR_THICKNESS + KNEE_DEPTH_FRACTION * front
        socket_for(wall, socket_x, FLOOR_THICKNESS)
        sign = 1.0 if side == "left" else -1.0
        self.add_child(
            KneeBrace(
                f"{self.name}_{side}_knee_brace",
                sign,
                sign * self.width / 2,
                sign * self.rack.hole_spacing / 2,
                EAR_THICKNESS,
                socket_x,
                FLOOR_THICKNESS,
                self.knee_brace_units,
                self.wall_inset,
            )
        )

    def _merge_corner(self, ear: Plate, wall: Panel, edge: Edge) -> None:
        """Print the ear and the front segment of its side wall as one upright piece: no joint between them."""
        columns = sorted({i for i, _ in wall.segments})
        front = columns[0] if edge is Edge.U0 else columns[-1]
        segments = [plate for (i, _), plate in wall.segments.items() if i == front]
        if len(segments) != 1:
            raise ValueError(f"{wall.name} is split in height, so its ear can't print as one piece with it")
        segment = segments[0]
        up = segment.frame.direction_to_local(Vector(0, 0, -1))
        segment.set_print_up(up)
        segment.merge(ear)
        segment.print_settings = SOLID


def _segment_sizes(panel: Panel) -> str:
    sizes = {(round(p.length), round(p.width)) for p in panel.segments.values()}
    return ", ".join(f"{a} x {b}" for a, b in sorted(sizes)) + " mm"


def _offset_stations(span: float) -> list[float]:
    """Top-edge stations, offset half a pitch from the bottom-edge ones so screws from above and below never meet."""
    base = edge_positions(span)
    half = (base[1] - base[0]) / 2
    shifted = [p + half for p in base[:-1]]
    return [p for p in shifted if EDGE_JOINT_END_MARGIN <= p <= span - EDGE_JOINT_END_MARGIN] or base


def _always(plate: Plate) -> Callable[[Vector], Plate | None]:
    """A resolver for a lap whose first plate is fixed (a neighbouring cassette's side)."""

    def resolve(_point: Vector) -> Plate | None:
        return plate

    return resolve


def _wall_resolver(wall: Panel) -> Callable[[Vector], Plate | None]:
    """The wall segment a lap screw at a rack point would pass through, or None on a seam."""

    def resolve(point: Vector) -> Plate | None:
        local = wall.frame.to_local(point)
        if wall.in_splice_zone(local.X, local.Y, 4):
            return None
        found = wall.segment_at(local.X, local.Y, margin=6)
        return None if found is None else found[0]

    return resolve
