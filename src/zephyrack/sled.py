# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less hot-swap drive sled.

The sled is a U: two rails screwed to the drive's SFF side holes, joined by a front
handle bar. The rails ride in grooves in the bay's side plates; a sprung detent on
the left rail clicks into a notch when the sled is home.

Print orientation is the sled's own frame (rails standing on the bed). Drive weight
bends the rails in their own vertical plane and handle pulls bend the bar in the
bed plane, so both run along the layers. Every horizontal hole is a teardrop and
every vent a diamond, so nothing needs support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Box, Location, Part, Plane, Polygon, Pos, Vector, extrude

from .component import Component
from .fasteners import DRIVE_SCREW_HEAD_RECESS_DEPTH, DRIVE_SCREW_HEAD_RECESS_DIAMETER
from .plate import teardrop_prism
from .standards import DriveFormFactor

DRIVE_SIDE_CLEARANCE = 0.5
"""Gap between the drive and each rail."""
FRONT_BAR_THICKNESS = 6.0
RAIL_MIN_WIDTH = DRIVE_SCREW_HEAD_RECESS_DEPTH + 2.0
RAIL_MARGIN_ABOVE_HOLE = 1.5
RECESS_MARGIN_BELOW = 1.0
FACE_CLEARANCE_ABOVE_DRIVE = 0.5
GRIP_NOTCH_WIDTH = 40.0
GRIP_NOTCH_DEPTH = 9.0
VENT_SIZE = 6.0
"""Diamond vents in the handle bar: square holes turned 45 degrees, so their tops are 45 degree roofs."""
VENT_PITCH = 10.0
DETENT_ARM_LENGTH = 24.0
DETENT_ARM_THICKNESS = 1.6
DETENT_GAP = 1.2
DETENT_BUMP = 0.8
DETENT_BUMP_SETBACK = 4.0
"""Distance from the arm's free (front) end to the top of the detent bump."""


@dataclass(frozen=True)
class SledGeometry:
    """Where a sled's features sit in its own frame (x back from the handle face, y from the left rail, z up)."""

    drive: DriveFormFactor
    width: float
    """Rail outer face to rail outer face."""
    bar_inset: float = 0.0
    """How far the handle bar stops short of the rails' outer faces, which run in the bay's grooves."""

    @property
    def rail_width(self) -> float:
        return (self.width - self.drive.width - 2 * DRIVE_SIDE_CLEARANCE) / 2

    @property
    def drive_base(self) -> float:
        """Height of the drive's base above the rail bottoms, so the head recess clears the rail's underside."""
        return max(0.0, DRIVE_SCREW_HEAD_RECESS_DIAMETER / 2 + RECESS_MARGIN_BELOW - self.drive.side_hole_height)

    @property
    def rail_height(self) -> float:
        return (
            self.drive_base
            + self.drive.side_hole_height
            + DRIVE_SCREW_HEAD_RECESS_DIAMETER / 2
            + RAIL_MARGIN_ABOVE_HOLE
        )

    @property
    def bar_height(self) -> float:
        return self.drive_base + self.drive.height + FACE_CLEARANCE_ABOVE_DRIVE

    @property
    def length(self) -> float:
        return FRONT_BAR_THICKNESS + self.drive.length

    @property
    def detent_arm_start(self) -> float:
        """The arm's free end, just behind the handle bar."""
        return FRONT_BAR_THICKNESS + DETENT_GAP

    @property
    def detent_x(self) -> float:
        return self.detent_arm_start + DETENT_BUMP_SETBACK

    def validate(self) -> None:
        if self.rail_width < RAIL_MIN_WIDTH:
            raise ValueError(
                f"{self.drive.name} sled is {self.width:.1f} mm wide; rails would be {self.rail_width:.2f} mm, "
                f"under the {RAIL_MIN_WIDTH:.1f} mm the screw recess needs"
            )


def diamond_prism(centre: Vector, size: float, length: float) -> Part:
    """A square hole turned 45 degrees, running along +x."""
    half = size / math.sqrt(2)
    profile = Plane(origin=centre, x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * Polygon(
        (half, 0), (0, half), (-half, 0), (0, -half), align=None
    )
    return extrude(profile, amount=length, dir=(1, 0, 0))


class Sled(Component):
    def __init__(self, name: str, geometry: SledGeometry, placement: Location) -> None:
        geometry.validate()
        super().__init__(name)
        self.geometry = geometry
        self.placement = placement

    def solids(self) -> dict[str, Part]:
        g = self.geometry
        rail_w, rail_h = g.rail_width, g.rail_height
        body: Part = Pos(g.length / 2, rail_w / 2, rail_h / 2) * Box(g.length, rail_w, rail_h)
        body += Pos(g.length / 2, g.width - rail_w / 2, rail_h / 2) * Box(g.length, rail_w, rail_h)
        body += Pos(FRONT_BAR_THICKNESS / 2, g.width / 2, g.bar_height / 2) * Box(
            FRONT_BAR_THICKNESS, g.width - 2 * g.bar_inset, g.bar_height
        )
        cuts: list[Part] = [
            Pos(FRONT_BAR_THICKNESS / 2, g.width / 2, g.bar_height - GRIP_NOTCH_DEPTH / 2 + 0.5)
            * Box(FRONT_BAR_THICKNESS + 2, GRIP_NOTCH_WIDTH, GRIP_NOTCH_DEPTH + 1)
        ]
        vent_z = rail_h + VENT_SIZE
        vent_top = g.bar_height - GRIP_NOTCH_DEPTH - VENT_SIZE
        if vent_top > vent_z:
            span = g.width - 2 * rail_w - 2 * VENT_SIZE
            count = max(1, int(span // VENT_PITCH))
            for k in range(count):
                y = g.width / 2 + (k - (count - 1) / 2) * VENT_PITCH
                cuts.append(diamond_prism(Vector(-1, y, (vent_z + vent_top) / 2), VENT_SIZE, FRONT_BAR_THICKNESS + 2))
        connector_end = FRONT_BAR_THICKNESS + g.drive.length
        hole_z = g.drive_base + g.drive.side_hole_height
        for offset in g.drive.side_hole_offsets:
            x = connector_end - offset
            for outer_y, inward in ((0.0, Vector(0, 1, 0)), (g.width, Vector(0, -1, 0))):
                start = Vector(x, outer_y, hole_z) - inward
                cuts.append(teardrop_prism(start, inward, g.drive.screw_clearance / 2, rail_w + 2))
                cuts.append(
                    teardrop_prism(
                        start, inward, DRIVE_SCREW_HEAD_RECESS_DIAMETER / 2, DRIVE_SCREW_HEAD_RECESS_DEPTH + 1
                    )
                )
        # Detent: a slot frees the left rail's outer skin into a cantilever fixed at its back end.
        arm_start = g.detent_arm_start
        cuts.append(
            Pos(arm_start + DETENT_ARM_LENGTH / 2, DETENT_ARM_THICKNESS + DETENT_GAP / 2, rail_h / 2)
            * Box(DETENT_ARM_LENGTH, DETENT_GAP, rail_h + 2)
        )
        cuts.append(
            Pos(arm_start - DETENT_GAP / 2, (DETENT_ARM_THICKNESS + DETENT_GAP) / 2 - 0.5, rail_h / 2)
            * Box(DETENT_GAP, DETENT_ARM_THICKNESS + DETENT_GAP + 1, rail_h + 2)
        )
        body = body.cut(*cuts)
        bump = extrude(
            Polygon(
                (g.detent_x - DETENT_BUMP * 2, 0),
                (g.detent_x, -DETENT_BUMP),
                (g.detent_x + DETENT_BUMP * 2, 0),
                align=None,
            ),
            amount=rail_h,
            dir=(0, 0, 1),
        )
        return {"part": body.fuse(bump).clean()}
