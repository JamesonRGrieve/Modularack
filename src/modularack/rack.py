# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fully printed 10 in or 19 in rack frame, from the same plates and joints as the chassis.

Each side is a front post, an optional rear post and a side panel between them; a base
and a top tie the two sides together. Posts carry the EIA-310 hole pattern with captive
M6 nuts on their inner faces, so standard rack screws (or Modularack ears) fasten to them.

Posts are taller than a printer bed, so they are printed in segments of whole U. The
segments butt end to end and are carried by the side panel, whose own seams are kept
clear of the post seams: each part bridges the other's joints, like brickwork.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from build123d import Part, Vector

from .component import Component
from .fasteners import M6_NUT_ACROSS_CORNERS, M6_NUT_HEIGHT, RACK_SCREW_CLEARANCE
from .joints import Hardware, edge_joint, edge_positions
from .layout import MK3S_BED, Bed, Panel
from .plate import Edge, Frame, HexPocket, Plate, ThroughHole
from .standards import POST_INNER_EDGE_TO_HOLE, RACK_UNIT, RackStandard, rack_hole_heights

POST_WIDTH = 30.0
"""Post face width, from the opening edge outward."""
POST_THICKNESS = 9.0
SIDE_PANEL_THICKNESS = 9.0
BASE_THICKNESS = 7.0
NUT_POCKET_CLEARANCE = 0.3
POST_SEAM_CLEARANCE = 20.0
"""Side-panel seams stay at least this far from a post seam."""
MIN_POST_JOINTS = 2
POST_JOINT_PITCH = 30.0
"""Closer than the default edge pitch, so even a short post segment gets two joints to its panel."""


@dataclass
class PrintedRack(Component):
    rack: RackStandard
    units: int
    depth: float
    four_post: bool = True
    bed: Bed = MK3S_BED

    def __post_init__(self) -> None:
        if self.units < 1:
            raise ValueError("A rack is at least 1U tall")
        Component.__init__(self, f"rack_{self.rack.name}_{self.units}U")
        self.height = self.units * RACK_UNIT
        self.half_opening = self.rack.opening / 2
        self.outer_half_width = self.half_opening + POST_WIDTH
        max_units = int(max(self.bed.usable_x, self.bed.usable_y) // RACK_UNIT)
        count = math.ceil(self.units / max_units)
        self.segment_units = [self.units // count + (1 if k < self.units % count else 0) for k in range(count)]
        self.hardware = self._build().items

    def solids(self) -> dict[str, Part]:
        return {}

    def bill_of_materials(self) -> Counter[str]:
        return Counter(self.hardware)

    def _post_seams(self) -> list[float]:
        seams, z = [], 0.0
        for units in self.segment_units[:-1]:
            z += units * RACK_UNIT
            seams.append(z)
        return seams

    def _posts(self, side: int, rear: bool) -> list[Plate]:
        """Post segments for one corner. side: +1 left, -1 right."""
        b = BASE_THICKNESS
        posts: list[Plate] = []
        z = 0.0
        for index, units in enumerate(self.segment_units):
            height = units * RACK_UNIT
            if not rear:
                origin_y = self.half_opening if side > 0 else -self.outer_half_width
                frame = Frame(Vector(0, origin_y, b + z), Vector(0, 1, 0), Vector(1, 0, 0))
                hole_u = (
                    (self.rack.hole_spacing / 2 - self.half_opening)
                    if side > 0
                    else POST_WIDTH - POST_INNER_EDGE_TO_HOLE
                )
            else:
                origin_y = self.outer_half_width if side > 0 else -self.half_opening
                frame = Frame(Vector(self.depth, origin_y, b + z), Vector(0, -1, 0), Vector(-1, 0, 0))
                hole_u = POST_WIDTH - POST_INNER_EDGE_TO_HOLE if side > 0 else POST_INNER_EDGE_TO_HOLE
            name = f"{self.name}_{'left' if side > 0 else 'right'}_{'rear' if rear else 'front'}_post{index}"
            explode = Vector(1 if rear else -1, 0, 0)
            post = Plate(name, POST_WIDTH, height, POST_THICKNESS, frame, explode)
            for hole_z in rack_hole_heights(units):
                post.add(ThroughHole(hole_u, hole_z, RACK_SCREW_CLEARANCE))
                post.add(
                    HexPocket(
                        hole_u,
                        hole_z,
                        M6_NUT_ACROSS_CORNERS + NUT_POCKET_CLEARANCE,
                        M6_NUT_HEIGHT + NUT_POCKET_CLEARANCE,
                    )
                )
            self.add_child(post)
            posts.append(post)
            z += height
        return posts

    def _build(self) -> Hardware:
        b, d, w = BASE_THICKNESS, self.depth, self.outer_half_width
        hardware = Hardware([])
        self.base = Panel(
            f"{self.name}_base",
            d,
            2 * w,
            b,
            Frame(Vector(0, -w, 0), Vector(1, 0, 0), Vector(0, 0, 1)),
            self.bed,
            explode_direction=Vector(0, 0, -1),
        )
        self.top = Panel(
            f"{self.name}_top",
            d,
            2 * w,
            b,
            Frame(Vector(0, w, 2 * b + self.height), Vector(1, 0, 0), Vector(0, 0, -1)),
            self.bed,
            explode_direction=Vector(0, 0, 1),
        )
        self.add_child(self.base)
        self.add_child(self.top)
        keep = [(s - POST_SEAM_CLEARANCE, s + POST_SEAM_CLEARANCE) for s in self._post_seams()]
        front_end = POST_THICKNESS
        back_end = d - POST_THICKNESS if self.four_post else d
        for side in (1, -1):
            front = self._posts(side, rear=False)
            rear = self._posts(side, rear=True) if self.four_post else []
            if side > 0:
                frame = Frame(Vector(front_end, w, b), Vector(1, 0, 0), Vector(0, -1, 0))
                front_edge, rear_edge = Edge.U0, Edge.U1
            else:
                frame = Frame(Vector(back_end, -w, b), Vector(-1, 0, 0), Vector(0, 1, 0))
                front_edge, rear_edge = Edge.U1, Edge.U0
            panel = Panel(
                f"{self.name}_{'left' if side > 0 else 'right'}_side",
                back_end - front_end,
                self.height,
                SIDE_PANEL_THICKNESS,
                frame,
                self.bed,
                keepouts_v=keep,
                explode_direction=Vector(0, side, 0),
            )
            self.add_child(panel)
            stations = edge_positions(self.height, POST_JOINT_PITCH)
            hardware.items += edge_joint(list(front), panel, front_edge, stations).items
            if rear:
                hardware.items += edge_joint(list(rear), panel, rear_edge, stations).items
            for posts in (front, rear):
                if not posts:
                    continue
                hardware.items += edge_joint(self.base, posts[0], Edge.V0).items
                hardware.items += edge_joint(self.top, posts[-1], Edge.V1).items
                for post in posts:
                    joints = sum(
                        1 for f in post.features if isinstance(f, ThroughHole) and f.diameter < RACK_SCREW_CLEARANCE
                    )
                    if joints < MIN_POST_JOINTS:
                        raise ValueError(f"{post.name} has only {joints} joints to its side panel")
            hardware.items += edge_joint(self.base, panel, Edge.V0).items
            hardware.items += edge_joint(self.top, panel, Edge.V1).items
            hardware.items += panel.screws
        for panel in (self.base, self.top):
            hardware.items += panel.screws
        nuts = sum(
            1 for c in self.descendants() if isinstance(c, Plate) for f in c.features if isinstance(f, HexPocket)
        )
        hardware.items += ["M6 hex nut (ISO 4032)"] * nuts
        return hardware
