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
from .chassis import RackChassis
from .fea import (
    GRAVITY,
    SAFETY_FACTOR,
    EarProblem,
    EarResult,
    _layer_axis,
    _mesh,
    _summarise,
    chassis_mass,
    solve_calculix,
)
from .plate import Plate

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
        f"{label}_{units}U_toolless_box": partial(build, units, toolless_box=True)
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


if __name__ == "__main__":
    main()
