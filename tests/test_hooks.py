# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less mounting in square-hole racks, printed upright, and one-piece corners."""

import pytest
from build123d import Pos

from zephyrack.chassis import EarStyle, RackChassis
from zephyrack.checks import check
from zephyrack.hooks import (
    HOOK_DROP,
    HOOK_PEG_HEIGHT,
    HOOK_VERTICAL_CLEARANCE,
    SQUARE_HOLE,
    RackHook,
    RackPeg,
    SpringHook,
    blade_strain,
    hook_width,
    spring_blades,
)
from zephyrack.plate import Edge, EdgeInsert, Plate
from zephyrack.reference import chassis_10_inch, chassis_19_inch
from zephyrack.standards import RACK_10_INCH, RACK_19_INCH, RackStandard


def _ear(chassis: RackChassis, side: str = "left") -> Plate:
    ear = chassis.children[f"{chassis.name}_{side}_ear"]
    assert isinstance(ear, Plate)
    return ear


@pytest.mark.parametrize("rack", [RACK_10_INCH, RACK_19_INCH])
def test_a_hook_fits_its_square_hole_in_any_rack_of_that_width(rack: RackStandard) -> None:
    # Both ears' hooks must fit together across the whole spread of real hole spacings.
    assert hook_width(rack) + rack.hole_spacing_tolerance < SQUARE_HOLE
    assert pytest.approx(SQUARE_HOLE) == HOOK_PEG_HEIGHT + HOOK_DROP + HOOK_VERTICAL_CLEARANCE


def test_the_spring_blades_stay_well_inside_the_plastics_elastic_range() -> None:
    assert blade_strain() < 0.02


@pytest.mark.parametrize("style", [EarStyle.HOOK, EarStyle.SNAP])
@pytest.mark.parametrize("units", [1, 3])
def test_mounts_sit_in_the_eia_hole_column(style: EarStyle, units: int) -> None:
    chassis = chassis_19_inch(units, style)
    for side in ("left", "right"):
        ear = _ear(chassis, side)
        mounts = [f for f in ear.features if isinstance(f, RackHook | RackPeg | SpringHook)]
        # A hook, peg or the spring hook in every hole.
        assert len(mounts) == 3 * units
        assert sum(isinstance(f, SpringHook) for f in mounts) == (1 if style is EarStyle.SNAP else 0)
        for mount in mounts:
            u = (mount.band[0] + mount.band[1]) / 2
            centre = ear.placement * Pos(u, mount.hole_v, 0)
            assert abs(centre.position.Y) == pytest.approx(RACK_19_INCH.hole_spacing / 2, abs=1e-6)


def test_the_spring_hook_sits_in_the_top_u_top_hole() -> None:
    chassis = chassis_19_inch(2, EarStyle.SNAP)
    ear = _ear(chassis)
    spring = next(f for f in ear.features if isinstance(f, SpringHook))
    assert spring.hole_v > ear.width - SQUARE_HOLE


@pytest.mark.parametrize("build", [chassis_10_inch, chassis_19_inch])
def test_the_spring_hook_hangs_on_its_blades_alone(build) -> None:  # type: ignore[no-untyped-def]
    # Cut the two blades and the block and its lip come away from the ear in one piece.
    ear = _ear(build(1, EarStyle.SNAP))
    spring = next(f for f in ear.features if isinstance(f, SpringHook))
    freed = ear.body() - spring_blades(spring, ear)
    assert len(freed.solids()) == 2


@pytest.mark.parametrize("style", [EarStyle.HOOK, EarStyle.SNAP])
def test_square_hole_ears_print_upright(style: EarStyle) -> None:
    chassis = chassis_19_inch(1, style)
    part = chassis.printable_parts()[f"{chassis.name}_left_ear"]
    # Standing on the chassis's top edge: the print is as tall as the chassis.
    assert chassis.height - 1e-6 <= part.bounding_box().size.Z <= chassis.height + HOOK_DROP  # a lip may reach below


@pytest.mark.parametrize("style", list(EarStyle))
def test_a_one_piece_corner_prints_as_one_upright_part(style: EarStyle) -> None:
    chassis = RackChassis(RACK_10_INCH, 1, 380, ear_style=style, one_piece=True)
    chassis.build()
    parts = chassis.printable_parts()
    segment = chassis.left_wall.segments[(0, 0)]
    assert f"{chassis.name}_left_ear" not in parts
    corner = parts[segment.name]
    assert corner.is_valid and len(corner.solids()) == 1
    assert chassis.height - 1e-6 <= corner.bounding_box().size.Z <= chassis.height + HOOK_DROP
    # Nothing joins the ear to its wall: no inserts in the wall's front edge.
    assert not any(isinstance(f, EdgeInsert) and f.edge is Edge.U0 for f in segment.features)
    report = check(chassis)
    assert report.clean, report
