# SPDX-License-Identifier: AGPL-3.0-or-later
from itertools import pairwise

import pytest

from zephyrack.standards import (
    ATX,
    MICRO_ATX,
    MINI_ITX,
    MM_PER_INCH,
    MotherboardFormFactor,
    MountingHole,
    panel_height,
    rack_hole_heights,
)


def inches(*values: float) -> tuple[float, ...]:
    return tuple(round(v * MM_PER_INCH, 2) for v in values)


def rounded(position: tuple[float, float]) -> tuple[float, ...]:
    return tuple(round(v, 2) for v in position)


def test_mini_itx_holes_match_spec_figure_3() -> None:
    # Mini-ITX 1.1 Figure 3: C at 0.25 in / 0.40 in, F 6.20 right and 0.90 down, H/J 6.10 down.
    holes = MINI_ITX.hole_positions()
    assert set(holes) == {MountingHole.C, MountingHole.F, MountingHole.H, MountingHole.J}
    assert rounded(holes[MountingHole.C]) == inches(0.25, 0.40)
    assert rounded(holes[MountingHole.F]) == inches(6.45, 1.30)
    assert rounded(holes[MountingHole.H]) == inches(0.25, 6.50)
    assert rounded(holes[MountingHole.J]) == inches(6.45, 6.50)


def test_micro_atx_holes_match_spec_figure_3() -> None:
    # microATX 1.2 Figure 3, datum B at 1.350 in / 0.400 in from the rear-left corner.
    holes = MICRO_ATX.hole_positions()
    b = (1.350, 0.400)
    expected = {
        MountingHole.B: (0.0, 0.0),
        MountingHole.C: (1.800, 0.0),
        MountingHole.F: (8.000, 0.900),
        MountingHole.R: (-0.800, 6.100),
        MountingHole.S: (0.0, 6.100),
        MountingHole.H: (1.800, 6.100),
        MountingHole.J: (8.000, 6.100),
        MountingHole.L: (1.800, 8.950),
        MountingHole.M: (8.000, 8.950),
    }
    assert set(holes) == set(expected)
    for hole, (dx, dy) in expected.items():
        assert rounded(holes[hole]) == inches(b[0] + dx, b[1] + dy), hole


def test_atx_holes_match_spec_figure_3() -> None:
    # ATX 2.2 Figure 3, datum A at 0.650 in / 0.400 in from the rear-left corner.
    holes = ATX.hole_positions()
    a = (0.650, 0.400)
    expected = {
        MountingHole.A: (0.0, 0.0),
        MountingHole.C: (4.900, 0.0),
        MountingHole.F: (11.100, 0.900),
        MountingHole.G: (0.0, 6.100),
        MountingHole.H: (4.900, 6.100),
        MountingHole.J: (11.100, 6.100),
        MountingHole.K: (0.0, 8.950),
        MountingHole.L: (4.900, 8.950),
        MountingHole.M: (11.100, 8.950),
    }
    assert set(holes) == set(expected)
    for hole, (dx, dy) in expected.items():
        assert rounded(holes[hole]) == inches(a[0] + dx, a[1] + dy), hole


@pytest.mark.parametrize("form_factor", [MINI_ITX, MICRO_ATX, ATX])
def test_every_hole_lies_on_its_board(form_factor: MotherboardFormFactor) -> None:
    for x, y in form_factor.hole_positions().values():
        assert 0 < x < form_factor.width
        assert 0 < y < form_factor.depth


def test_panel_height_deducts_one_thirty_second_inch() -> None:
    assert panel_height(1) == pytest.approx(43.66)
    assert panel_height(4) == pytest.approx(4 * 44.45 - 0.79)
    with pytest.raises(ValueError):
        panel_height(0)


def test_rack_holes_follow_the_half_five_eighths_pattern() -> None:
    heights = rack_hole_heights(2)
    assert heights == pytest.approx([6.35, 22.225, 38.1, 50.8, 66.675, 82.55])
    gaps = [round(b - a, 3) for a, b in pairwise(heights)]
    assert gaps == [15.875, 15.875, 12.7, 15.875, 15.875]
