# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finite-element checks of the load paths that matter, with stresses read in each part's print frame.

`uv run zephyrack-fea [design ...]` meshes the rack ear of each chassis with gmsh (second-order
tetrahedra), solves it in CalculiX for the worst real mounting (a fully loaded chassis hanging
from its two front ears in a two-post rack), and reports:

- in-layer stress (von Mises), against the material's printed tensile strength;
- tension across the layers and shear between them, against its interlayer adhesion;
- the ear's deflection.

The part is analysed in its print frame (bed at w = 0), so sigma_ww is tension across the layers
and tau_uw / tau_vw are interlaminar shear. The external binaries come from ZEPHYRACK_GMSH and
ZEPHYRACK_CCX, defaulting to the desktop installs the CAD SOP records.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from build123d import export_step

from .chassis import FLOOR_THICKNESS, WALL_THICKNESS, RackChassis
from .plate import Plate, Slot, ThroughHole
from .reference import reference_builders
from .sled import Sled
from .standards import DRIVE_3_5

logger = logging.getLogger(__name__)

GMSH = os.environ.get("ZEPHYRACK_GMSH", "/opt/gmsh-4.15.2-Linux64/bin/gmsh")
CCX = os.environ.get("ZEPHYRACK_CCX", "/opt/calculix-freecad-1.1.4/bin/ccx")
SOLVER_TIMEOUT = 1800
MESH_SIZE = 1.5
"""Largest tetrahedron edge, mm."""


@dataclass(frozen=True)
class Material:
    """Prusament PLA technical data sheet v1.1 (16-02-2022), printed specimens."""

    name: str = "Prusament PLA"
    density: float = 1.24e-3
    """g/mm^3 (ISO 1183)."""
    modulus: float = 2300.0
    """MPa, tensile, horizontal print (ISO 527-1)."""
    poisson: float = 0.36
    """Typical for PLA; not on the data sheet."""
    in_layer_strength: float = 51.0
    """MPa, tensile strength of horizontally printed specimens (ISO 527-1)."""
    interlayer_strength: float = 17.0
    """MPa, interlayer adhesion (Prusa Polymers method)."""


PLA = Material()
SAFETY_FACTOR = 2.0
GRAVITY = 9.81e-3
"""N per g."""


@dataclass(frozen=True)
class Payload:
    """Design assumptions for what a chassis carries, in grams. Not measured."""

    drive_3_5: float = 750.0
    drive_2_5: float = 150.0
    board: float = 2000.0
    """Board, CPU, cooler and memory."""
    power_supply: float = 2500.0


PAYLOAD = Payload()


@dataclass(frozen=True)
class EarResult:
    design: str
    load_n: float
    moment_nmm: float
    max_displacement: float
    in_layer: float
    across_layer_tension: float
    interlayer_shear: float

    @property
    def in_layer_factor(self) -> float:
        return PLA.in_layer_strength / self.in_layer

    @property
    def interlayer_factor(self) -> float:
        return PLA.interlayer_strength / max(self.across_layer_tension, self.interlayer_shear)

    @property
    def passes(self) -> bool:
        return min(self.in_layer_factor, self.interlayer_factor) >= SAFETY_FACTOR


def chassis_mass(chassis: RackChassis) -> float:
    """Printed parts as solid PLA (an upper bound) plus the payload, in grams."""
    printed = sum(part.volume for part in chassis.printable_parts().values()) * PLA.density
    payload = 0.0
    for sled in (c for c in chassis.descendants() if isinstance(c, Sled)):
        payload += PAYLOAD.drive_3_5 if sled.geometry.drive is DRIVE_3_5 else PAYLOAD.drive_2_5
    if chassis.motherboard is not None:
        payload += PAYLOAD.board + PAYLOAD.power_supply
    return printed + payload


def _mesh(step: Path, work: Path) -> tuple[dict[int, tuple[float, float, float]], list[list[int]]]:
    msh = work / "part.msh"
    subprocess.run(
        [GMSH, str(step), "-3", "-order", "2", "-clmax", str(MESH_SIZE), "-format", "msh2", "-o", str(msh)],
        check=True,
        capture_output=True,
        timeout=SOLVER_TIMEOUT,
    )
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: list[list[int]] = []
    lines = msh.read_text().splitlines()
    i = lines.index("$Nodes") + 2
    while lines[i] != "$EndNodes":
        index, x, y, z = lines[i].split()
        nodes[int(index)] = (float(x), float(y), float(z))
        i += 1
    i = lines.index("$Elements") + 2
    while lines[i] != "$EndElements":
        fields = lines[i].split()
        if fields[1] == "11":  # 10-node tetrahedron
            connectivity = [int(n) for n in fields[3 + int(fields[2]) :]]
            # gmsh orders the last two edge nodes (2-3, 1-3) opposite to CalculiX C3D10.
            connectivity[8], connectivity[9] = connectivity[9], connectivity[8]
            elements.append(connectivity)
        i += 1
    return nodes, elements


def _write_deck(
    path: Path,
    nodes: dict[int, tuple[float, float, float]],
    elements: list[list[int]],
    fixed: list[int],
    forces: dict[int, tuple[float, float, float]],
) -> None:
    lines = ["*NODE"] + [f"{n},{x},{y},{z}" for n, (x, y, z) in nodes.items()]
    lines.append("*ELEMENT, TYPE=C3D10, ELSET=EALL")
    lines += [f"{k + 1}," + ",".join(str(n) for n in e) for k, e in enumerate(elements)]
    lines += ["*NSET, NSET=FIXED"] + [str(n) for n in fixed]
    lines += [
        "*MATERIAL, NAME=PLA",
        "*ELASTIC",
        f"{PLA.modulus},{PLA.poisson}",
        "*SOLID SECTION, ELSET=EALL, MATERIAL=PLA",
        "*STEP",
        "*STATIC",
        "*BOUNDARY",
        "FIXED,1,3,0.0",
        "*CLOAD",
    ]
    for node, vector in forces.items():
        lines += [f"{node},{dof + 1},{value}" for dof, value in enumerate(vector) if value]
    lines += ["*NODE PRINT, NSET=NALL", "U", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    lines.insert(0, "*NSET, NSET=NALL, GENERATE\n1," + str(max(nodes)) + ",1")
    path.write_text("\n".join(lines) + "\n")


def _results(dat: Path) -> tuple[float, list[tuple[float, ...]]]:
    displacement = 0.0
    stresses: list[tuple[float, ...]] = []
    section = ""
    for line in dat.read_text().splitlines():
        if "displacements" in line:
            section = "u"
            continue
        if "stresses" in line:
            section = "s"
            continue
        fields = line.split()
        if not fields:
            continue
        try:
            values = [float(f) for f in fields]
        except ValueError:
            continue
        if section == "u" and len(values) == 4:
            displacement = max(displacement, math.sqrt(sum(v * v for v in values[1:])))
        elif section == "s" and len(values) == 8:
            stresses.append(tuple(values[2:]))
    return displacement, stresses


def von_mises(s: tuple[float, ...]) -> float:
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy * xy + xz * xz + yz * yz))


BEARING_HALF_HEIGHT = 5.0
"""The wall's front edge bears on the ear over this half-height around the pivot."""
PEAK_PERCENTILE = 0.995
"""Point loads and fixed nodes make single-point stress spikes; report the 99.5th percentile."""


def _percentile(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(PEAK_PERCENTILE * len(ordered)))]


def analyse_ear(name: str, chassis: RackChassis) -> EarResult:
    """The left ear of a chassis hung from its front ears: half the weight, half the overturning moment."""
    ear = chassis.children[f"{chassis.name}_left_ear"]
    assert isinstance(ear, Plate)
    weight = chassis_mass(chassis) * GRAVITY
    load = weight / 2
    lever = chassis.depth / 2
    moment = load * lever
    slots = [f for f in ear.features if isinstance(f, Slot)]
    joints = [f for f in ear.features if isinstance(f, ThroughHole)]
    bearing_v = FLOOR_THICKNESS + BEARING_HALF_HEIGHT
    # The overturning moment pivots the wall about its bottom edge, which bears on the ear; the screws
    # above it take tension in proportion to their height over that pivot (like a bolted flange).
    arms = {id(h): h.v - bearing_v for h in joints if h.v > bearing_v}
    second_moment = sum(a * a for a in arms.values())
    tensions = {key: moment * arm / second_moment for key, arm in arms.items()}
    couple = sum(tensions.values())
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        export_step(ear.solids()["plate"], work / "part.step")
        nodes, elements = _mesh(work / "part.step", work)
        fixed = [
            n
            for n, (u, v, w) in nodes.items()
            if any(
                abs(v - s.v) <= s.diameter / 2 + 0.05 and abs(u - s.u) <= s.travel / 2 + s.diameter / 2 + 0.05
                for s in slots
            )
            and 0 < w < ear.thickness
        ]
        forces: dict[int, list[float]] = {}

        def add(selected: list[int], total: tuple[float, float, float]) -> None:
            if not selected:
                raise RuntimeError(f"{name}: no mesh nodes for a load")
            for n in selected:
                f = forces.setdefault(n, [0.0, 0.0, 0.0])
                for k in range(3):
                    f[k] += total[k] / len(selected)

        def hole_wall(h: ThroughHole) -> list[int]:
            r = h.diameter / 2
            return [
                n
                for n, (u, v, w) in nodes.items()
                if abs(math.hypot(u - h.u, v - h.v) - r) < 0.05 and 0 <= w <= ear.thickness
            ]

        def countersink(h: ThroughHole) -> list[int]:
            return [
                n
                for n, (u, v, w) in nodes.items()
                if h.diameter / 2 + 0.05 < math.hypot(u - h.u, v - h.v) <= h.countersink_diameter / 2 + 0.05
                and w < (h.countersink_diameter - h.diameter) / 2 + 0.05
            ]

        for h in joints:
            add(hole_wall(h), (0.0, -load / len(joints), 0.0))
        for h in joints:
            if id(h) in tensions:
                add(countersink(h), (0.0, 0.0, tensions[id(h)]))
        # The left ear starts at the side wall's inner face, so the wall's front edge bears on u in [0, WALL_THICKNESS].
        bearing = [
            n
            for n, (u, v, w) in nodes.items()
            if abs(w - ear.thickness) < 0.05 and u <= WALL_THICKNESS and abs(v - bearing_v) <= BEARING_HALF_HEIGHT
        ]
        add(bearing, (0.0, 0.0, -couple))
        _write_deck(work / "ear.inp", nodes, elements, fixed, {n: (f[0], f[1], f[2]) for n, f in forces.items()})
        subprocess.run([CCX, "-i", "ear"], cwd=work, check=True, capture_output=True, timeout=SOLVER_TIMEOUT)
        displacement, stresses = _results(work / "ear.dat")
    return EarResult(
        design=name,
        load_n=load,
        moment_nmm=moment,
        max_displacement=displacement,
        in_layer=_percentile([von_mises(s) for s in stresses]),
        across_layer_tension=_percentile([max(0.0, s[2]) for s in stresses]),
        interlayer_shear=_percentile([math.hypot(s[4], s[5]) for s in stresses]),
    )


@dataclass(frozen=True)
class WallResult:
    design: str
    bending_stress: float
    """MPa, in-plane (along the layers) at the ear joint, where the wall's moment peaks."""

    @property
    def factor(self) -> float:
        return PLA.in_layer_strength / self.bending_stress


def wall_bending(name: str, chassis: RackChassis) -> WallResult:
    """Each side wall is a deep beam cantilevered from its ear, carrying half the chassis in its own plane.

    Closed form (sigma = 6M / t h^2): the wall is a plain rectangle there, and its seams are bridged by
    the floor and cover (their seams are staggered against the wall's).
    """
    load = chassis_mass(chassis) * GRAVITY / 2
    moment = load * chassis.depth / 2
    height = chassis.height - 2 * FLOOR_THICKNESS
    return WallResult(name, 6 * moment / (WALL_THICKNESS * height**2))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    builders = reference_builders()
    names = sys.argv[1:] or [n for n in builders if n.startswith("chassis_")]
    failed = False
    for name in names:
        design = builders[name]()
        assert isinstance(design, RackChassis)
        r = analyse_ear(name, design)
        failed |= not r.passes
        logger.info(
            "%s: ear carries %.0f N + %.1f N.m; deflection %.2f mm; in-layer %.1f MPa (x%.1f); "
            "across layers %.2f MPa tension, %.2f MPa shear (x%.1f) -> %s",
            name,
            r.load_n,
            r.moment_nmm / 1000,
            r.max_displacement,
            r.in_layer,
            r.in_layer_factor,
            r.across_layer_tension,
            r.interlayer_shear,
            r.interlayer_factor,
            "OK" if r.passes else "BELOW x2",
        )
        wall = wall_bending(name, design)
        failed |= wall.factor < SAFETY_FACTOR
        logger.info("%s: side wall in-plane bending %.1f MPa (x%.1f)", name, wall.bending_stress, wall.factor)
    raise SystemExit(1 if failed else 0)
