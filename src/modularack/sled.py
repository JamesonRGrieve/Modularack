# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less hot-swap drive sled.

The sled is a U: two rails screwed to the drive's SFF side holes, joined by a front
handle bar. A pinned sled (`SledGeometry.pinned`) takes no screws: a printed pin on a sprung skin of
each rail sits in each side hole. Press the drive up between the rails from below; it hangs on the pins'
flat tops, and pushing it up and out cams them aside.

The rails ride in grooves in the bay's side plates; a sprung detent on the left rail clicks into a notch
when the sled is home.

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
PIN_ENGAGE = 1.8
"""How far a tool-less sled's pin reaches into the drive's tapped side hole."""
PIN_CLEARANCE = 0.3
"""Between the pin's corners and the hole's minor diameter."""
PIN_ARM_LENGTH = 26.0
"""Short enough that a 2.5 in sled's detent arm fits between its two pin arms."""
PIN_ARM_SKIN = 1.6
"""The rail's inner skin that carries a pin, freed by a slot behind it."""
PIN_ARM_GAP = 2.4
"""The slot behind the skin: room for the pin to swing clear of the drive."""
PIN_ARM_FREE = 5.0
"""The arm runs past its pin by this much to its free end."""
PIN_ARM_END_GAP = 1.2
DETENT_ARM_SPACING = 2.0
"""Solid rail between a pin arm's slots and the detent arm's, along the rail."""
RAIL_CORE_MIN = 1.5
"""Solid rail left between a pin arm's slot and the detent arm's (or the rail's outer face)."""
PLA_MODULUS = 2300.0
"""MPa: Prusament PLA's data-sheet modulus, the same figure as `fea.PLA` (which this module can't import)."""


def pin_release_force(rail_height: float) -> float:
    """N to push a drive up out of a pinned sled: four arms, each bent PIN_ENGAGE + PIN_CLEARANCE by a 45
    degree cam, so the push equals the arms' spring force. Its weight hangs on the pins' flat tops."""
    second_moment = rail_height * PIN_ARM_SKIN**3 / 12
    lever = PIN_ARM_LENGTH - PIN_ARM_FREE
    stiffness = 3 * PLA_MODULUS * second_moment / lever**3
    return 4 * stiffness * (PIN_ENGAGE + PIN_CLEARANCE)


def pin_arm_strain() -> float:
    """Peak strain in a pin arm as the drive pushes its pin clear: 3 t d / (2 L^2), L from root to pin."""
    travel = PIN_ENGAGE + PIN_CLEARANCE
    return 3 * PIN_ARM_SKIN * travel / (2 * (PIN_ARM_LENGTH - PIN_ARM_FREE) ** 2)


@dataclass(frozen=True)
class SledGeometry:
    """Where a sled's features sit in its own frame (x back from the handle face, y from the left rail, z up)."""

    drive: DriveFormFactor
    width: float
    """Rail outer face to rail outer face."""
    bar_inset: float = 0.0
    """How far the handle bar stops short of the rails' outer faces, which run in the bay's grooves."""
    pinned: bool = False
    """Tool-less: printed pins on sprung skins of the rails snap into the drive's side holes, instead of
    screws. The drive hangs on the pins' flat tops; pushing it up cams them aside to release it."""

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

    @staticmethod
    def pin_arm_root(x: float, free: float) -> float:
        """Where a pin arm at x, running past its pin to `free`, joins the rail."""
        return x - (free - x) * (PIN_ARM_LENGTH - PIN_ARM_FREE) / PIN_ARM_FREE

    def pin_arm_spans(self) -> list[tuple[float, float]]:
        """The x range each pin arm (and its slots) takes on a rail."""
        spans = set()
        for x, _, _, free in self.pin_arms():
            root = self.pin_arm_root(x, free)
            end = free + (PIN_ARM_END_GAP if free > x else -PIN_ARM_END_GAP)
            lo, hi = sorted((end, root))
            spans.add((lo, hi))
        return sorted(spans)

    @property
    def detent_arm_start(self) -> float:
        """The arm's free end, just behind the handle bar; on a pinned sled, behind any pin arm in the way."""
        start = FRONT_BAR_THICKNESS + DETENT_GAP
        if self.pinned:
            for lo, hi in self.pin_arm_spans():
                if start - DETENT_GAP - DETENT_ARM_SPACING < hi and lo < start + DETENT_ARM_LENGTH + DETENT_ARM_SPACING:
                    start = hi + DETENT_GAP + DETENT_ARM_SPACING
        return start

    @property
    def detent_x(self) -> float:
        return self.detent_arm_start + DETENT_BUMP_SETBACK

    def pin_arms(self) -> list[tuple[float, float, float, float]]:
        """Each pin's (x, y of the rail's inner face, inward direction, free-end x)."""
        connector_end = FRONT_BAR_THICKNESS + self.drive.length
        arms = []
        for offset in self.drive.side_hole_offsets:
            x = connector_end - offset
            # The free end points to the nearer end of the rail, so the arm stays on it.
            free = x - PIN_ARM_FREE if x - FRONT_BAR_THICKNESS < self.length - x else x + PIN_ARM_FREE
            for inner_y, inward in ((self.rail_width, 1.0), (self.width - self.rail_width, -1.0)):
                arms.append((x, inner_y, inward, free))
        return arms

    def pinned_rail_width(self) -> float:
        """The narrowest rail that takes a pin arm (and the detent arm, where they overlap along the rail)."""
        need = PIN_ARM_SKIN + PIN_ARM_GAP + RAIL_CORE_MIN
        start = self.detent_arm_start
        if any(start < hi and lo < start + DETENT_ARM_LENGTH for lo, hi in self.pin_arm_spans()):
            need += DETENT_ARM_THICKNESS + DETENT_GAP
        return need

    def validate(self) -> None:
        if self.pinned:
            need = self.pinned_rail_width()
            start = self.detent_arm_start
            if start + DETENT_ARM_LENGTH > self.length - 1:
                raise ValueError(f"{self.drive.name} sled: no room for the detent arm between its pin arms")
            if self.rail_width < need:
                raise ValueError(
                    f"{self.drive.name} sled rails are {self.rail_width:.1f} mm wide; its pin arms need {need:.1f}"
                )
            for x, _, _, free in self.pin_arms():
                root = self.pin_arm_root(x, free)
                if min(free, root) < FRONT_BAR_THICKNESS + 1 or max(free, root) > self.length - 1:
                    raise ValueError(f"{self.drive.name} sled: a pin arm at x = {x:.1f} runs off its rail")
            return
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
        pins: list[Part] = []
        if g.pinned:
            for x, inner_y, inward, free in g.pin_arms():
                root = g.pin_arm_root(x, free)
                lo, hi = sorted((free, root))
                gap = (inner_y - inward * (PIN_ARM_SKIN + PIN_ARM_GAP), inner_y - inward * PIN_ARM_SKIN)
                g0, g1 = sorted(gap)
                cuts.append(Pos((lo + hi) / 2, (g0 + g1) / 2, rail_h / 2) * Box(hi - lo, g1 - g0, rail_h + 2))
                # Across the skin at the free end, so the skin hangs from its root alone.
                e0, e1 = sorted((gap[0], inner_y + inward))
                end = free + (PIN_ARM_END_GAP / 2 if free > x else -PIN_ARM_END_GAP / 2)
                cuts.append(Pos(end, (e0 + e1) / 2, rail_h / 2) * Box(PIN_ARM_END_GAP, e1 - e0, rail_h + 2))
                # A diamond pin: its 45 degree faces print standing up and cam the skin out as the drive
                # is pressed in between the rails.
                # Flat on top, where the drive hangs on it, and a 45 degree point below: it prints standing
                # up, and a drive pushed up from below cams it aside. It fits inside the hole's minor diameter.
                a = (g.drive.side_hole_minor - PIN_CLEARANCE) / (2 * math.sqrt(2))
                reach = DRIVE_SIDE_CLEARANCE + PIN_ENGAGE
                plane = Plane(origin=(x, inner_y - inward * 0.5, hole_z), x_dir=(1, 0, 0), z_dir=(0, inward, 0))
                # The plane's second axis is -inward * z: flip heights to match.
                outline = [(-a, a), (a, a), (a, 0.0), (0.0, -a), (-a, 0.0)]
                profile = plane * Polygon(*[(px, -inward * pz) for px, pz in outline], align=None)
                pins.append(extrude(profile, amount=reach + 0.5, dir=(0, inward, 0)))
        else:
            for offset in g.drive.side_hole_offsets:
                x = connector_end - offset
                for outer_y, inward_v in ((0.0, Vector(0, 1, 0)), (g.width, Vector(0, -1, 0))):
                    start = Vector(x, outer_y, hole_z) - inward_v
                    cuts.append(teardrop_prism(start, inward_v, g.drive.screw_clearance / 2, rail_w + 2))
                    cuts.append(
                        teardrop_prism(
                            start, inward_v, DRIVE_SCREW_HEAD_RECESS_DIAMETER / 2, DRIVE_SCREW_HEAD_RECESS_DEPTH + 1
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
        result = body.fuse(bump)
        for pin in pins:
            result = result.fuse(pin)
        return {"part": result.clean()}
