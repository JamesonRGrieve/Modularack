# SPDX-License-Identifier: AGPL-3.0-or-later
"""FEA of the tool-less box's dovetails: the tab on a side wall's bottom edge, and the floor's lip over it.

When the chassis hangs from its ears, the walls carry the floor and everything on it through these tabs.
Each tab is solved twice, in CalculiX on the same pipeline as the ears (`fea`), with stresses read in the
print frame:

- **tab**: a slice of the wall around one tab, held at its top cut. The floor's lip bears on the tab's
  45 degree flank, pushing it down and inward; the groove's inner side holds it from moving inward.
- **lip**: a slice of the floor around one groove, held at its cut toward the chassis's middle. The tab
  bears up and outward on the groove's flank and inward on its inner side.

The demand is the whole chassis (`fea.chassis_mass`, an upper bound: the walls, cover and ears don't
hang on the tabs) shared evenly by the tabs on both sides. Being linear, one solve at a reference load
gives each tab's capacity at the x2 safety factor.
"""

from __future__ import annotations

import argparse
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

from build123d import Box, Part, Pos, export_step

from . import lid, toolless
from . import sled as sl
from .cassette import Cassette
from .chassis import RackChassis
from .fea import (
    GRAVITY,
    PAYLOAD,
    PLA,
    SAFETY_FACTOR,
    EarProblem,
    EarResult,
    _layer_axis,
    _mesh,
    _summarise,
    chassis_mass,
    solve_calculix,
)
from .plate import Plate, RectCut
from .sled import Sled
from .standards import DRIVE_3_5

REFERENCE_LOAD = 100.0
"""N on one tab: the solve is linear, so capacities scale from it."""
SLICE_MARGIN = 8.0
"""Plastic kept beyond the tab's or groove's ends."""
TAB_SLICE_HEIGHT = 15.0
LIP_SLICE_DEPTH = 20.0
COVER_LIFT = 200.0
"""N pulling the cover straight up (a hand lifting the chassis by its lid): no design load, a margin."""
JOINT_MESH_SIZE = 0.8
JOINT_PEAK_VOLUME = 1.0
"""mm^3: a tab is about 160 mm^3, so the ears' 45 mm^3 would average away its root."""
ON_SURFACE = 0.02


@dataclass(frozen=True)
class JointResult:
    joint: str
    result: EarResult
    demand_n: float
    """N per tab, the chassis hanging from its ears."""

    @property
    def factor(self) -> float:
        """The joint's margin at its demand (x2 passes, as for the ears)."""
        at_reference = min(self.result.in_layer_factor, self.result.interlayer_factor)
        return at_reference * REFERENCE_LOAD / self.demand_n

    @property
    def capacity_n(self) -> float:
        """N one tab carries at x2."""
        return self.factor * self.demand_n / SAFETY_FACTOR


def _box(u0: float, v0: float, w0: float, u1: float, v1: float, w1: float) -> Part:
    return Pos((u0 + u1) / 2, (v0 + v1) / 2, (w0 + w1) / 2) * Box(u1 - u0, v1 - v0, w1 - w0)


def _first(chassis: RackChassis, kind: type, panels: list[str]) -> tuple[Plate, object]:
    for name in panels:
        panel = getattr(chassis, name)
        for plate in panel.segments.values():
            for feature in plate.features:
                if isinstance(feature, kind):
                    return plate, feature
    raise ValueError(f"{chassis.name} has no {kind.__name__}: build it with toolless_box=True")


def tabs_per_side(chassis: RackChassis) -> int:
    return sum(
        isinstance(f, lid.CoverTab) and f.edge_v == 0.0 for p in chassis.left_wall.segments.values() for f in p.features
    )


def demand(chassis: RackChassis) -> float:
    return chassis_mass(chassis) * GRAVITY / (2 * tabs_per_side(chassis))


def tab_problem(chassis: RackChassis, work: Path) -> EarProblem:
    plate, feature = _first(chassis, lid.CoverTab, ["left_wall"])
    assert isinstance(feature, lid.CoverTab)
    t, undercut, reach, top = plate.thickness, lid.TAB_UNDERCUT, lid.TAB_REACH, lid.TAB_TOP
    u0, u1 = max(feature.u0 - SLICE_MARGIN, 0.0), min(feature.u1 + SLICE_MARGIN, plate.length)
    height = min(TAB_SLICE_HEIGHT, plate.width)
    export_step(plate.body() & _box(u0, -reach - 1, -1, u1, height, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    on_tab = [n for n, (u, _, _) in nodes.items() if feature.u0 - 0.01 <= u <= feature.u1 + 0.01]
    flank = [
        n
        for n in on_tab
        if -undercut - 0.01 <= nodes[n][1] <= 0.01 and abs(nodes[n][2] - (undercut + nodes[n][1])) < ON_SURFACE
    ]
    inner = [n for n in on_tab if -reach - 0.01 <= nodes[n][1] <= 0.01 and abs(nodes[n][2] - top) < ON_SURFACE]
    fixed = [n for n, (_, v, _) in nodes.items() if v >= height - ON_SURFACE]
    # The lip bears on the flank, pushing the tab down and inward (+w, toward the inner face).
    loads = [(flank, (0.0, -REFERENCE_LOAD, REFERENCE_LOAD))]
    partial = [(n, 3) for n in inner]
    return EarProblem(
        nodes,
        elements,
        fixed,
        loads,
        REFERENCE_LOAD,
        0.0,
        partial=partial,
        layer_axis=_layer_axis(plate),
        peak_volume=JOINT_PEAK_VOLUME,
    )


def lip_problem(chassis: RackChassis, work: Path) -> EarProblem:
    plate, feature = _first(chassis, toolless.FloorSocket, ["floor"])
    assert isinstance(feature, toolless.FloorSocket)
    t, c = plate.thickness, lid.CLEARANCE
    undercut, reach, top = lid.TAB_UNDERCUT, lid.TAB_REACH + c, lid.TAB_TOP
    drop = c * math.sqrt(2)
    lo = min(*feature.lock, *feature.window)
    hi = max(*feature.lock, *feature.window)
    u0, u1 = max(lo - SLICE_MARGIN, 0.0), min(hi + SLICE_MARGIN, plate.length)
    edge = feature.edge_v - feature.sign * chassis.wall_inset
    inward = feature.edge_v + feature.sign * LIP_SLICE_DEPTH
    v0, v1 = sorted((edge, inward))
    export_step(plate.body() & _box(u0, max(v0, 0.0), -1, u1, min(v1, plate.width), t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    l0, l1 = sorted(feature.lock)

    def profile(n: int) -> tuple[float, float]:
        """(depth below the top face, distance into the wall from its outer face)."""
        _, v, w = nodes[n]
        return t - w, feature.sign * (v - feature.edge_v)

    in_lock = [n for n, (u, _, _) in nodes.items() if l0 - 0.01 <= u <= l1 + 0.01]
    flank = [
        n
        for n in in_lock
        if -0.01 <= profile(n)[0] <= undercut - drop + c + 0.01
        and abs(profile(n)[1] - (undercut - drop - profile(n)[0])) < ON_SURFACE
    ]
    inner = [
        n for n in in_lock if -0.01 <= profile(n)[0] <= reach + 0.01 and abs(profile(n)[1] - (top + c)) < ON_SURFACE
    ]
    fixed = [n for n, (_, v, _) in nodes.items() if abs(v - inward) < ON_SURFACE]
    s = feature.sign
    loads = [(flank, (0.0, -s * REFERENCE_LOAD, REFERENCE_LOAD)), (inner, (0.0, s * REFERENCE_LOAD, 0.0))]
    return EarProblem(
        nodes, elements, fixed, loads, REFERENCE_LOAD, 0.0, layer_axis=_layer_axis(plate), peak_volume=JOINT_PEAK_VOLUME
    )


def cover_tabs(chassis: RackChassis) -> int:
    return sum(isinstance(f, lid.CoverTab) for p in chassis.cover.segments.values() for f in p.features)


def cover_demand(chassis: RackChassis) -> float:
    """N per cover tab: COVER_LIFT pulling the cover up, shared by its tabs."""
    return COVER_LIFT / cover_tabs(chassis)


def cover_lip_problem(chassis: RackChassis, work: Path) -> EarProblem:
    """A slice of a side wall around one cover socket, held at its bottom cut; the cover's tab, pulled
    up, bears on the groove's top face, bending the wall's lip above it."""
    plate, feature = _first(chassis, lid.TabSocket, ["left_wall"])
    assert isinstance(feature, lid.TabSocket)
    t, c = plate.thickness, lid.CLEARANCE
    lo, hi = sorted(feature.lock)
    u0 = max(min(*feature.lock, *feature.window) - SLICE_MARGIN, 0.0)
    u1 = min(max(*feature.lock, *feature.window) + SLICE_MARGIN, plate.length)
    bottom = max(feature.floor_v - TAB_SLICE_HEIGHT, 0.0)
    export_step(plate.body() & _box(u0, bottom, -1, u1, plate.width + 1, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    roof = feature.floor_v + lid.TAB_TOP + c
    depth = lid.TAB_REACH + c
    top_face = [
        n
        for n, (u, v, w) in nodes.items()
        if lo - 0.01 <= u <= hi + 0.01 and abs(v - roof) < ON_SURFACE and t - depth - 0.01 <= w <= t + 0.01
    ]
    fixed = [n for n, (_, v, _) in nodes.items() if abs(v - bottom) < ON_SURFACE]
    loads = [(top_face, (0.0, REFERENCE_LOAD, 0.0))]
    return EarProblem(
        nodes, elements, fixed, loads, REFERENCE_LOAD, 0.0, layer_axis=_layer_axis(plate), peak_volume=JOINT_PEAK_VOLUME
    )


@dataclass(frozen=True)
class LatchResult:
    latch: str
    closed_form_strain: float
    fea_strain: float
    """Peak von Mises stress over modulus, the arm bent by the force the closed form says moves the tooth
    its full travel."""
    free_end_deflection: float
    """mm the arm's free end moves (past the tooth, so more than the tooth's travel)."""
    travel: float


def _latch_force(width: float, thickness: float, lever: float, travel: float) -> float:
    """The tip force that bends a cantilever of that section and length by `travel`."""
    second_moment = thickness * width**3 / 12
    return 3 * PLA.modulus * second_moment * travel / lever**3


def cover_latch_problem(chassis: RackChassis, work: Path) -> tuple[EarProblem, float]:
    """The cover's latch arm in a slice of the cover, held where the slice joins the rest of the cover;
    the wall pushes its tooth inward."""
    plate, tooth = _first(chassis, lid.LatchTooth, ["cover"])
    assert isinstance(tooth, lid.LatchTooth)
    t, o = plate.thickness, tooth.outward
    root = plate.length - lid.LATCH_ARM
    u0 = max(root - SLICE_MARGIN, 0.0)
    inner = tooth.edge_v - o * (lid.LATCH_WIDTH + lid.LATCH_RELIEF + SLICE_MARGIN)
    v0, v1 = sorted((inner, tooth.edge_v + o * (lid.TOOTH + 1)))
    export_step(plate.body() & _box(u0, v0, -1, plate.length + 1, v1, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    face_v = tooth.edge_v + o * lid.TOOTH
    face = [
        n
        for n, (u, v, w) in nodes.items()
        if tooth.u0 - 0.01 <= u <= tooth.u1 + 0.01 and abs(v - face_v) < ON_SURFACE and w >= lid.TOOTH - 0.01
    ]
    fixed = [n for n, (u, v, _) in nodes.items() if u <= u0 + ON_SURFACE or abs(v - inner) < ON_SURFACE]
    lever = plate.length - lid.TOOTH_FROM_END - lid.TOOTH_LENGTH / 2 - root
    travel = lid.TOOTH + lid.CLEARANCE
    force = _latch_force(lid.LATCH_WIDTH, t, lever, travel)
    loads = [(face, (0.0, -o * force, 0.0))]
    problem = EarProblem(
        nodes, elements, fixed, loads, force, 0.0, layer_axis=_layer_axis(plate), peak_volume=JOINT_PEAK_VOLUME
    )
    return problem, travel


def rear_latch_problem(chassis: RackChassis, work: Path) -> tuple[EarProblem, float]:
    """One of the rear wall's latch arms, held below its root; the side wall pushes its tooth inward."""
    plate, tooth = _first(chassis, toolless.SideTooth, ["rear_wall"])
    assert isinstance(tooth, toolless.SideTooth)
    t, o = plate.thickness, tooth.outward
    inner = tooth.edge_u - o * (toolless.REAR_ARM_WIDTH + toolless.REAR_ARM_RELIEF + SLICE_MARGIN)
    u0, u1 = sorted((inner, tooth.edge_u + o * (toolless.REAR_TOOTH + 1)))
    export_step(plate.body() & _box(u0, -1, -1, u1, plate.width + 1, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    face_u = tooth.edge_u + o * toolless.REAR_TOOTH
    face = [
        n
        for n, (u, v, w) in nodes.items()
        if tooth.v0 + toolless.REAR_TOOTH - 0.01 <= v <= tooth.v1 + 0.01 and abs(u - face_u) < ON_SURFACE
    ]
    fixed = [n for n, (u, v, _) in nodes.items() if abs(u - inner) < ON_SURFACE or v <= ON_SURFACE - 0.0]
    lever = (tooth.v0 + tooth.v1) / 2 - toolless.REAR_ARM_ROOT
    travel = toolless.REAR_TOOTH + lid.CLEARANCE
    force = _latch_force(toolless.REAR_ARM_WIDTH, toolless.REAR_TOOTH_THICKNESS, lever, travel) + _latch_force(
        toolless.REAR_ARM_WIDTH, t - toolless.REAR_TOOTH_THICKNESS, lever, travel
    )
    loads = [(face, (-o * force, 0.0, 0.0))]
    problem = EarProblem(
        nodes, elements, fixed, loads, force, 0.0, layer_axis=_layer_axis(plate), peak_volume=JOINT_PEAK_VOLUME
    )
    return problem, travel


def analyse_latches(name: str, chassis: RackChassis) -> list[LatchResult]:
    results = []
    cases = (
        ("cover", cover_latch_problem, lid.latch_strain()),
        ("rear", rear_latch_problem, toolless.rear_latch_strain(chassis.rear_wall.width)),
    )
    for latch, build, closed in cases:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            problem, travel = build(chassis, work)
            displacement, stresses = solve_calculix(problem, work)
            summary = _summarise(f"{name} {latch} latch", problem, displacement, stresses)
        results.append(LatchResult(latch, closed, summary.in_layer / PLA.modulus, displacement, travel))
    return results


def _module_plates(chassis: RackChassis) -> list[tuple[Cassette, int]]:
    """Each drawer module and how many rail tabs (detent included) hold it."""
    out = []
    for c in chassis.children.values():
        if isinstance(c, Cassette):
            n = sum(
                isinstance(f, toolless.RailTab | toolless.DetentBump) for p in (c.left, c.right) for f in p.features
            )
            if n:
                out.append((c, n))
    return out


def rail_demand(chassis: RackChassis) -> float:
    """N per rail tab: the heaviest module (its printed parts solid, plus its drives) lifted at 1 g, as if
    the chassis were turned over, shared by its tabs."""
    worst = 0.0
    for cassette, tabs in _module_plates(chassis):
        grams = sum(part.volume for part in cassette.printable_parts().values()) * PLA.density
        for sled in (d for d in cassette.descendants() if isinstance(d, Sled)):
            grams += PAYLOAD.drive_3_5 if sled.geometry.drive is DRIVE_3_5 else PAYLOAD.drive_2_5
        worst = max(worst, grams * GRAVITY / tabs)
    if not worst:
        raise ValueError(f"{chassis.name} has no drawer modules: build it with toolless_modules=True")
    return worst


def rail_tab_problem(chassis: RackChassis, work: Path) -> EarProblem:
    """A slice of a module's side plate around one rail tab, held at its top cut. Lifted, the tab bears up
    on the groove's far lip: pushed down and toward the near side, held there by the groove's near wall
    (or the neighbour's tab beside it)."""
    plate, feature = _first_cassette(chassis, toolless.RailTab)
    assert isinstance(feature, toolless.RailTab)
    t, undercut, reach, top = plate.thickness, lid.TAB_UNDERCUT, lid.TAB_REACH, lid.TAB_TOP
    u0, u1 = max(feature.u0 - SLICE_MARGIN, 0.0), min(feature.u1 + SLICE_MARGIN, plate.length)
    height = min(TAB_SLICE_HEIGHT, plate.width)
    export_step(plate.body() & _box(u0, -reach - 1, -1, u1, height, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    on_tab = [n for n, (u, _, _) in nodes.items() if feature.u0 - 0.01 <= u <= feature.u1 + 0.01]
    flank = [
        n
        for n in on_tab
        if -undercut - 0.01 <= nodes[n][1] <= 0.01 and abs(nodes[n][2] - (top - nodes[n][1])) < ON_SURFACE
    ]
    near = [n for n in on_tab if -reach - 0.01 <= nodes[n][1] <= 0.01 and abs(nodes[n][2]) < ON_SURFACE]
    fixed = [n for n, (_, v, _) in nodes.items() if v >= height - ON_SURFACE]
    loads = [(flank, (0.0, -REFERENCE_LOAD, -REFERENCE_LOAD))]
    return EarProblem(
        nodes,
        elements,
        fixed,
        loads,
        REFERENCE_LOAD,
        0.0,
        partial=[(n, 3) for n in near],
        layer_axis=_layer_axis(plate),
        peak_volume=JOINT_PEAK_VOLUME,
    )


def rail_lip_problem(chassis: RackChassis, work: Path) -> EarProblem:
    """A slice of the floor around one drawer rail, held at its cut toward the module's middle; a lifted
    tab bears up and outward on the groove's far lip."""
    plate, feature = _first(chassis, toolless.RailGroove, ["floor"])
    assert isinstance(feature, toolless.RailGroove)
    t, c = plate.thickness, lid.CLEARANCE
    undercut, top = lid.TAB_UNDERCUT, lid.TAB_TOP
    drop = c * math.sqrt(2)
    l0, _ = sorted(feature.lock)
    # One tab's stretch of the rail (the tabs share the load evenly), clear of the open front end.
    tab = (max(l0, 0.0) + SLICE_MARGIN, max(l0, 0.0) + SLICE_MARGIN + lid.TAB_LENGTH)
    u0, u1 = tab[0] - SLICE_MARGIN, min(tab[1] + SLICE_MARGIN, plate.length)
    near = feature.edge_v - feature.sign * SLICE_MARGIN
    far = feature.edge_v + feature.sign * LIP_SLICE_DEPTH
    v0, v1 = sorted((near, far))
    export_step(plate.body() & _box(u0, max(v0, 0.0), -1, u1, min(v1, plate.width), t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)

    def profile(n: int) -> tuple[float, float]:
        _, v, w = nodes[n]
        return t - w, feature.sign * (v - feature.edge_v)

    under = [n for n, (u, _, _) in nodes.items() if tab[0] <= u <= tab[1]]
    flank = [
        n
        for n in under
        if -0.01 <= profile(n)[0] <= undercut + c - drop + 0.01
        and abs(profile(n)[1] - (top + profile(n)[0] + drop)) < ON_SURFACE
    ]
    fixed = [n for n, (_, v, _) in nodes.items() if abs(v - far) < ON_SURFACE]
    s = feature.sign
    loads = [(flank, (0.0, s * REFERENCE_LOAD, REFERENCE_LOAD))]
    return EarProblem(
        nodes, elements, fixed, loads, REFERENCE_LOAD, 0.0, layer_axis=_layer_axis(plate), peak_volume=JOINT_PEAK_VOLUME
    )


def _first_cassette(chassis: RackChassis, kind: type) -> tuple[Plate, object]:
    for c in chassis.children.values():
        if isinstance(c, Cassette):
            for plate in (c.left, c.right):
                for f in plate.features:
                    if isinstance(f, kind):
                        return plate, f
    raise ValueError(f"{chassis.name} has no {kind.__name__}: build it with toolless_modules=True")


def detent_problem(chassis: RackChassis, work: Path) -> tuple[EarProblem, float, float]:
    """A drawer's detent arm in a slice of its side plate, held above the relief slot and behind the arm's
    root; the groove floor pushes the nose up by its travel. Returns the problem, the travel and the
    closed-form strain."""
    plate, bump = _first_cassette(chassis, toolless.DetentBump)
    assert isinstance(bump, toolless.DetentBump)
    t, r = plate.thickness, lid.TAB_REACH
    slot = next(f for f in plate.features if isinstance(f, RectCut) and abs(f.v0 - toolless.DETENT_ARM_HEIGHT) < 1e-6)
    root = slot.u1 if bump.front_low else slot.u0
    u0, u1 = (-1.0, root + SLICE_MARGIN) if bump.front_low else (root - SLICE_MARGIN, plate.length + 1)
    top = toolless.DETENT_ARM_HEIGHT + toolless.DETENT_RELIEF + SLICE_MARGIN
    export_step(plate.body() & _box(u0, -r - bump.drop - 1, -1, u1, top, t + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    nose = [
        n
        for n, (u, v, _) in nodes.items()
        if bump.u0 + bump.drop <= u <= bump.u1 - bump.drop and abs(v - (-r - bump.drop)) < ON_SURFACE
    ]
    fixed = [
        n
        for n, (u, v, _) in nodes.items()
        if v >= top - ON_SURFACE or abs(u - (u1 if bump.front_low else u0)) < ON_SURFACE
    ]
    lever = abs(root - (bump.u0 + bump.u1) / 2)
    travel = bump.drop - lid.CLEARANCE
    force = _latch_force(toolless.DETENT_ARM_HEIGHT, t, lever, travel)
    problem = EarProblem(
        nodes,
        elements,
        fixed,
        [(nose, (0.0, force, 0.0))],
        force,
        0.0,
        layer_axis=_layer_axis(plate),
        peak_volume=JOINT_PEAK_VOLUME,
    )
    return problem, travel, toolless.detent_strain(lever, bump.drop)


def pin_arm_problem(chassis: RackChassis, work: Path) -> tuple[EarProblem, float, float]:
    """A pinned sled's front pin arm, in a slice of its rail held at the rail's outer face and beyond the
    arm's root; the drive pushes the pin out by its travel. The sled prints in its own frame, z up."""
    sled = next(d for d in chassis.descendants() if isinstance(d, Sled) and d.geometry.pinned)
    g = sled.geometry
    x, inner_y, inward, free = min(g.pin_arms(), key=lambda a: (a[0], a[2]))
    root = g.pin_arm_root(x, free)
    toward_root = 1.0 if root > free else -1.0
    x0, x1 = sorted((free - 2 * toward_root, root + 6 * toward_root))
    outer_y = inner_y - inward * g.rail_width
    y0, y1 = sorted((outer_y, inner_y + inward * (sl.DRIVE_SIDE_CLEARANCE + sl.PIN_ENGAGE + 1)))
    export_step(sled.solids()["part"] & _box(x0, y0, -1, x1, y1, g.rail_height + 1), work / "part.step")
    nodes, elements, _ = _mesh(work / "part.step", work, JOINT_MESH_SIZE)
    tip_y = inner_y + inward * (sl.DRIVE_SIDE_CLEARANCE + sl.PIN_ENGAGE)
    tip = [n for n, (_, y, _) in nodes.items() if abs(y - tip_y) < ON_SURFACE]
    far = x1 if root > free else x0
    fixed = [n for n, (px, y, _) in nodes.items() if abs(y - outer_y) < ON_SURFACE or abs(px - far) < ON_SURFACE]
    lever = abs(root - x)
    travel = sl.PIN_ENGAGE + sl.PIN_CLEARANCE
    # The skin bends across its 1.6 mm, over the rail's full height.
    force = _latch_force(sl.PIN_ARM_SKIN, g.rail_height, lever, travel)
    problem = EarProblem(
        nodes,
        elements,
        fixed,
        [(tip, (0.0, -inward * force, 0.0))],
        force,
        0.0,
        layer_axis=2,
        peak_volume=JOINT_PEAK_VOLUME,
    )
    return problem, travel, sl.pin_arm_strain()


def analyse_pin_arm(name: str, chassis: RackChassis) -> LatchResult:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        problem, travel, closed = pin_arm_problem(chassis, work)
        displacement, stresses = solve_calculix(problem, work)
        summary = _summarise(f"{name} pin arm", problem, displacement, stresses)
    return LatchResult("sled pin", closed, summary.in_layer / PLA.modulus, displacement, travel)


def analyse_rails(name: str, chassis: RackChassis) -> tuple[list[JointResult], LatchResult]:
    need = rail_demand(chassis)
    results = []
    for joint, build in (("rail tab", rail_tab_problem), ("rail lip", rail_lip_problem)):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            problem = build(chassis, work)
            displacement, stresses = solve_calculix(problem, work)
            results.append(JointResult(joint, _summarise(f"{name} {joint}", problem, displacement, stresses), need))
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        problem, travel, closed = detent_problem(chassis, work)
        displacement, stresses = solve_calculix(problem, work)
        summary = _summarise(f"{name} detent", problem, displacement, stresses)
    return results, LatchResult("detent", closed, summary.in_layer / PLA.modulus, displacement, travel)


def analyse_dovetails(name: str, chassis: RackChassis) -> list[JointResult]:
    results = []
    need = demand(chassis)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        problem = cover_lip_problem(chassis, work)
        displacement, stresses = solve_calculix(problem, work)
        cover = _summarise(f"{name} cover lip", problem, displacement, stresses)
    results.append(JointResult("cover lip", cover, cover_demand(chassis)))
    for joint, build in (("tab", tab_problem), ("lip", lip_problem)):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            problem = build(chassis, work)
            displacement, stresses = solve_calculix(problem, work)
            results.append(JointResult(joint, _summarise(f"{name} {joint}", problem, displacement, stresses), need))
    return results


def main() -> None:
    from functools import partial

    from .reference import chassis_10_inch, chassis_19_inch, reference_builders

    parser = argparse.ArgumentParser(description="FEA of the tool-less box's dovetails")
    parser.add_argument("designs", nargs="*", help="reference designs; default: every width and height, tool-less")
    args = parser.parse_args()
    builders = reference_builders()
    sweep = {
        f"{label}_{units}U_toolless_box": partial(
            build, units, toolless_box=True, toolless_modules=True, toolless_sleds=True
        )
        for label, build in (("chassis_10in", chassis_10_inch), ("chassis_19in", chassis_19_inch))
        for units in range(1, 5)
    }
    builders.update(sweep)
    args.designs = args.designs or list(sweep)
    print(f"{'design':32} {'joint':9} {'N/tab':>7} {'MPa@100N':>9} {'across':>8} {'capacity N':>11} {'factor':>7}")
    for design in args.designs:
        chassis = builders[design]()
        assert isinstance(chassis, RackChassis)
        for r in sorted(analyse_dovetails(design, chassis), key=lambda r: r.joint):
            e = r.result
            print(
                f"{design:32} {r.joint:9} {r.demand_n:7.1f} {e.in_layer:9.2f} "
                f"{max(e.interlayer_shear, e.interlayer_combined):8.2f} {r.capacity_n:11.0f} {r.factor:7.1f}"
            )
        if chassis.toolless_modules:
            rails, detent = analyse_rails(design, chassis)
            for r in rails:
                e = r.result
                print(
                    f"{design:32} {r.joint:9} {r.demand_n:7.1f} {e.in_layer:9.2f} "
                    f"{max(e.interlayer_shear, e.interlayer_combined):8.2f} {r.capacity_n:11.0f} {r.factor:7.1f}"
                )
            print(
                f"{design:32} detent: strain {detent.fea_strain:.2%} FEA vs {detent.closed_form_strain:.2%} closed form"
            )
        if chassis.toolless_sleds:
            pin = analyse_pin_arm(design, chassis)
            print(
                f"{design:32} sled pin arm: strain {pin.fea_strain:.2%} FEA vs {pin.closed_form_strain:.2%} closed form"
            )
        for latch in analyse_latches(design, chassis):
            print(
                f"{design:32} {latch.latch} latch: strain {latch.fea_strain:.2%} FEA vs {latch.closed_form_strain:.2%} "
                f"closed form; free end moves {latch.free_end_deflection:.2f} mm for {latch.travel:.2f} mm at the tooth"
            )


if __name__ == "__main__":
    main()
