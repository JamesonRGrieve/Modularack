# SPDX-License-Identifier: AGPL-3.0-or-later
"""Knee braces: struts from a square hole lower down the post that prop a chassis's side walls."""

import pytest
from build123d import Pos, Vector

from zephyrack.braces import KneeBrace, anchor_height
from zephyrack.chassis import EarStyle, RackChassis
from zephyrack.checks import check
from zephyrack.fea import SAFETY_FACTOR, Brace, StrutLayout, analyse_corner, knee_brace_strut
from zephyrack.hooks import SQUARE_HOLE
from zephyrack.printability import overhangs
from zephyrack.reference import chassis_10_inch, chassis_19_inch
from zephyrack.standards import RACK_19_INCH


@pytest.mark.parametrize(
    ("build", "style", "units"),
    [(chassis_19_inch, EarStyle.SNAP, 2), (chassis_10_inch, EarStyle.HOOK, 1), (chassis_19_inch, EarStyle.SCREW, 1)],
)
def test_a_braced_chassis_prints_and_assembles(build, style: EarStyle, units: int) -> None:  # type: ignore[no-untyped-def]
    chassis = build(1, style, True, units)
    report = check(chassis)
    assert report.clean, report
    strut = chassis.printable_parts()[f"{chassis.name}_left_knee_brace"]
    assert strut.is_valid and len(strut.solids()) == 1
    assert not overhangs(strut)


@pytest.mark.parametrize("units", [1, 2])
def test_the_strut_seats_in_the_anchor_hole(units: int) -> None:
    chassis = chassis_19_inch(1, EarStyle.HOOK, True, units)
    for side in ("left", "right"):
        brace = chassis.children[f"{chassis.name}_{side}_knee_brace"]
        assert isinstance(brace, KneeBrace)
        strut = brace.solids()["part"]
        hole = Pos(brace.post_face_x, brace.hole_y, anchor_height(units))
        # The peg is in the hole (in front of and behind the post's face) and rests on its bottom edge.
        assert strut.is_inside(hole.position + Vector(1.0, 0.0, 0.0))
        assert pytest.approx(anchor_height(units) - SQUARE_HOLE / 2, abs=0.6) == strut.bounding_box().min.Z
        assert abs(brace.hole_y) == pytest.approx(RACK_19_INCH.hole_spacing / 2)


def test_braces_anchor_one_or_two_units_down() -> None:
    with pytest.raises(ValueError, match="1 or 2 units"):
        RackChassis(RACK_19_INCH, 1, 470, knee_brace_units=3).build()


@pytest.mark.parametrize("units", [1, 2])
def test_the_strut_holds_its_load_and_does_not_buckle(units: int) -> None:
    result = knee_brace_strut("19in 4U", chassis_19_inch(4, EarStyle.HOOK, True, units))
    assert result.passes
    assert result.buckling_factor >= SAFETY_FACTOR


def test_a_knee_brace_two_units_down_lifts_the_snap_corner_past_twice_its_load() -> None:
    # Unbraced, the 19 in 1U snap corner reaches only about x1.0 / x0.8 hung from two posts.
    chassis = chassis_19_inch(1, EarStyle.SNAP, True, 2)
    result = analyse_corner("19in 1U snap braced", chassis, Brace.STRUT, StrutLayout(2, False))
    assert result.in_layer_factor >= SAFETY_FACTOR
    assert result.interlayer_factor >= SAFETY_FACTOR
