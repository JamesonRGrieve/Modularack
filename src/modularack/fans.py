# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fan grilles: a honeycomb over a fan's swept area and the holes to screw it on, for any spare fan.

`FanGrille` cuts a plate printed flat: every honeycomb cell is a vertical hexagonal prism, so it prints
without supports and the webs between cells run in the plate's plane. `FanBay` is a front module whose
face carries one; `RackChassis(rear_fans=..., cover_fans=...)` puts them in the rear wall and the cover.
Sizes and screw patterns are in `standards.FANS`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Circle, Cylinder, HexLocations, Part, Pos, RegularPolygon, Sketch, Vector, extrude

from .cassette import SIDE_THICKNESS, VENT_MARGIN, Blank
from .component import Component
from .layout import MK3S_BED, Bed
from .plate import Feature, Frame, Plate
from .standards import FAN_SCREW_CLEARANCE, FANS, FanSize

CELL = 6.0
"""Honeycomb cell, across its flats."""
WEB = 1.35
"""Between cells: three 0.45 mm lines."""
FAN_MARGIN = 2.0
"""Plastic kept round the frame's outline where other features compete for room (rear wall, cover)."""
FACE_MARGIN = 1.0
"""A front fan bay's face only has to cover the frame behind it."""


def fan(size: int) -> FanSize:
    if size not in FANS:
        raise ValueError(f"No {size} mm fan; sizes are {sorted(FANS)}")
    return FANS[size]


@dataclass
class FanGrille(Feature):
    """A fan's honeycomb and screw holes, centred at (u, v) on a flat-printed plate."""

    u: float
    v: float
    size: int

    def shape(self, plate: Plate) -> Part:
        if plate.print_up is not None:
            raise ValueError(f"{plate.name}: fan grilles go in plates printed flat")
        spec, t = fan(self.size), plate.thickness
        radius = spec.blade_diameter / 2
        pitch = CELL + WEB
        # HexLocations takes the circumradius of the packing hexagon: flats = pitch.
        count = 2 * math.ceil(radius / pitch) + 2
        cells = Sketch() + [
            loc * RegularPolygon(CELL / math.sqrt(3), 6, major_radius=True)
            for loc in HexLocations(pitch / math.sqrt(3), count, count)
        ]
        honeycomb = cells & Circle(radius)
        grille = Pos(self.u, self.v, -1) * extrude(honeycomb, amount=t + 2)
        for spacing in spec.spacings:
            for du in (-spacing / 2, spacing / 2):
                for dv in (-spacing / 2, spacing / 2):
                    hole = Cylinder((FAN_SCREW_CLEARANCE + spec.tolerance) / 2, t + 2)
                    grille += Pos(self.u + du, self.v + dv, t / 2) * hole
        return grille

    def extent(self, plate: Plate) -> tuple[tuple[float, float, float, float] | None, tuple[float, float]]:
        half = fan(self.size).frame / 2 + FAN_MARGIN
        return (self.u - half, self.v - half, self.u + half, self.v + half), (-1.0, plate.thickness + 1)


def needs(size: int) -> float:
    """Room (square) a fan's grille takes on a plate."""
    return fan(size).frame + 2 * FAN_MARGIN


@dataclass
class FanBay(Blank):
    """A front module whose face carries a fan grille; the fan screws on behind it."""

    size: int = 80

    def min_width(self) -> float:
        return max(self.width, needs(self.size) + 2 * (SIDE_THICKNESS + VENT_MARGIN))

    def decorate(self, face: Plate) -> None:
        # The fan sits behind the face, so the face need only cover its frame with FACE_MARGIN to spare.
        tall = fan(self.size).frame + 2 * FACE_MARGIN
        if face.width < tall:
            raise ValueError(f"A {self.size} mm fan needs a {tall:.1f} mm tall face; this one is {face.width:.1f}")
        face.add(FanGrille(face.length / 2, face.width / 2, self.size))


class FanPlate(Component):
    """A free-standing grille plate for one or more fans, packed in rows (largest first), each fan with its
    own honeycomb and screw holes. Refused if the fans don't fit the bed. It guards fans too big for any of a
    chassis's bed-sized panel segments (a 200 mm grille needs about 232 mm of segment, clear of seam bands),
    or any set of spare fans screwed to one plate."""

    def __init__(self, name: str, sizes: int | tuple[int, ...], thickness: float = 3.0, bed: Bed = MK3S_BED) -> None:
        super().__init__(name)
        self.sizes = (sizes,) if isinstance(sizes, int) else tuple(sizes)
        if not self.sizes:
            raise ValueError(f"{name}: no fans")
        placed, length, width = _pack(self.sizes, bed)
        self.plate = Plate(name, length, width, thickness, Frame(Vector(0, 0, 0), Vector(1, 0, 0), Vector(0, 0, 1)))
        for size, u, v in placed:
            self.plate.add(FanGrille(u, v, size))

    def solids(self) -> dict[str, Part]:
        return self.plate.solids()


PLATE_GAP = 2.0
"""Between neighbouring fans' frames on a FanPlate."""


def _pack(sizes: tuple[int, ...], bed: Bed) -> tuple[list[tuple[int, float, float]], float, float]:
    """Guillotine-pack square fans (largest first) on the bed: each goes in the free rectangle it fits most
    snugly, which is then split along its shorter leftover. Returns (size, u, v) centres and the plate size."""
    limit_u, limit_v = max(bed.usable_x, bed.usable_y), min(bed.usable_x, bed.usable_y)
    free: list[tuple[float, float, float, float]] = [(0.0, 0.0, limit_u + PLATE_GAP, limit_v + PLATE_GAP)]
    placed: list[tuple[int, float, float]] = []
    for size in sorted(sizes, key=lambda s: -fan(s).frame):
        cell = fan(size).frame + PLATE_GAP
        fits = [r for r in free if r[2] >= cell - 1e-9 and r[3] >= cell - 1e-9]
        if not fits:
            raise ValueError(f"Fans {sizes} don't fit one plate: the bed takes {limit_u:.0f} x {limit_v:.0f}")
        u, v, w, h = min(fits, key=lambda r: (min(r[2] - cell, r[3] - cell), r[1], r[0]))
        free.remove((u, v, w, h))
        placed.append((size, u + cell / 2 - PLATE_GAP / 2, v + cell / 2 - PLATE_GAP / 2))
        # Split the leftover L into two rectangles, cutting along the shorter leftover side.
        if w - cell < h - cell:
            free += [(u + cell, v, w - cell, cell), (u, v + cell, w, h - cell)]
        else:
            free += [(u + cell, v, w - cell, h), (u, v + cell, cell, h - cell)]
        free = [r for r in free if r[2] > 0 and r[3] > 0]
    length = max(u + fan(s).frame / 2 for s, u, _ in placed)
    width = max(v + fan(s).frame / 2 for s, _, v in placed)
    return placed, length, width
