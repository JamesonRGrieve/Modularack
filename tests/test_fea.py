# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strength checks on the worst real mounting: a loaded chassis hung from its front ears (two-post).

Needs gmsh and CalculiX (MODULARACK_GMSH / MODULARACK_CCX); the CAD SOP records the desktop installs.
"""

from pathlib import Path

import pytest

from modularack.crosscheck import LinearProblem, run_code_aster, run_elmer, run_fenicsx
from modularack.fea import (
    PETG,
    SAFETY_FACTOR,
    _summarise,
    analyse_ear,
    cross_check_ear,
    ear_problem,
    solve_calculix,
    wall_bending,
)
from modularack.reference import chassis_10_inch, chassis_19_inch


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


def test_five_independent_codes_agree_on_the_ear(tmp_path: Path) -> None:
    # CalculiX, scikit-fem, FEniCSx, Code_Aster and Elmer solve the identical linear mesh and loads.
    # Element-stress codes must match to four figures; Elmer reports nodal (averaged) stress, so only
    # its displacement is held to that, and its stresses to the same order.
    problem = ear_problem(chassis_19_inch(1), tmp_path)
    reference = _summarise("calculix", problem, *solve_calculix(problem, tmp_path, second_order=False))
    linear = LinearProblem.of(problem)
    for name, runner in (("fenicsx", run_fenicsx), ("code_aster", run_code_aster)):
        work = tmp_path / name
        work.mkdir()
        result = _summarise(name, problem, *runner(linear, work))
        assert result.max_displacement == pytest.approx(reference.max_displacement, rel=1e-3), name
        assert result.in_layer == pytest.approx(reference.in_layer, rel=1e-3), name
        assert result.interlayer_shear == pytest.approx(reference.interlayer_shear, rel=1e-3), name
    work = tmp_path / "elmer"
    work.mkdir()
    elmer = _summarise("elmer", problem, *run_elmer(linear, work))
    assert elmer.max_displacement == pytest.approx(reference.max_displacement, rel=1e-3)
    assert elmer.interlayer_shear == pytest.approx(reference.interlayer_shear, rel=0.25)


def test_a_petg_ear_holds_twice_its_two_post_load() -> None:
    result = analyse_ear("chassis_19in_1U", chassis_19_inch(1), PETG)
    assert result.material is PETG
    assert result.in_layer_factor >= SAFETY_FACTOR
    assert result.interlayer_factor >= SAFETY_FACTOR


def test_softer_layers_do_not_raise_the_stress_between_them() -> None:
    # Printed parts are softer across their layers by an amount no data sheet gives. Taking that
    # modulus at 0.6 of in-plane moves load away from the bonds, so the isotropic check is the cautious one.
    isotropic = analyse_ear("chassis_19in_1U", chassis_19_inch(1))
    soft = analyse_ear("chassis_19in_1U", chassis_19_inch(1), layer_modulus_ratio=0.6)
    assert soft.interlayer_factor >= isotropic.interlayer_factor * 0.98
    assert soft.interlayer_factor >= SAFETY_FACTOR
