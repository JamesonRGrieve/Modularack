# SPDX-License-Identifier: AGPL-3.0-or-later
"""Several chassis laid out side by side along Y, exploded, for review."""

from __future__ import annotations

from build123d import Compound, Pos

from .chassis import RackChassis

DEFAULT_EXPLODE_DISTANCE = 127.0
DEFAULT_GAP_BETWEEN_UNITS = 381.0


class ExplodedView:
    def __init__(
        self,
        explode_distance: float = DEFAULT_EXPLODE_DISTANCE,
        gap_between_units: float = DEFAULT_GAP_BETWEEN_UNITS,
    ) -> None:
        self.explode_distance = explode_distance
        self.gap_between_units = gap_between_units
        self.chassis: list[RackChassis] = []

    def add(self, chassis: RackChassis) -> RackChassis:
        self.chassis.append(chassis)
        return chassis

    def assemble(self) -> Compound:
        """Each chassis exploded, front-aligned, spaced along +Y by its exploded width plus the gap."""
        placed = []
        y = 0.0
        for index, chassis in enumerate(self.chassis):
            exploded = chassis.assemble(self.explode_distance)
            half_width = exploded.bounding_box().size.Y / 2
            if index > 0:
                y += half_width
            placed.append(Pos(0, y, 0) * exploded)
            y += half_width + self.gap_between_units
        return Compound(children=placed)
