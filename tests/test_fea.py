# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strength checks on the worst real mounting: a loaded chassis hung from its front ears (two-post).

Needs gmsh and CalculiX (ZEPHYRACK_GMSH / ZEPHYRACK_CCX); the CAD SOP records the desktop installs.
"""

import pytest

from zephyrack.fea import SAFETY_FACTOR, analyse_ear, cross_check_ear, wall_bending
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


def test_two_independent_solvers_agree_on_the_same_mesh_and_loads() -> None:
    # CalculiX C3D4 and scikit-fem P1 on identical linear tetrahedra and nodal loads: any difference
    # would be a bug in the mesh import, supports or load set-up, not in either solver.
    calculix, scikit = cross_check_ear("chassis_19in_1U", chassis_19_inch(1))
    assert scikit.max_displacement == pytest.approx(calculix.max_displacement, rel=1e-3)
    assert scikit.in_layer == pytest.approx(calculix.in_layer, rel=1e-3)
    assert scikit.interlayer_shear == pytest.approx(calculix.interlayer_shear, rel=1e-3)
