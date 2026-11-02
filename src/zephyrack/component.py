# SPDX-License-Identifier: AGPL-3.0-or-later
"""The component tree every Zephyrack assembly is built from.

A component owns named solids plus child components. Each component has a
placement in its parent's frame. Exploding is computed when an assembly is
built, never stored: `assemble(explode_distance)` returns a fresh compound, and
the printable parts are always the unexploded solids in their own (print) frame.

Rack frame: +X runs from the front of the rack toward the back, +Y is to the left
when facing +X, +Z is up. Millimetres.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from build123d import Compound, Location, Part, Pos, Vector

from .print_settings import STRUCTURAL, PrintSettings


class Component(ABC):
    """A named node in an assembly, with its own solids and child components."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.placement = Location()
        self.children: dict[str, Component] = {}
        self.hardware: list[str] = []
        """Screws, inserts and nuts this assembly consumes (filled in by assemblies that build joints)."""
        self.print_settings: PrintSettings = STRUCTURAL
        """The slicer settings this component's solids are verified at."""
        self.print_location = Location()
        """Takes this component's solids from their own frame to their print orientation (+Z up)."""

    @abstractmethod
    def solids(self) -> dict[str, Part]:
        """This component's own solids, in its local frame."""

    def explode_offset(self, distance: float) -> Vector:
        """How far this component moves away from its parent when the assembly is exploded."""
        return Vector(0, 0, 0)

    def add_child(self, child: Component) -> Component:
        if child.name in self.children:
            raise ValueError(f"{self.name} already has a child named {child.name!r}")
        self.children[child.name] = child
        return child

    def assemble(self, explode_distance: float = 0.0) -> Compound:
        """This component and its descendants in the parent's frame, optionally exploded."""
        location = Pos(*self.explode_offset(explode_distance)) * self.placement
        shapes = []
        for key, solid in self.solids().items():
            # moved, not located: a part may carry its own position in its location (a lone Pos * Box).
            placed = solid.moved(location)
            placed.label = self.name if key in ("plate", "part") else f"{self.name}.{key}"
            shapes.append(placed)
        for child in self.children.values():
            assembled = child.assemble(explode_distance)
            # A plate printed as part of another (Plate.merge) has nothing of its own to place.
            if assembled.children:
                shapes.append(assembled.moved(location))
        compound = Compound(children=shapes)
        compound.label = self.name
        return compound

    def descendants(self) -> list[Component]:
        found: list[Component] = [self]
        for child in self.children.values():
            found += child.descendants()
        return found

    def printable_parts(self) -> dict[str, Part]:
        """Every solid in the tree, unexploded and in its own print frame, keyed by component name."""
        parts: dict[str, Part] = {}
        for component in self.descendants():
            for key, solid in component.solids().items():
                path = component.name if key in ("plate", "part") else f"{component.name}.{key}"
                if path in parts:
                    raise ValueError(f"Two printable parts are both named {path!r}")
                parts[path] = solid.moved(component.print_location)
        return parts

    def part_print_settings(self) -> dict[str, PrintSettings]:
        """The print settings of every part `printable_parts` returns, under the same keys."""
        settings: dict[str, PrintSettings] = {}
        for component in self.descendants():
            for key in component.solids():
                path = component.name if key in ("plate", "part") else f"{component.name}.{key}"
                settings[path] = component.print_settings
        return settings
