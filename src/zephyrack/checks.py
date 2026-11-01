# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whole-assembly checks shared by the build report and the test suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from build123d import Shape

from .component import Component
from .layout import MK3S_BED, Bed
from .printability import fits_bed, overhangs

INTERFERENCE_LIMIT = 1.0
"""mm^3. Parts that only touch intersect in a sliver of zero volume."""


@dataclass
class Report:
    parts: int = 0
    off_bed: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    needs_support: list[str] = field(default_factory=list)
    interferences: list[tuple[str, str, float]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.off_bed or self.invalid or self.needs_support or self.interferences)


def _overlap(a: Shape[Any], b: Shape[Any]) -> bool:
    ba, bb = a.bounding_box(), b.bounding_box()
    return not (
        ba.min.X >= bb.max.X
        or bb.min.X >= ba.max.X
        or ba.min.Y >= bb.max.Y
        or bb.min.Y >= ba.max.Y
        or ba.min.Z >= bb.max.Z
        or bb.min.Z >= ba.max.Z
    )


def interferences(assembly: Component) -> list[tuple[str, str, float]]:
    """Every pair of placed parts that overlaps by more than INTERFERENCE_LIMIT."""
    found = []
    for a, b in combinations(assembly.assemble().leaves, 2):
        if not _overlap(a, b):
            continue
        common = a.intersect(b)
        volume = sum(s.volume for s in common.solids()) if common is not None else 0.0
        if volume > INTERFERENCE_LIMIT:
            found.append((a.label, b.label, volume))
    return found


def check(assembly: Component, bed: Bed = MK3S_BED, with_interference: bool = True) -> Report:
    report = Report()
    for name, part in assembly.printable_parts().items():
        report.parts += 1
        if not fits_bed(part, bed):
            report.off_bed.append(name)
        if not part.is_valid or len(part.solids()) != 1:
            report.invalid.append(name)
        if overhangs(part):
            report.needs_support.append(name)
    if with_interference:
        report.interferences = interferences(assembly)
    return report
