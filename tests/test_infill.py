# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parts checked as printed: a solid shell of perimeters and skins around a sparse infill core."""

import dataclasses
from pathlib import Path

import pytest

from modularack.build import bill_of_materials
from modularack.fea import (
    SAFETY_FACTOR,
    _mesh_regions,
    ear_as_printed,
    printed_ear_bounds,
    printed_wall_bending,
    wall_as_printed,
    wall_bending,
)
from modularack.infill import split, wall_section_modulus
from modularack.plate import Plate
from modularack.print_settings import PRUSA_MK3_QUALITY, SOLID, STRUCTURAL
from modularack.reference import chassis_10_inch, chassis_19_inch


def _ear(units: int = 1) -> Plate:
    chassis = chassis_19_inch(units)
    ear = chassis.children[f"{chassis.name}_left_ear"]
    assert isinstance(ear, Plate)
    return ear


def test_shell_and_core_make_up_the_whole_part() -> None:
    ear = _ear()
    shell, core = split(ear, STRUCTURAL)
    assert shell.volume + core.volume == pytest.approx(ear.solids()["plate"].volume, rel=1e-6)
    overlap = shell & core  # None when they do not overlap at all
    assert overlap is None or overlap.volume < 1e-3


def test_thick_perimeters_that_cut_the_core_apart_still_mesh(tmp_path: Path) -> None:
    # At 6 perimeters the rings round the screw holes meet the outer ones and split the core in pieces.
    shell, core = split(_ear(), dataclasses.replace(STRUCTURAL, perimeters=6))
    _nodes, elements, core_elements = _mesh_regions(shell, core, tmp_path)
    assert 0 < len(core_elements) < len(elements)


def test_a_wall_with_no_core_left_is_as_stiff_as_solid() -> None:
    full = dataclasses.replace(STRUCTURAL, bottom_layers=20, top_layers=25)  # 9 mm of skin
    assert wall_section_modulus(9.0, 30.0, full, 0.0) == pytest.approx(9.0 * 30.0**2 / 6, rel=1e-6)


def test_the_stock_profile_is_too_thin_for_an_ear() -> None:
    # Even the stiffest infill PrusaSlicer's stock MK3 profile could lay leaves the 19" 1U ear short of
    # twice its two-post load across the layers; with the core ignored it is far short. Hence SOLID ears.
    empty, stiffest = printed_ear_bounds("chassis_19in_1U", chassis_19_inch(1), PRUSA_MK3_QUALITY)
    assert stiffest.shell.interlayer_factor < SAFETY_FACTOR
    assert empty.shell.interlayer_factor < stiffest.shell.interlayer_factor


def test_every_ear_is_printed_solid_and_holds_twice_its_load() -> None:
    for chassis in (chassis_19_inch(1), chassis_10_inch(1), chassis_19_inch(4)):
        for side in ("left", "right"):
            assert chassis.children[f"{chassis.name}_{side}_ear"].print_settings is SOLID
    assert ear_as_printed("chassis_19in_1U", chassis_19_inch(1)).passes


def test_side_walls_hold_twice_their_load_as_printed_with_the_infill_ignored() -> None:
    for chassis in (chassis_19_inch(1), chassis_10_inch(1), chassis_19_inch(4)):
        printed = wall_as_printed(chassis.name, chassis)
        assert printed.factor >= SAFETY_FACTOR
        assert printed.factor < wall_bending(chassis.name, chassis).factor
    # Full-height walls are deep enough that even the stock two perimeters hold the 19 in 1U chassis,
    # though with less margin than the four the walls are printed with.
    one_u = chassis_19_inch(1)
    stock = printed_wall_bending(one_u.name, one_u, PRUSA_MK3_QUALITY).factor
    assert SAFETY_FACTOR <= stock < wall_as_printed(one_u.name, one_u).factor


def test_the_bill_of_materials_states_each_parts_print_settings() -> None:
    chassis = chassis_10_inch(1)
    bom = bill_of_materials(chassis, chassis.hardware)
    assert f"- {chassis.name}_left_ear (solid: 100% infill)" in bom
    assert "structural: 4 perimeters" in bom
