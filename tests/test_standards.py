# SPDX-License-Identifier: AGPL-3.0-or-later
from itertools import pairwise

import pytest

from zephyrack.standards import (
    ATX,
    CEB,
    DRIVE_2_5,
    DRIVE_3_5,
    EEB,
    HOLE_POSITIONS_FROM_C,
    MICRO_ATX,
    MINI_ITX,
    MM_PER_INCH,
    RACK_10_INCH,
    RACK_19_INCH,
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


def test_drive_dimensions_match_their_sff_tables() -> None:
    # SFF-8301 Rev 1.9 Table 3-1: A3 101.60, A1 26.10, A2 147.00, A8 28.50, A9 101.60, A10 6.35.
    assert (DRIVE_3_5.width, DRIVE_3_5.height, DRIVE_3_5.length) == (101.6, 26.10, 147.0)
    assert DRIVE_3_5.side_hole_offsets == pytest.approx((28.50, 130.10))
    assert DRIVE_3_5.side_hole_height == 6.35
    # SFF-8201 Rev 3.4 Table 3-1: A4 69.85, A1 15.00, A6 100.45, A52 14.00, A53 90.60, A23 3.00.
    assert (DRIVE_2_5.width, DRIVE_2_5.height, DRIVE_2_5.length) == (69.85, 15.0, 100.45)
    assert DRIVE_2_5.side_hole_offsets == (14.0, 90.6)
    assert DRIVE_2_5.side_hole_height == 3.0


def test_rack_openings_follow_the_19_inch_post_geometry() -> None:
    assert RACK_19_INCH.opening == pytest.approx(450.0)
    assert RACK_10_INCH.opening == pytest.approx(236.525 - 15.1)


def test_eeb_holes_match_ssi_figure_2() -> None:
    # SSI EEB 2011 v1.0.1 Figure 2: datum A is 16.51 mm from the left edge, 10.16 from the rear.
    holes = EEB.hole_positions()
    a = (16.51, 10.16)
    expected = {
        MountingHole.A: (0.0, 0.0),
        MountingHole.C: (124.46, 0.0),
        MountingHole.F: (281.94, 22.86),
        MountingHole.G: (0.0, 154.94),
        MountingHole.H: (124.46, 154.94),
        MountingHole.J: (281.94, 154.94),
        MountingHole.K: (0.0, 227.33),
        MountingHole.L: (124.46, 227.33),
        MountingHole.M: (281.94, 227.33),
        MountingHole.X: (-5.08, 312.42),
        MountingHole.Y: (124.46, 312.42),
        MountingHole.Z: (281.94, 312.42),
    }
    assert set(holes) == set(expected)
    for hole, (dx, dy) in expected.items():
        assert rounded(holes[hole]) == (round(a[0] + dx, 2), round(a[1] + dy, 2)), hole
    assert set(CEB.holes) == set(ATX.holes)


def test_eeb_alternates_sit_where_figure_2_puts_them() -> None:
    c = HOLE_POSITIONS_FROM_C
    assert c[MountingHole.F_ALT] == (157.48, 0.0)
    assert c[MountingHole.H_ALT] == pytest.approx((78.74 - 124.46, 177.8))
    assert c[MountingHole.J_ALT] == (157.48, 181.61)
    assert c[MountingHole.Y_ALT] == pytest.approx((78.74 - 124.46, 312.42))
