# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rear supports (four-post racks) and side-web clamps (two-post channel racks)."""

import pytest

from zephyrack.chassis import EarStyle, RackChassis
from zephyrack.checks import check
from zephyrack.fea import GRAVITY, SAFETY_FACTOR, chassis_mass
from zephyrack.printability import overhangs
from zephyrack.rear import OVERLAP, PIN_PITCH_FRONT, PIN_PITCH_REAR, RearLayout
from zephyrack.standards import RACK_19_INCH
from zephyrack.web import PostChannel, WebClamp, clamp_reaction


def _rear_chassis(span: tuple[float, float]) -> RackChassis:
    chassis = RackChassis(RACK_19_INCH, 1, 470, ear_style=EarStyle.SNAP, rear_support=span)
    chassis.build()
    return chassis


def test_a_rear_supported_chassis_prints_and_assembles() -> None:
    chassis = _rear_chassis((520, 640))
    report = check(chassis)
    assert report.clean, report
    for name in ("rear_arm_front", "rear_arm_rear", "rear_pin"):
        for side in ("left", "right"):
            part = chassis.printable_parts()[f"{chassis.name}_{side}_{name}"]
            assert part.is_valid and len(part.solids()) == 1
            assert not overhangs(part)


def test_the_vernier_locks_the_arms_at_every_millimetre_of_the_range() -> None:
    chassis = _rear_chassis((520, 640))
    arm = chassis.children[f"{chassis.name}_left_rear_arm_front"]
    layout = arm.layout  # type: ignore[attr-defined]
    assert isinstance(layout, RearLayout)
    front = layout.front_holes()
    for extra in range(0, int(layout.span) + 1):
        # Moving the rear arm back by `extra` moves its holes with it; some pair must line up within 0.5 mm.
        rear = [x + extra for x in layout.rear_holes()]
        assert min(abs(f - r) for f in front for r in rear) <= 0.5, extra
    assert pytest.approx(1.0) == PIN_PITCH_FRONT - PIN_PITCH_REAR
    assert OVERLAP >= PIN_PITCH_FRONT * PIN_PITCH_REAR


def test_a_rack_depth_range_too_long_for_the_bed_is_refused() -> None:
    with pytest.raises(ValueError, match="don't fit the bed"):
        _rear_chassis((520, 800))


def test_a_web_clamped_chassis_prints_and_assembles() -> None:
    chassis = RackChassis(RACK_19_INCH, 1, 470, ear_style=EarStyle.SNAP, one_piece=True, web_clamp=PostChannel())
    chassis.build()
    report = check(chassis)
    assert report.clean, report
    clamp = chassis.printable_parts()[f"{chassis.name}_left_web_clamp"]
    assert clamp.is_valid and len(clamp.solids()) == 1
    assert not overhangs(clamp)


@pytest.mark.parametrize("units", [1, 4])
def test_the_web_clamps_grip_holds_twice_what_it_carries(units: int) -> None:
    chassis = RackChassis(RACK_19_INCH, units, 470, web_clamp=PostChannel())
    chassis.build()
    clamp = chassis.children[f"{chassis.name}_left_web_clamp"]
    assert isinstance(clamp, WebClamp)
    load = chassis_mass(chassis) * GRAVITY / 2
    assert clamp.capacity() >= SAFETY_FACTOR * clamp_reaction(load, chassis.depth, clamp)
