# SPDX-License-Identifier: AGPL-3.0-or-later
"""A printed plate as its solid shell (perimeters and skins) and its sparse infill core.

`split` cuts a plate into the two by its `PrintSettings`, so the FEA can give each its own stiffness
and strength.

The core's stiffness depends on the infill pattern, and published PLA tests disagree on how much
(their rankings of grid, gyroid, honeycomb and triangles flip with density and specimen). So the FEA
brackets it instead of guessing:

- `EMPTY_CORE`: the core carries nothing; the shell alone takes the load. This is the floor for
  every pattern and density, so a part that passes it passes whatever infill the printer uses.
- `voigt_core(density)`: the core is as stiff as its material fraction allows (lines all aligned
  with the load). No pattern beats it.
"""

from __future__ import annotations

from build123d import Box, Kind, Part, Pos, offset

from .plate import Plate
from .print_settings import PrintSettings

EMPTY_CORE = 1e-4
"""Core modulus as a fraction of solid: effectively nothing, but keeps the stiffness matrix regular."""


def voigt_core(density: float) -> float:
    """The stiffest any infill of this density can be, as a fraction of solid: its material fraction."""
    return density


def split(plate: Plate, settings: PrintSettings) -> tuple[Part, Part]:
    """The plate's solid shell and its sparse core, which together make the whole plate."""
    whole = plate.body()
    p, bottom = settings.perimeter_thickness, settings.bottom_thickness
    height = plate.thickness - bottom - settings.top_thickness
    if height <= 0 or min(plate.length, plate.width) <= 2 * p:
        raise ValueError(f"{plate.name} is solid at {settings.name}: no room for infill")
    core = Pos(plate.length / 2, plate.width / 2, bottom + height / 2) * Box(
        plate.length - 2 * p, plate.width - 2 * p, height
    )
    # Every cut through the plate gets its own ring of perimeters: grow each by the perimeter thickness.
    for feature in plate.features:
        if not feature.additive:
            core = core - offset(feature.shape(plate), amount=p, kind=Kind.ARC)
    return whole - core, core


def wall_section_modulus(thickness: float, height: float, settings: PrintSettings, core_fraction: float) -> float:
    """Section modulus (mm^3) of a plate printed flat and bent in its own plane, across its `height`.

    Both skins span the full height; the perimeters along the two long edges sit at the extreme fibres;
    the core between them counts at `core_fraction` of solid.
    """
    p = settings.perimeter_thickness
    skins = settings.bottom_thickness + settings.top_thickness
    middle = thickness - skins
    edge_arm = height / 2 - p / 2
    second_moment = (
        skins * height**3 / 12
        + 2 * (middle * p**3 / 12 + middle * p * edge_arm**2)
        + core_fraction * middle * (height - 2 * p) ** 3 / 12
    )
    return second_moment / (height / 2)
