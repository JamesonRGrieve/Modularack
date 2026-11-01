# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strength checks on the worst real mounting: a loaded chassis hung from its front ears (two-post).

Needs gmsh and CalculiX (ZEPHYRACK_GMSH / ZEPHYRACK_CCX); the CAD SOP records the desktop installs.
"""

from zephyrack.fea import SAFETY_FACTOR, analyse_ear, wall_bending
from zephyrack.reference import chassis_10_inch, chassis_19_inch


def test_the_19_inch_1u_ear_holds_twice_its_two_post_load() -> None:
    # The shortest, widest chassis has the least lever to resist its overturning moment.
    result = analyse_ear("chassis_19in_1U", chassis_19_inch(1))
    assert result.in_layer_factor >= SAFETY_FACTOR
    assert result.interlayer_factor >= SAFETY_FACTOR
    assert result.max_displacement < 1.0


def test_side_walls_hold_twice_their_in_plane_load() -> None:
    for chassis in (chassis_19_inch(1), chassis_10_inch(1), chassis_19_inch(4)):
        assert wall_bending(chassis.name, chassis).factor >= SAFETY_FACTOR
