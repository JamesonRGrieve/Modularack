# SPDX-License-Identifier: AGPL-3.0-or-later
"""FEA of the tool-less box's dovetails (needs gmsh and CalculiX, like test_fea)."""

import tempfile
from pathlib import Path

import pytest

from modularack.fea import SAFETY_FACTOR
from modularack.joint_fea import (
    analyse_dovetails,
    analyse_latches,
    analyse_pin_arm,
    analyse_rails,
    cover_lip_problem,
    lip_problem,
    tab_problem,
)
from modularack.reference import chassis_19_inch


@pytest.fixture(scope="module")
def chassis():  # type: ignore[no-untyped-def]
    return chassis_19_inch(1, toolless_box=True)


@pytest.mark.parametrize("build", [tab_problem, lip_problem, cover_lip_problem])
def test_every_load_and_support_lands_on_the_mesh(chassis, build) -> None:  # type: ignore[no-untyped-def]
    with tempfile.TemporaryDirectory() as tmp:
        problem = build(chassis, Path(tmp))
    assert problem.fixed
    assert all(nodes for nodes, _ in problem.loads)


def test_the_floor_dovetails_hold_the_chassis_at_twice_its_weight(chassis) -> None:  # type: ignore[no-untyped-def]
    results = {r.joint: r for r in analyse_dovetails("19in 1U", chassis)}
    for result in results.values():
        assert result.factor >= SAFETY_FACTOR, result
        # A solid, sensible deflection: the supports leave no mechanism.
        assert result.result.max_displacement < 0.5
    # The floor's lip, bent up across its layers, is the weaker side of the joint.
    assert results["lip"].factor < results["tab"].factor


def test_the_latch_arms_strain_as_the_closed_form_says(chassis) -> None:  # type: ignore[no-untyped-def]
    for latch in analyse_latches("19in 1U", chassis):
        assert latch.fea_strain < 0.02
        assert latch.fea_strain == pytest.approx(latch.closed_form_strain, rel=0.15)
        assert latch.free_end_deflection > latch.travel


def test_drawer_rails_and_detent_hold_a_module_lifted_at_1g() -> None:
    drawers = chassis_19_inch(2, toolless_box=True, toolless_modules=True)
    joints, detent = analyse_rails("19in 2U", drawers)
    for joint in joints:
        assert joint.factor >= SAFETY_FACTOR, joint
        assert joint.result.max_displacement < 0.5
    assert detent.fea_strain < 0.02
    # The closed form misses the slot root's concentration, but stays within 40 %.
    assert detent.fea_strain == pytest.approx(detent.closed_form_strain, rel=0.4)


def test_a_sled_pin_arm_strains_no_more_than_the_closed_form_says() -> None:
    sleds = chassis_19_inch(1, toolless_sleds=True)
    pin = analyse_pin_arm("19in 1U", sleds)
    assert pin.fea_strain < pin.closed_form_strain < 0.02
