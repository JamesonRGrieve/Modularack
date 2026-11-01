# SPDX-License-Identifier: AGPL-3.0-or-later
"""The slicer settings each printed part is verified at.

A printed part is not solid: the slicer lays `perimeters` solid lines around every outline (the outer
edges and every hole), `bottom_layers` and `top_layers` of solid skin, and fills the rest with sparse
infill. The FEA (`fea`, `infill`) checks parts as printed, so every part carries the profile it was
checked at and the bill of materials states it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrintSettings:
    """The slicer settings that decide how much of a part is solid."""

    name: str
    perimeters: int
    bottom_layers: int
    top_layers: int
    infill_density: float
    """Fraction of the core's volume that is plastic."""
    infill_pattern: str
    line_width: float = 0.45
    layer_height: float = 0.2

    @property
    def perimeter_thickness(self) -> float:
        return self.perimeters * self.line_width

    @property
    def bottom_thickness(self) -> float:
        return self.bottom_layers * self.layer_height

    @property
    def top_thickness(self) -> float:
        return self.top_layers * self.layer_height

    def describe(self) -> str:
        if self.infill_density >= 1:
            return f"{self.name}: 100% infill"
        return (
            f"{self.name}: {self.perimeters} perimeters, {self.bottom_layers} bottom / {self.top_layers} top layers, "
            f"{self.infill_density:.0%} {self.infill_pattern}"
        )


PRUSA_MK3_QUALITY = PrintSettings("PrusaSlicer 0.20mm QUALITY @MK3", 2, 4, 5, 0.15, "gyroid")
"""The stock MK3S profile as PrusaSlicer ships it (PrusaResearch.ini). Too thin for the chassis walls."""

STRUCTURAL = PrintSettings("structural", 4, 4, 5, 0.15, "gyroid")
"""The stock profile with 4 perimeters: what every printed part defaults to."""

SOLID = PrintSettings("solid", 4, 4, 5, 1.0, "rectilinear")
"""100% infill, for the small parts that carry the most (rack ears)."""
