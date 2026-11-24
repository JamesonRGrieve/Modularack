# SPDX-License-Identifier: AGPL-3.0-or-later
"""Checks that every printable part prints as modelled: it fits the bed and needs no supports.

A part is checked in its own frame, which is its print orientation (bed at its lowest Z).
A surface needs support when it faces down more steeply than 45 degrees and isn't sitting
on the bed. Faces are sampled on a grid, so curved faces (teardrop holes, countersinks)
are checked across their whole extent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build123d import Part

from .layout import Bed

MAX_OVERHANG_DEGREES = 45.0
SAMPLING_TOLERANCE_DEGREES = 0.05
"""Numerical slack only: samples are tessellation vertices, which lie exactly on the trimmed face."""
BED_CONTACT_TOLERANCE = 0.05
TESSELLATION_TOLERANCE = 0.05


@dataclass(frozen=True)
class Overhang:
    area: float
    lowest_normal_z: float
    height: float


def overhangs(part: Part) -> list[Overhang]:
    """Every face of `part` that would need support.

    Samples are the vertices of each face's own tessellation, which lie on the trimmed face
    (a teardrop's cylinder face spans only the arc its roof doesn't replace). Triangle
    centroids would not: projected onto the full cylinder they read up to 2 degrees steep.
    """
    limit = -math.sin(math.radians(MAX_OVERHANG_DEGREES + SAMPLING_TOLERANCE_DEGREES))
    bed = part.bounding_box().min.Z
    found: list[Overhang] = []
    for face in part.faces():
        vertices, _ = face.tessellate(TESSELLATION_TOLERANCE)
        worst = 1.0
        height = math.inf
        for vertex in vertices:
            normal = face.normal_at(vertex)
            if limit > normal.Z and vertex.Z - bed > BED_CONTACT_TOLERANCE:
                worst = min(worst, normal.Z)
                height = min(height, vertex.Z - bed)
        if worst < limit:
            found.append(Overhang(face.area, worst, height))
    return found


def fits_bed(part: Part, bed: Bed) -> bool:
    size = part.bounding_box().size
    return bed.fits((size.X, size.Y, size.Z))
