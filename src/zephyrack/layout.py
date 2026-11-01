# SPDX-License-Identifier: AGPL-3.0-or-later
"""Panels larger than the printer bed, split into plates joined by flush splices.

A panel is one logical flat surface (a floor, a wall). It is cut into segment
plates that each fit the bed. Neighbouring segments are joined by a splice strip
that sits in a rebate across the seam on the inner face, so both faces of the
panel stay flush. Countersunk screws pass down through the strip into heat-set
inserts in the segments, so seam loads travel along the layers of strip and
segment alike.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from build123d import Part, Vector

from .component import Component
from .fasteners import INSERT_M3_SHORT, M3_CLEARANCE, M3_COUNTERSINK_DIAMETER, screw_length
from .plate import Face, Frame, Plate, RectCut, ThroughHole, TopPocket


@dataclass(frozen=True)
class Bed:
    """The usable print area. Defaults are a Prusa MK3S/MK3S+ (250 x 210 x 210) less a margin."""

    x: float = 250.0
    y: float = 210.0
    z: float = 210.0
    margin: float = 5.0

    @property
    def usable_x(self) -> float:
        return self.x - 2 * self.margin

    @property
    def usable_y(self) -> float:
        return self.y - 2 * self.margin

    def fits(self, size: tuple[float, float, float]) -> bool:
        a, b, h = size
        flat_fits = (a <= self.usable_x and b <= self.usable_y) or (a <= self.usable_y and b <= self.usable_x)
        return flat_fits and h <= self.z


MK3S_BED = Bed()


@dataclass(frozen=True)
class SpliceSpec:
    width: float = 24.0
    thickness: float = 2.5
    clearance: float = 0.2
    screw_pitch: float = 35.0
    end_margin: float = 11.0
    """Strip ends stop this far from the panel or segment edge, clear of edge-insert reliefs (9.7 deep)."""
    min_run: float = 7.0
    """Shortest strip that still seats one countersunk screw."""

    @property
    def zone(self) -> float:
        """Half-width of the band around a seam that nothing else may use."""
        return self.width / 2 + self.clearance + 2.0


SPLICE = SpliceSpec()


EXTRA_SEGMENTS_TO_TRY = 3


def plan_seams(
    length: float,
    max_segment: float,
    keepouts: list[tuple[float, float]],
    zone: float,
    min_segment: float = 30.0,
) -> list[float]:
    """Seam positions that cut `length` into segments no longer than `max_segment`.

    A seam's band (position +/- zone) may not overlap any keepout interval. Seams start
    evenly spaced and slide to the nearest free position; if the keepouts leave no room,
    one more segment is tried, up to EXTRA_SEGMENTS_TO_TRY more.
    """
    if length <= max_segment:
        return []
    fewest = math.ceil(length / max_segment)
    for count in range(fewest, fewest + EXTRA_SEGMENTS_TO_TRY + 1):
        seams = _seams_for(length, max_segment, keepouts, zone, min_segment, count)
        if seams is not None:
            return seams
    raise ValueError(f"No seam layout clears the keepouts in a {length:.1f} mm panel")


SEAM_SEARCH_STEP = 0.5


def _seams_for(
    length: float,
    max_segment: float,
    keepouts: list[tuple[float, float]],
    zone: float,
    min_segment: float,
    count: int,
) -> list[float] | None:
    def free(position: float) -> bool:
        return all(position + zone <= a or position - zone >= b for a, b in keepouts)

    seams: list[float] = []
    previous = 0.0
    for index in range(1, count):
        ideal = length * index / count
        candidates = sorted(
            (
                ideal + sign * offset * SEAM_SEARCH_STEP
                for offset in range(int(max_segment / SEAM_SEARCH_STEP))
                for sign in (1, -1)
            ),
            key=lambda p: abs(p - ideal),
        )
        chosen = next(
            (
                p
                for p in candidates
                if free(p) and min_segment <= p - previous <= max_segment and p <= length - min_segment
            ),
            None,
        )
        if chosen is None:
            return None
        seams.append(chosen)
        previous = chosen
    return seams if length - previous <= max_segment else None


@dataclass
class Panel(Component):
    """A logical flat surface, split into bed-sized segment plates joined by flush splices."""

    name: str
    length: float
    width: float
    thickness: float
    frame: Frame
    bed: Bed = MK3S_BED
    keepouts_u: list[tuple[float, float]] = field(default_factory=list)
    keepouts_v: list[tuple[float, float]] = field(default_factory=list)
    explode_direction: Vector = field(default_factory=lambda: Vector(0, 0, 0))
    splice: SpliceSpec = SPLICE

    def __post_init__(self) -> None:
        Component.__init__(self, self.name)
        portrait = (self.bed.usable_x, self.bed.usable_y)
        landscape = (self.bed.usable_y, self.bed.usable_x)
        best = min(
            (portrait, landscape),
            key=lambda m: math.ceil(self.length / m[0]) * math.ceil(self.width / m[1]),
        )
        self.seams_u = plan_seams(self.length, best[0], self.keepouts_u, self.splice.zone)
        self.seams_v = plan_seams(self.width, best[1], self.keepouts_v, self.splice.zone)
        self.u_bounds = [0.0, *self.seams_u, self.length]
        self.v_bounds = [0.0, *self.seams_v, self.width]
        self.segments: dict[tuple[int, int], Plate] = {}
        for i in range(len(self.u_bounds) - 1):
            for j in range(len(self.v_bounds) - 1):
                u0, u1 = self.u_bounds[i], self.u_bounds[i + 1]
                v0, v1 = self.v_bounds[j], self.v_bounds[j + 1]
                frame = Frame(self.frame.to_rack(Vector(u0, v0, 0)), self.frame.u, self.frame.w)
                suffix = "" if len(self.u_bounds) == 2 and len(self.v_bounds) == 2 else f"_{i}{j}"
                plate = Plate(f"{self.name}{suffix}", u1 - u0, v1 - v0, self.thickness, frame, self.explode_direction)
                self.segments[(i, j)] = plate
                self.add_child(plate)
        self.splice_plates: list[Plate] = []
        self.screws: list[str] = []
        self._splice()

    def solids(self) -> dict[str, Part]:
        return {}

    def segment_at(self, u: float, v: float, margin: float = 0.0) -> tuple[Plate, float, float] | None:
        """The segment containing logical (u, v) at least `margin` from its edges, and the local point."""
        for (i, j), plate in self.segments.items():
            lu, lv = u - self.u_bounds[i], v - self.v_bounds[j]
            if plate.contains(lu, lv, margin):
                return plate, lu, lv
        return None

    def in_splice_zone(self, u: float, v: float, clearance: float) -> bool:
        reach = self.splice.zone + clearance
        return any(abs(u - s) < reach for s in self.seams_u) or any(abs(v - s) < reach for s in self.seams_v)

    def _splice(self) -> None:
        for i in range(len(self.seams_u)):
            for j in range(len(self.v_bounds) - 1):
                self._join(self.segments[(i, j)], self.segments[(i + 1, j)], along_u=True, index=(i, j))
        for j in range(len(self.seams_v)):
            for i in range(len(self.u_bounds) - 1):
                self._join(self.segments[(i, j)], self.segments[(i, j + 1)], along_u=False, index=(i, j))

    def _join(self, low: Plate, high: Plate, along_u: bool, index: tuple[int, int]) -> None:
        """Splice `low` to `high` across their shared seam with a flush strip.

        along_u: the seam is a line of constant u and the strip runs along v. A strip end
        that meets a crossing seam stops clear of that seam's whole band.
        """
        s = self.splice
        i, j = index
        half = s.width / 2 + s.clearance
        depth = s.thickness
        if self.thickness - depth < INSERT_M3_SHORT.length:
            raise ValueError(f"{self.name}: {self.thickness} mm is too thin for a flush splice")
        if along_u:
            span, crossing_before, crossing_after = low.width, j > 0, j + 1 < len(self.v_bounds) - 1
        else:
            span, crossing_before, crossing_after = low.length, i > 0, i + 1 < len(self.u_bounds) - 1
        start = s.zone if crossing_before else s.end_margin
        end = s.zone if crossing_after else s.end_margin
        run = span - start - end
        if run < s.min_run:
            raise ValueError(f"{self.name}: segment too narrow to splice")
        if run < s.screw_pitch:
            stations = [start + run / 2]
        else:
            count = math.floor(run / s.screw_pitch) + 1
            stations = [start + run * k / (count - 1) for k in range(count)]

        def place(along: float, across: float, plate: Plate) -> tuple[float, float]:
            """(along the seam, across it from the seam line) -> plate (u, v)."""
            if along_u:
                return (plate.length + across, along) if plate is low else (across, along)
            return (along, plate.width + across) if plate is low else (along, across)

        def rect(plate: Plate, sign: int) -> RectCut:
            (u0, v0), (u1, v1) = place(start - 1, 0.0, plate), place(span - end + 1, sign * half, plate)
            return RectCut(min(u0, u1), min(v0, v1), max(u0, u1), max(v0, v1), depth)

        low.add(rect(low, -1))
        high.add(rect(high, 1))
        corner_u, corner_v = place(start - 0.5, -s.width / 2, low)
        origin = low.frame.to_rack(Vector(corner_u, corner_v, self.thickness - depth))
        strip_size = (s.width, run + 1) if along_u else (run + 1, s.width)
        strip = Plate(
            f"{self.name}_splice_{'u' if along_u else 'v'}{i}{j}",
            *strip_size,
            depth - 0.1,
            Frame(origin, self.frame.u, self.frame.w),
            self.explode_direction,
        )
        for station in stations:
            for sign, plate in ((-1, low), (1, high)):
                pu, pv = place(station, sign * s.width / 4, plate)
                plate.add(TopPocket(pu, pv, INSERT_M3_SHORT.bore_diameter, 0, through=True))
                across = s.width / 2 + sign * s.width / 4
                along = station - start + 0.5
                su, sv = (across, along) if along_u else (along, across)
                strip.add(ThroughHole(su, sv, M3_CLEARANCE, Face.TOP, M3_COUNTERSINK_DIAMETER))
        self.splice_plates.append(strip)
        self.add_child(strip)
        length = screw_length(strip.thickness, INSERT_M3_SHORT.length, low.thickness - depth)
        self.screws += [f"M3x{length} countersunk (ISO 10642)", INSERT_M3_SHORT.name] * (2 * len(stations))
