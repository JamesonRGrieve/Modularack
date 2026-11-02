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
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np
from build123d import Compound, Part, export_step
from skfem import Basis, ElementTetP1, ElementVector, MeshTet1, asm, condense, solve
from skfem.models.elasticity import lame_parameters, linear_elasticity

from .chassis import FLOOR_THICKNESS, WALL_THICKNESS, RackChassis
from .hooks import (
    FLANGE_GAP,
    HOOK_DROP,
    SPRING_BODY_WIDTH,
    SPRING_LIP_DEPTH,
    SQUARE_HOLE,
    RackHook,
    RackPeg,
    SpringHook,
    hook_back,
    peg_back,
    spring_catch,
)
from .infill import EMPTY_CORE, split, voigt_core, wall_section_modulus
from .plate import Plate, Slot, ThroughHole
from .print_settings import PrintSettings
from .reference import reference_builders
from .sled import Sled
from .standards import DRIVE_3_5, POST_INNER_EDGE_TO_HOLE

logger = logging.getLogger(__name__)

GMSH = os.environ.get("ZEPHYRACK_GMSH", "/opt/gmsh-4.15.2-Linux64/bin/gmsh")
CCX = os.environ.get("ZEPHYRACK_CCX", "/opt/calculix-freecad-1.1.4/bin/ccx")
SOLVER_TIMEOUT = 1800
MESH_SIZE = 1.5
"""Largest tetrahedron edge, mm."""
MESH_RETRY_SCALE = 0.85


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


def _mesh(source: Path, work: Path) -> tuple[dict[int, tuple[float, float, float]], list[list[int]], list[int]]:
    """Second-order tetrahedra of a STEP (or a .geo merging several), with each element's volume tag."""
    msh = work / "part.msh"
    # gmsh's 3D mesher occasionally gives up on a thin sliver; a slightly finer mesh gets past it.
    for size in (MESH_SIZE, MESH_SIZE * MESH_RETRY_SCALE):
        result = subprocess.run(
            [
                GMSH,
                str(source),
                "-3",
                "-order",
                "2",
                "-clmax",
                str(size),
                # Curved second-order elements on small holes can invert; straighten them out.
                "-setnumber",
                "Mesh.HighOrderOptimize",
                "2",
                "-format",
                "msh2",
                "-o",
                str(msh),
            ],
            capture_output=True,
            text=True,
            timeout=SOLVER_TIMEOUT,
        )
        if result.returncode == 0:
            break
    else:
        raise RuntimeError(f"gmsh failed on {source.name}: {result.stdout[-1000:]}")
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: list[list[int]] = []
    volumes: list[int] = []
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
            volumes.append(int(fields[4]))  # tags: physical, elementary (the volume)
        i += 1
    return nodes, elements, volumes


def _mesh_regions(shell: Part, core: Part, work: Path) -> tuple[dict[int, Vector3], list[list[int]], frozenset[int]]:
    """One conformal mesh of shell and core, and which elements are the core's."""
    export_step(Compound([shell, core]), work / "parts.step")
    (work / "part.geo").write_text('SetFactory("OpenCASCADE");\nMerge "parts.step";\nCoherence;\n')
    nodes, elements, volumes = _mesh(work / "part.geo", work)
    # gmsh numbers the fragments itself, and thick perimeters can cut the core into several pieces:
    # each volume belongs to the core if one of its elements sits inside the core solid.
    probe: dict[int, Vector3] = {}
    for element, volume in zip(elements, volumes, strict=True):
        if volume not in probe:
            corners = np.array([nodes[n] for n in element[:4]])
            x, y, z = corners.mean(axis=0)
            probe[volume] = (float(x), float(y), float(z))
    core_tags = {tag for tag, point in probe.items() if core.is_inside(point)}
    if not core_tags or core_tags == set(probe):
        raise RuntimeError("Could not tell the shell's elements from the core's")
    return nodes, elements, frozenset(k for k, v in enumerate(volumes) if v in core_tags)


DECK_FORMAT = ".10g"
"""CalculiX reads numbers from 20-character fields: full-precision floats like -5.349609493123235e-05
overflow them and the card is rejected."""


def _write_deck(
    path: Path,
    nodes: dict[int, tuple[float, float, float]],
    elements: list[list[int]],
    kind: str,
    fixed: list[int],
    forces: dict[int, tuple[float, float, float]],
    core: frozenset[int] = frozenset(),
    core_fraction: float = 1.0,
    partial: list[tuple[int, int]] | None = None,
) -> None:
    lines = ["*NODE"] + [f"{n},{x:{DECK_FORMAT}},{y:{DECK_FORMAT}},{z:{DECK_FORMAT}}" for n, (x, y, z) in nodes.items()]
    lines += ["*NSET, NSET=NALL"] + [str(n) for n in nodes]
    lines.append(f"*ELEMENT, TYPE={kind}, ELSET=EALL")
    lines += [f"{k + 1}," + ",".join(str(n) for n in e) for k, e in enumerate(elements)]
    lines += ["*ELSET, ELSET=SHELL"] + [str(k + 1) for k in range(len(elements)) if k not in core]
    if fixed:
        lines += ["*NSET, NSET=FIXED"] + [str(n) for n in fixed]
    lines += ["*MATERIAL, NAME=PLA", "*ELASTIC", f"{PLA.modulus},{PLA.poisson}"]
    lines += ["*SOLID SECTION, ELSET=SHELL, MATERIAL=PLA"]
    if core:
        lines += ["*ELSET, ELSET=CORE"] + [str(k + 1) for k in sorted(core)]
        lines += ["*MATERIAL, NAME=INFILL", "*ELASTIC", f"{PLA.modulus * core_fraction},{PLA.poisson}"]
        lines += ["*SOLID SECTION, ELSET=CORE, MATERIAL=INFILL"]
    lines += [
        "*STEP",
        "*STATIC",
        "*BOUNDARY",
        *(["FIXED,1,3,0.0"] if fixed else []),
        *(f"{node},{dof},{dof},0.0" for node, dof in partial or []),
        "*CLOAD",
    ]
    for node, vector in forces.items():
        lines += [f"{node},{dof + 1},{value:{DECK_FORMAT}}" for dof, value in enumerate(vector) if value]
    lines += ["*NODE PRINT, NSET=NALL", "U", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    path.write_text("\n".join(lines) + "\n")


def _results(dat: Path) -> tuple[float, list[tuple[float, ...]]]:
    displacement, stresses, _ = _element_results(dat)
    return displacement, stresses


def _element_results(dat: Path) -> tuple[float, list[tuple[float, ...]], list[int]]:
    """Largest displacement, integration-point stresses, and the (0-based) element of each."""
    displacement = 0.0
    stresses: list[tuple[float, ...]] = []
    owners: list[int] = []
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
            owners.append(int(values[0]) - 1)
    return displacement, stresses, owners


def von_mises(s: tuple[float, ...]) -> float:
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy * xy + xz * xz + yz * yz))


BEARING_HALF_HEIGHT = 5.0
POST_BEARING_HEIGHT = 5.0
"""A hook ear's foot bears on the post's face over this height: the pivot of the overturning moment."""
"""The wall's front edge bears on the ear over this half-height around the pivot."""
PEAK_PERCENTILE = 0.995
"""Fallback for stresses that can't be tied to elements (nodal output): the 99.5th percentile."""
PEAK_VOLUME = 45.0
"""mm^3. Point loads and fixed nodes make single-point stress spikes, so the peak reported is the stress
exceeded over the most-stressed 45 mm^3 of plastic: about 0.5 % of a standalone ear, and unlike a
percentile it doesn't drop as more lightly loaded part (a whole wall) joins the model."""


def _percentile(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(PEAK_PERCENTILE * len(ordered)))]


Vector3 = tuple[float, float, float]


@dataclass
class EarProblem:
    """A meshed ear with its supports and loads, independent of the solver that runs it."""

    nodes: dict[int, Vector3]
    elements: list[list[int]]
    """10-node tetrahedra in CalculiX C3D10 node order; the first four are the corners."""
    fixed: list[int]
    loads: list[tuple[list[int], Vector3]]
    """Each load is a total force spread evenly over a set of nodes."""
    load_n: float
    moment_nmm: float
    core: frozenset[int] = frozenset()
    """Elements of the sparse infill core (indices into `elements`); empty for a solid part."""
    partial: list[tuple[int, int]] = field(default_factory=list)
    """(node, dof) pairs held in one direction only (1-3 = u, v, w): bearing contacts."""
    layer_axis: int = 2
    """The plate-frame axis that points up in the print: w for a flat plate, u for an edge-printed one."""

    def corners(self) -> set[int]:
        return {n for e in self.elements for n in e[:4]}

    def nodal_forces(self, allowed: set[int]) -> dict[int, Vector3]:
        """Each load's total spread over those of its nodes the solver's mesh has."""
        forces: dict[int, list[float]] = {}
        for selected, total in self.loads:
            usable = [n for n in selected if n in allowed]
            if not usable:
                raise RuntimeError("A load has no nodes on this mesh")
            for n in usable:
                f = forces.setdefault(n, [0.0, 0.0, 0.0])
                for k in range(3):
                    f[k] += total[k] / len(usable)
        return {n: (f[0], f[1], f[2]) for n, f in forces.items()}


def ear_problem(chassis: RackChassis, work: Path, settings: PrintSettings | None = None) -> EarProblem:
    """The left ear of a chassis hung from its front ears: half the weight, half the overturning moment.

    Solid by default; with print `settings` the ear is meshed as its solid shell and sparse core.
    """
    ear = chassis.children[f"{chassis.name}_left_ear"]
    assert isinstance(ear, Plate)
    load = chassis_mass(chassis) * GRAVITY / 2
    moment = load * chassis.depth / 2
    slots = [f for f in ear.features if isinstance(f, Slot)]
    joints = [f for f in ear.features if isinstance(f, ThroughHole)]
    bearing_v = FLOOR_THICKNESS + BEARING_HALF_HEIGHT
    # The overturning moment pivots the wall about its bottom edge, which bears on the ear; the screws
    # above it take tension in proportion to their height over that pivot (like a bolted flange).
    arms = {id(h): h.v - bearing_v for h in joints if h.v > bearing_v}
    second_moment = sum(a * a for a in arms.values())
    tensions = {key: moment * arm / second_moment for key, arm in arms.items()}
    core: frozenset[int] = frozenset()
    if settings is None:
        export_step(ear.body(), work / "part.step")
        nodes, elements, _ = _mesh(work / "part.step", work)
    else:
        nodes, elements, core = _mesh_regions(*split(ear, settings), work)
    t = ear.thickness
    partial: list[tuple[int, int]] = []
    if any(isinstance(f, RackHook | RackPeg | SpringHook) for f in ear.features):
        fixed, partial = _hook_supports(ear, nodes)
    else:
        fixed = [
            n
            for n, (u, v, w) in nodes.items()
            if any(
                abs(v - s.v) <= s.diameter / 2 + 0.05 and abs(u - s.u) <= s.travel / 2 + s.diameter / 2 + 0.05
                for s in slots
            )
            and 0 < w < t
        ]

    def hole_wall(h: ThroughHole) -> list[int]:
        r = h.diameter / 2
        return [n for n, (u, v, w) in nodes.items() if abs(math.hypot(u - h.u, v - h.v) - r) < 0.05]

    def countersink(h: ThroughHole) -> list[int]:
        return [
            n
            for n, (u, v, w) in nodes.items()
            if h.diameter / 2 + 0.05 < math.hypot(u - h.u, v - h.v) <= h.countersink_diameter / 2 + 0.05
            and w < (h.countersink_diameter - h.diameter) / 2 + 0.05
        ]

    loads: list[tuple[list[int], Vector3]] = [(hole_wall(h), (0.0, -load / len(joints), 0.0)) for h in joints]
    loads += [(countersink(h), (0.0, 0.0, tensions[id(h)])) for h in joints if id(h) in tensions]
    # The left ear starts at the side wall's inner face, so the wall's front edge bears on u in [0, WALL_THICKNESS].
    bearing = [
        n
        for n, (u, v, w) in nodes.items()
        if abs(w - ear.thickness) < 0.05 and u <= WALL_THICKNESS and abs(v - bearing_v) <= BEARING_HALF_HEIGHT
    ]
    loads.append((bearing, (0.0, 0.0, -sum(tensions.values()))))
    layer_axis = _layer_axis(ear)
    return EarProblem(nodes, elements, fixed, loads, load, moment, core, partial, layer_axis)


def _layer_axis(plate: Plate) -> int:
    """The plate-frame axis that points up (or down) in its print: w for a flat plate."""
    if plate.print_up is None:
        return 2
    return 0 if abs(plate.print_up.X) > abs(plate.print_up.Y) else 1


class Brace(StrEnum):
    """Idealised braces for ranking concepts: each adds the support its brace would give."""

    NONE = "none"
    FLANGE_BAR = "flange bar"
    """A rigid bar behind the post's flange holds every peg's and hook's tail back (rearward support)."""
    KNEE = "knee"
    """A strut from the post props the wall's bottom edge at KNEE_DEPTH of the corner's wall (upward support)."""


KNEE_DEPTH = 0.8
"""Where the knee brace meets the wall, as a fraction of the corner's wall length."""
BRACE_PATCH = 5.0


def corner_problem(chassis: RackChassis, work: Path, brace: Brace = Brace.NONE) -> EarProblem:
    """The left one-piece corner (ear and front wall segment, printed as one) hung from its post.

    The rest of the chassis is a rigid lever: at the corner's cut (its splice to the next wall segment)
    it applies half the chassis's weight as shear, plus the couple that brings the moment at the post up
    to that of the whole chassis hung there. Meshed in the ear's frame, so the post supports are the ear's.
    """
    ear = chassis.children[f"{chassis.name}_left_ear"]
    assert isinstance(ear, Plate) and ear.merged_into is not None
    segment = ear.merged_into
    load = chassis_mass(chassis) * GRAVITY / 2
    moment = load * chassis.depth / 2
    part = segment.solids()["plate"].moved(ear.placement.inverse() * segment.placement)
    export_step(part, work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work)
    if any(isinstance(f, RackHook | RackPeg | SpringHook) for f in ear.features):
        fixed, partial = _hook_supports(ear, nodes)
    else:
        slots = [f for f in ear.features if isinstance(f, Slot)]
        fixed = [
            n
            for n, (u, v, w) in nodes.items()
            if any(
                abs(v - s.v) <= s.diameter / 2 + 0.05 and abs(u - s.u) <= s.travel / 2 + s.diameter / 2 + 0.05
                for s in slots
            )
            and 0 < w < ear.thickness
        ]
        partial = []
    if brace is Brace.FLANGE_BAR:
        tails = [_tail(f, ear) for f in ear.features if isinstance(f, RackHook | RackPeg | SpringHook)]
        partial += [
            (n, 3)
            for n, (u, v, w) in nodes.items()
            for (u0, u1), back in tails
            if u0 - 0.05 <= u <= u1 + 0.05 and abs(w - back) < 0.05
        ]
    elif brace is Brace.KNEE:
        prop_w = ear.thickness + KNEE_DEPTH * segment.length
        partial += [
            (n, 2)
            for n, (u, v, w) in nodes.items()
            if abs(v - FLOOR_THICKNESS) < 0.05
            and abs(w - prop_w) <= BRACE_PATCH
            and -0.05 <= u <= WALL_THICKNESS + 0.05
        ]
    # The cut face: the segment's rear end, across the wall's thickness (u in [0, WALL_THICKNESS] here).
    cut_w = ear.thickness + segment.length
    face = [n for n, (u, v, w) in nodes.items() if abs(w - cut_w) < 0.05 and -0.05 <= u <= WALL_THICKNESS + 0.05]
    if not face:
        raise RuntimeError("No nodes on the corner's cut face")
    heights = [nodes[n][1] for n in face]
    centre = sum(heights) / len(heights)
    second = sum((h - centre) ** 2 for h in heights)
    couple = moment - load * segment.length
    loads: list[tuple[list[int], Vector3]] = [(face, (0.0, -load, 0.0))]
    # The couple as a linear spread of force along w over the cut face (like bending stress): top in
    # tension pulling rearward, bottom pushing forward.
    for n in face:
        loads.append(([n], (0.0, 0.0, couple * (nodes[n][1] - centre) / second)))
    return EarProblem(nodes, elements, fixed, loads, load, moment, frozenset(), partial, _layer_axis(segment))


def _tail(feature: RackHook | RackPeg | SpringHook, ear: Plate) -> tuple[tuple[float, float], float]:
    """A mount's hook column and the w of its back face, where a flange bar would hold it."""
    if isinstance(feature, SpringHook):
        lo, hi = sorted(spring_catch(feature, ear))
        return (lo - SPRING_BODY_WIDTH, hi), ear.thickness + FLANGE_GAP + SPRING_LIP_DEPTH
    if isinstance(feature, RackHook):
        return feature.band, hook_back(ear)
    return feature.band, peg_back(ear)


def analyse_corner(name: str, chassis: RackChassis, brace: Brace = Brace.NONE) -> EarResult:
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        problem = corner_problem(chassis, work, brace)
        return _summarise(name, problem, *solve_calculix(problem, work))


def _hook_supports(ear: Plate, nodes: dict[int, Vector3]) -> tuple[list[int], list[tuple[int, int]]]:
    """A square-hole ear hung from a post: each lip held against the back of the flange (rearward, and
    sideways by friction), each weight-bearing hook or peg resting on its hole's bottom edge, and the
    ear's foot bearing on the post's face (the pivot of the overturning moment)."""
    t = ear.thickness
    catch_w = t + FLANGE_GAP
    tol = 0.05
    fixed: list[int] = []
    partial: list[tuple[int, int]] = []
    centres: list[float] = []
    for f in ear.features:
        if isinstance(f, RackHook | RackPeg):
            (u0, u1), edge = f.band, f.hole_v - SQUARE_HOLE / 2
            centres.append((u0 + u1) / 2)
            back = catch_w if isinstance(f, RackHook) else peg_back(ear)
            for n, (u, v, w) in nodes.items():
                if not u0 - tol <= u <= u1 + tol:
                    continue
                if abs(v - edge) < tol and t - tol <= w <= back + tol:
                    # Resting on the hole's bottom edge, held sideways by its sides.
                    partial += [(n, 1), (n, 2)]
                elif isinstance(f, RackHook) and abs(w - catch_w) < tol and edge - HOOK_DROP - tol <= v <= edge + tol:
                    partial += [(n, 1), (n, 3)]
        elif isinstance(f, SpringHook):
            # The lip's catch face, outboard of the block: held rearward only (the blades set it sideways).
            lo, hi = sorted(spring_catch(f, ear))
            v_lo = f.hole_v - SQUARE_HOLE / 2
            for n, (u, v, w) in nodes.items():
                if abs(w - catch_w) < tol and lo - tol <= u <= hi + tol and v >= v_lo - tol:
                    partial.append((n, 3))
    # The left ear's post lies outboard of its hole column's inner edge (larger u).
    post_edge = centres[0] - POST_INNER_EDGE_TO_HOLE
    partial += [
        (n, 3) for n, (u, v, w) in nodes.items() if abs(w - t) < tol and v <= POST_BEARING_HEIGHT and u >= post_edge
    ]
    return fixed, partial


def solve_calculix(problem: EarProblem, work: Path, second_order: bool = True) -> tuple[float, list[tuple[float, ...]]]:
    """Max displacement and integration-point stresses (xx, yy, zz, xy, xz, yz) from CalculiX."""
    if second_order:
        nodes, elements, kind = problem.nodes, problem.elements, "C3D10"
    else:
        corners = problem.corners()
        nodes = {n: xyz for n, xyz in problem.nodes.items() if n in corners}
        elements, kind = [e[:4] for e in problem.elements], "C3D4"
    fixed = [n for n in problem.fixed if n in nodes]
    partial = [(n, dof) for n, dof in problem.partial if n in nodes]
    forces = problem.nodal_forces(set(nodes))
    _write_deck(work / "ear.inp", nodes, elements, kind, fixed, forces, partial=partial)
    subprocess.run([CCX, "-i", "ear"], cwd=work, check=True, capture_output=True, timeout=SOLVER_TIMEOUT)
    return _results(work / "ear.dat")


def solve_scikit_fem(problem: EarProblem) -> tuple[float, list[tuple[float, ...]]]:
    """The same problem on the corner nodes with scikit-fem's linear tetrahedra: an independent solver check."""
    corners = sorted(problem.corners())
    index = {n: k for k, n in enumerate(corners)}
    points = np.array([problem.nodes[n] for n in corners]).T
    tets = np.array([[index[n] for n in e[:4]] for e in problem.elements]).T
    mesh = MeshTet1(points, tets)
    basis = Basis(mesh, ElementVector(ElementTetP1()))
    lam, mu = lame_parameters(PLA.modulus, PLA.poisson)
    stiffness = asm(linear_elasticity(lam, mu), basis)
    load = np.zeros(basis.N)
    for node, vector in problem.nodal_forces(set(corners)).items():
        load[basis.nodal_dofs[:, index[node]]] += vector
    fixed_dofs = basis.nodal_dofs[:, [index[n] for n in problem.fixed if n in index]].ravel()
    displacement = solve(*condense(stiffness, load, D=fixed_dofs))
    magnitude = float(np.sqrt((displacement.reshape(-1, 3) ** 2).sum(axis=1)).max())
    grad = basis.interpolate(displacement).grad  # (3, 3, elements, points)
    strain = 0.5 * (grad + grad.transpose(1, 0, 2, 3))
    trace = strain[0, 0] + strain[1, 1] + strain[2, 2]
    stress = 2 * mu * strain
    for k in range(3):
        stress[k, k] += lam * trace
    rows = np.stack(
        [stress[0, 0], stress[1, 1], stress[2, 2], stress[0, 1], stress[0, 2], stress[1, 2]], axis=-1
    ).reshape(-1, 6)
    return magnitude, [tuple(float(v) for v in row) for row in rows]


LAYER_SHEARS = {0: (3, 4), 1: (3, 5), 2: (4, 5)}
"""Stress components (xx, yy, zz, xy, xz, yz) of the two shears acting on a plane normal to each axis."""


def _summarise(
    name: str,
    problem: EarProblem,
    displacement: float,
    stresses: list[tuple[float, ...]],
    owners: list[int] | None = None,
) -> EarResult:
    """Peak stresses of a solution. `owners` gives each stress's element; without it, stresses are taken
    as element-major integration points of every element, or (if they don't divide evenly) as nodal values."""
    axis = problem.layer_axis
    a, b = LAYER_SHEARS[axis]
    weights = _point_volumes(problem, len(stresses), owners)

    def peak(values: list[float]) -> float:
        return _percentile(values) if weights is None else _peak(values, weights)

    return EarResult(
        design=name,
        load_n=problem.load_n,
        moment_nmm=problem.moment_nmm,
        max_displacement=displacement,
        in_layer=peak([von_mises(s) for s in stresses]),
        across_layer_tension=peak([max(0.0, s[axis]) for s in stresses]),
        interlayer_shear=peak([math.hypot(s[a], s[b]) for s in stresses]),
    )


def _point_volumes(problem: EarProblem, count: int, owners: list[int] | None) -> list[float] | None:
    """The volume each stress sample stands for: its element's, shared among the element's points."""
    if owners is None:
        if count % len(problem.elements):
            return None
        per = count // len(problem.elements)
        owners = [k // per for k in range(count)]
    points = Counter(owners)
    volumes = {e: _tet_volume([problem.nodes[n] for n in problem.elements[e][:4]]) for e in points}
    return [volumes[e] / points[e] for e in owners]


def _tet_volume(corners: list[Vector3]) -> float:
    a, b, c, d = (np.array(p) for p in corners)
    return float(abs(np.dot(b - a, np.cross(c - a, d - a))) / 6)


def _peak(values: list[float], weights: list[float]) -> float:
    """The value exceeded over PEAK_VOLUME of material (or the smallest, if there is less than that)."""
    covered = 0.0
    for value, weight in sorted(zip(values, weights, strict=True), reverse=True):
        covered += weight
        if covered >= PEAK_VOLUME:
            return value
    return min(values)


def analyse_ear(name: str, chassis: RackChassis) -> EarResult:
    """Second-order CalculiX solution of the ear: the result the design is judged on."""
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        problem = ear_problem(chassis, work)
        return _summarise(name, problem, *solve_calculix(problem, work))


def cross_check_ear(name: str, chassis: RackChassis) -> tuple[EarResult, EarResult]:
    """CalculiX C3D4 and scikit-fem P1 on the identical linear mesh and loads, which must agree."""
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        problem = ear_problem(chassis, work)
        calculix = _summarise(name, problem, *solve_calculix(problem, work, second_order=False))
        scikit = _summarise(name, problem, *solve_scikit_fem(problem))
    return calculix, scikit


@dataclass(frozen=True)
class PrintedEarResult:
    """An ear as actually printed: its solid shell judged against the solid allowables, its core against
    allowables scaled by the infill's density (as are its stiffness and the share of each layer it bonds)."""

    settings: PrintSettings
    core_fraction: float
    shell: EarResult
    core: EarResult | None
    """Core stresses divided by the infill density; None when the core is taken as empty."""

    @property
    def passes(self) -> bool:
        return self.shell.passes and (self.core is None or self.core.passes)


def analyse_printed_ear(
    name: str, chassis: RackChassis, settings: PrintSettings, core_fraction: float
) -> PrintedEarResult:
    """The ear meshed as shell and core, the core at `core_fraction` of solid stiffness."""
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        problem = ear_problem(chassis, work, settings)
        fixed = list(problem.fixed)
        forces = problem.nodal_forces(set(problem.nodes))
        _write_deck(
            work / "ear.inp",
            problem.nodes,
            problem.elements,
            "C3D10",
            fixed,
            forces,
            problem.core,
            core_fraction,
            problem.partial,
        )
        subprocess.run([CCX, "-i", "ear"], cwd=work, check=True, capture_output=True, timeout=SOLVER_TIMEOUT)
        displacement, stresses, owners = _element_results(work / "ear.dat")
    in_shell = [(s, e) for s, e in zip(stresses, owners, strict=True) if e not in problem.core]
    core: EarResult | None = None
    if core_fraction > EMPTY_CORE:
        density = settings.infill_density
        in_core = [
            (tuple(v / density for v in s), e) for s, e in zip(stresses, owners, strict=True) if e in problem.core
        ]
        core = _summarise(f"{name} core", problem, displacement, [s for s, _ in in_core], [e for _, e in in_core])
    shell = _summarise(name, problem, displacement, [s for s, _ in in_shell], [e for _, e in in_shell])
    return PrintedEarResult(settings, core_fraction, shell, core)


def printed_ear_bounds(name: str, chassis: RackChassis, settings: PrintSettings) -> list[PrintedEarResult]:
    """The ear with an empty core (the floor for every infill) and with the stiffest possible core."""
    return [
        analyse_printed_ear(name, chassis, settings, EMPTY_CORE),
        analyse_printed_ear(name, chassis, settings, voigt_core(settings.infill_density)),
    ]


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
    height = chassis.height - FLOOR_THICKNESS
    return WallResult(name, 6 * moment / (WALL_THICKNESS * height**2))


def printed_wall_bending(name: str, chassis: RackChassis, settings: PrintSettings) -> WallResult:
    """`wall_bending` with the wall as printed and its core taken as empty: skins and edge perimeters only."""
    load = chassis_mass(chassis) * GRAVITY / 2
    moment = load * chassis.depth / 2
    height = chassis.height - FLOOR_THICKNESS
    return WallResult(name, moment / wall_section_modulus(WALL_THICKNESS, height, settings, EMPTY_CORE))


def ear_as_printed(name: str, chassis: RackChassis) -> EarResult:
    """The ear judged at its own print settings: solid if it is printed solid, else its shell alone."""
    ear = chassis.children[f"{chassis.name}_left_ear"]
    if ear.print_settings.infill_density >= 1:
        return analyse_ear(name, chassis)
    return analyse_printed_ear(name, chassis, ear.print_settings, EMPTY_CORE).shell


def wall_as_printed(name: str, chassis: RackChassis) -> WallResult:
    """The side wall judged at its own print settings, its infill taken as carrying nothing."""
    segment = next(iter(chassis.left_wall.segments.values()))
    return printed_wall_bending(name, chassis, segment.print_settings)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    builders = reference_builders()
    names = sys.argv[1:] or [n for n in builders if n.startswith("chassis_")]
    failed = False
    for name in names:
        design = builders[name]()
        assert isinstance(design, RackChassis)
        r = ear_as_printed(name, design)
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
        wall = wall_as_printed(name, design)
        failed |= wall.factor < SAFETY_FACTOR
        logger.info(
            "%s: side wall as printed (infill ignored), in-plane bending %.1f MPa (x%.1f)",
            name,
            wall.bending_stress,
            wall.factor,
        )
    raise SystemExit(1 if failed else 0)
