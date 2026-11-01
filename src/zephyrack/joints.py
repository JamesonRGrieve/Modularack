# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detachable joints between plates, placed from the plates' real positions.

Edge joint (an L or T corner): plate B's edge butts against a face of plate A. A
heat-set insert sits in B's edge, running in B's plane; a countersunk screw passes
through A into it. The insert pulls along B's layers and the screw bears on A
along A's layers, so neither part is loaded across its layers.

Lap joint: two plates face to face, screwed through both, into a captive nut or a
heat-set insert in the second plate.

Holes on both sides of a joint come from one point in the rack frame, so they line
up by construction; a joint whose plates don't actually meet raises.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from build123d import Vector

from .fasteners import (
    EDGE_INSERT,
    EDGE_INSERT_MIN_THICKNESS,
    EDGE_INSERT_RELIEF_DEPTH,
    INSERT_M3_LONG,
    M3_CLEARANCE,
    M3_COUNTERSINK_DIAMETER,
    M3_NUT_ACROSS_CORNERS,
    M3_NUT_HEIGHT,
    M3_NUT_POCKET_CLEARANCE,
    STANDARD_SCREW_LENGTHS,
    screw_length,
)
from .layout import Panel
from .plate import Edge, EdgeInsert, Face, HexPocket, Plate, ThroughHole, TopPocket, feature_extent

CONTACT_TOLERANCE = 1e-3
EDGE_JOINT_PITCH = 60.0
EDGE_JOINT_END_MARGIN = 7.0
"""Distance from a plate corner to the first insert, clear of the joints on the neighbouring edges."""
HOLE_EDGE_MARGIN = M3_COUNTERSINK_DIAMETER / 2 + 1.0
"""Smallest distance from a screw hole centre to the edge of the plate it passes through."""


class LapFastening(StrEnum):
    NUT = "nut"
    INSERT = "insert"


@dataclass
class Hardware:
    """Fasteners a joint consumes, for the bill of materials."""

    items: list[str]


Surface = Plate | Panel


def _locate(surface: Surface, rack_point: Vector, margin: float) -> tuple[Plate, Vector] | None:
    """The plate of `surface` that contains rack_point (in its plane), and the point in that plate's frame."""
    if isinstance(surface, Plate):
        local = surface.frame.to_local(rack_point)
        return (surface, local) if surface.contains(local.X, local.Y, margin) else None
    logical = surface.frame.to_local(rack_point)
    if surface.in_splice_zone(logical.X, logical.Y, margin):
        return None
    found = surface.segment_at(logical.X, logical.Y, margin)
    if found is None:
        return None
    plate, _, _ = found
    return plate, plate.frame.to_local(rack_point)


def _edge_point(surface: Surface, edge: Edge, position: float) -> tuple[Plate, EdgeInsert, Vector, Vector] | None:
    """B's plate holding the insert at `position` along the logical edge, the insert, its rack point and direction."""
    length, width = surface.length, surface.width
    match edge:
        case Edge.U0:
            logical, inward = Vector(0, position, 0), Vector(1, 0, 0)
        case Edge.U1:
            logical, inward = Vector(length, position, 0), Vector(-1, 0, 0)
        case Edge.V0:
            logical, inward = Vector(position, 0, 0), Vector(0, 1, 0)
        case Edge.V1:
            logical, inward = Vector(position, width, 0), Vector(0, -1, 0)
    probe = logical + inward * 1.0
    if isinstance(surface, Panel):
        if surface.in_splice_zone(probe.X, probe.Y, EDGE_INSERT.bore_diameter):
            return None
        found = surface.segment_at(probe.X, probe.Y)
        if found is None:
            return None
        plate, lu, lv = found
        local_point = Vector(lu, lv, 0) - inward * 1.0
    else:
        plate = surface
        local_point = logical
    along = local_point.Y if edge in (Edge.U0, Edge.U1) else local_point.X
    span = plate.width if edge in (Edge.U0, Edge.U1) else plate.length
    if not EDGE_JOINT_END_MARGIN <= along <= span - EDGE_JOINT_END_MARGIN:
        return None
    if plate.thickness < EDGE_INSERT_MIN_THICKNESS:
        raise ValueError(f"{plate.name} is {plate.thickness} mm; edge inserts need {EDGE_INSERT_MIN_THICKNESS:.1f}")
    insert = EdgeInsert(
        edge,
        along,
        EDGE_INSERT.bore_diameter,
        EDGE_INSERT.length,
        EDGE_INSERT.relief_diameter,
        EDGE_INSERT_RELIEF_DEPTH,
    )
    start, direction = insert.start_and_direction(plate)
    return plate, insert, plate.frame.to_rack(start), plate.frame.direction_to_rack(direction)


EDGE_JOINT_MIN_SPACING = 10.0


def edge_positions(span: float, pitch: float = EDGE_JOINT_PITCH, margin: float = EDGE_JOINT_END_MARGIN) -> list[float]:
    """Evenly spaced stations along an edge, at most `pitch` apart, at least two and never crowded."""
    usable = span - 2 * margin
    if usable < EDGE_JOINT_MIN_SPACING:
        raise ValueError(f"A {span:.1f} mm edge is too short for an edge joint")
    count = max(2, int(usable // pitch) + 2)
    return [margin + usable * k / (count - 1) for k in range(count)]


def _try_station(
    a: Surface | list[Surface], b: Surface, edge: Edge, position: float
) -> tuple[Plate, EdgeInsert, Plate, ThroughHole] | None:
    """The insert and hole for one station, or None if either would hit a seam, an edge or another feature."""
    found = _edge_point(b, edge, position)
    if found is None:
        return None
    b_plate, insert, rack_point, rack_direction = found
    b_region, (b_low, b_high) = feature_extent(insert, b_plate)
    if b_region is None or b_plate.blocked(b_region, b_low, b_high):
        return None
    located = _locate_any(a, rack_point, HOLE_EDGE_MARGIN)
    if located is None:
        return None
    a_plate, local = located
    if _hole_blocked(a_plate, local.X, local.Y):
        return None
    direction = a_plate.frame.direction_to_local(rack_direction)
    if abs(abs(direction.Z) - 1) > CONTACT_TOLERANCE:
        raise ValueError(f"{b_plate.name} edge {edge} does not meet {a_plate.name} square-on")
    if abs(local.Z - a_plate.thickness) < CONTACT_TOLERANCE:
        countersink = Face.BED
    elif abs(local.Z) < CONTACT_TOLERANCE:
        countersink = Face.TOP
    else:
        raise ValueError(f"{b_plate.name} edge {edge} does not touch a face of {a_plate.name}")
    return b_plate, insert, a_plate, ThroughHole(local.X, local.Y, M3_CLEARANCE, countersink, M3_COUNTERSINK_DIAMETER)


STATION_SEARCH_STEP = 1.0
SHORT_EDGE = 50.0
"""Edges shorter than this (1U walls) fit one station between their corner joints, which already tie them."""


def edge_joint(
    a: Surface | list[Surface],
    b: Surface,
    edge: Edge,
    positions: Iterable[float] | None = None,
    minimum: int | None = None,
) -> Hardware:
    """Screws through `a` into inserts in `b`'s `edge`.

    Each target station slides along the edge (up to half the spacing either way) to the
    nearest spot that clears seams, plate edges and existing features.
    """
    span = b.width if edge in (Edge.U0, Edge.U1) else b.length
    if minimum is None:
        minimum = 1 if span < SHORT_EDGE else 2
    targets = list(positions) if positions is not None else edge_positions(span)
    reach = max(EDGE_JOINT_MIN_SPACING, (targets[1] - targets[0]) / 2 if len(targets) > 1 else span / 2)
    chosen: list[float] = []
    items: list[str] = []
    for target in targets:
        offsets = [0.0]
        step = STATION_SEARCH_STEP
        while step <= reach:
            offsets += [step, -step]
            step += STATION_SEARCH_STEP
        for offset in offsets:
            position = target + offset
            if not 0 < position < span or any(abs(position - c) < EDGE_JOINT_MIN_SPACING for c in chosen):
                continue
            station = _try_station(a, b, edge, position)
            if station is None:
                continue
            b_plate, insert, a_plate, hole = station
            a_plate.add(hole)
            b_plate.add(insert)
            length = screw_length(a_plate.thickness, EDGE_INSERT.length, EDGE_INSERT_RELIEF_DEPTH)
            items += [f"M3x{length} countersunk (ISO 10642)", EDGE_INSERT.name]
            chosen.append(position)
            break
    made = len(chosen)
    stations = targets
    if made < minimum:
        names = a.name if not isinstance(a, list) else "/".join(x.name for x in a)
        raise ValueError(f"Only {made} of {len(stations)} edge-joint stations between {names} and {b.name} are usable")
    return Hardware(items)


def _locate_any(surfaces: Surface | list[Surface], rack_point: Vector, margin: float) -> tuple[Plate, Vector] | None:
    for surface in surfaces if isinstance(surfaces, list) else [surfaces]:
        local = surface.frame.to_local(rack_point)
        if abs(local.Z) > surface.thickness + CONTACT_TOLERANCE or local.Z < -CONTACT_TOLERANCE:
            continue
        found = _locate(surface, rack_point, margin)
        if found is not None:
            return found
    return None


def _hole_blocked(plate: Plate, u: float, v: float) -> bool:
    r = M3_COUNTERSINK_DIAMETER / 2 + 0.5
    return plate.blocked((u - r, v - r, u + r, v + r), -1.0, plate.thickness + 1)


NUT_SEAT_MIN = 2.0
"""Plastic left under a sunk nut."""


def nut_lap_fit(a_thickness: float, b_thickness: float) -> tuple[int, float]:
    """The longest standard screw that doesn't poke out of the nut pocket, and the pocket depth that seats its nut.

    The screw runs flush with the top of its nut; the nut is sunk as deep as it needs to be.
    """
    total = a_thickness + b_thickness
    for length in sorted(STANDARD_SCREW_LENGTHS, reverse=True):
        pocket = total + M3_NUT_HEIGHT - length
        if M3_NUT_HEIGHT <= pocket <= b_thickness - NUT_SEAT_MIN:
            return length, pocket
    raise ValueError(f"No standard screw seats a nut through {a_thickness} + {b_thickness} mm")


def lap_joint(a: Plate, b: Plate, rack_points: Iterable[Vector], fastening: LapFastening, minimum: int = 2) -> Hardware:
    """Screws through `a` and into `b`, where the two plates lie face to face.

    The head sits countersunk in a's free face. With a nut, b gets a hex pocket on its
    free (top) face; with an insert, b gets an insert bore through its thickness.
    """
    items: list[str] = []
    made = 0
    for point in rack_points:
        la, lb = a.frame.to_local(point), b.frame.to_local(point)
        if not (a.contains(la.X, la.Y, HOLE_EDGE_MARGIN) and b.contains(lb.X, lb.Y, HOLE_EDGE_MARGIN)):
            continue
        if _hole_blocked(a, la.X, la.Y) or _hole_blocked(b, lb.X, lb.Y):
            continue
        made += 1
        normal_dot = a.frame.w.dot(b.frame.w)
        if abs(abs(normal_dot) - 1) > CONTACT_TOLERANCE:
            raise ValueError(f"{a.name} and {b.name} are not parallel")
        a_face = Face.TOP if abs(la.Z) < 0.5 else Face.BED
        a.add(ThroughHole(la.X, la.Y, M3_CLEARANCE, a_face, M3_COUNTERSINK_DIAMETER))
        if fastening is LapFastening.NUT:
            if abs(lb.Z) > 0.5:
                raise ValueError(f"{b.name}'s nut pocket must be on the face away from {a.name}")
            length, pocket = nut_lap_fit(a.thickness, b.thickness)
            b.add(ThroughHole(lb.X, lb.Y, M3_CLEARANCE))
            b.add(HexPocket(lb.X, lb.Y, M3_NUT_ACROSS_CORNERS + M3_NUT_POCKET_CLEARANCE, pocket))
            items += [f"M3x{length} countersunk (ISO 10642)", "M3 hex nut (ISO 4032)"]
        else:
            b.add(TopPocket(lb.X, lb.Y, INSERT_M3_LONG.bore_diameter, 0, through=True))
            length = screw_length(a.thickness, INSERT_M3_LONG.length, b.thickness - INSERT_M3_LONG.length)
            items += [f"M3x{length} countersunk (ISO 10642)", INSERT_M3_LONG.name]
    if made < minimum:
        raise ValueError(f"Only {made} lap-joint points between {a.name} and {b.name} are usable")
    return Hardware(items)
