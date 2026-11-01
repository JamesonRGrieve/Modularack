# SPDX-License-Identifier: AGPL-3.0-or-later
"""The component tree every Zephyrack assembly is built from.

A component owns named solids plus child components, each placed at an offset
inside its parent. Exploding is computed when an assembly is built, never stored:
`assemble(explode_distance)` returns a fresh compound, and the printable parts are
always the unexploded solids.

Coordinates throughout: +X runs from the front of the rack toward the back, +Y is
to the left when facing +X, +Z is up. Millimetres.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from build123d import Compound, Location, Part, Vector


class Component(ABC):
    """A named node in an assembly, with its own solids and child components."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.offset = Vector(0, 0, 0)
        self.children: dict[str, Component] = {}

    @abstractmethod
    def solids(self) -> dict[str, Part]:
        """This component's own solids, in its local frame."""

    def explode_offset(self, distance: float) -> Vector:
        """How far this component moves away from its parent when the assembly is exploded."""
        return Vector(0, 0, 0)

    def add_child(self, name: str, child: Component, offset: Vector) -> Component:
        if name in self.children:
            raise ValueError(f"{self.name} already has a child named {name!r}")
        child.offset = offset
        self.children[name] = child
        return child

    def assemble(self, explode_distance: float = 0.0) -> Compound:
        """This component and its descendants in the parent's frame, optionally exploded."""
        location = Location(self.offset + self.explode_offset(explode_distance))
        shapes = [solid.located(location) for solid in self.solids().values()]
        shapes += [child.assemble(explode_distance).moved(location) for child in self.children.values()]
        compound = Compound(children=shapes)
        compound.label = self.name
        return compound

    def printable_parts(self, prefix: str = "") -> dict[str, Part]:
        """Every solid in the tree, unexploded and in its local frame, keyed by its path."""
        path = f"{prefix}{self.name}"
        parts = {f"{path}.{key}": solid for key, solid in self.solids().items()}
        for child in self.children.values():
            parts |= child.printable_parts(f"{path}/")
        return parts
