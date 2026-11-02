# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool-less front modules: drawers on dovetail rails, held home by a sprung detent."""

import pytest
from build123d import Part, Pos

from zephyrack import lid, toolless
from zephyrack.cassette import Cassette
from zephyrack.chassis import RackChassis
from zephyrack.checks import check
from zephyrack.plate import Feature, Plate
from zephyrack.reference import chassis_10_inch, chassis_19_inch


@pytest.fixture(scope="module")
def chassis() -> RackChassis:
    return chassis_19_inch(2, toolless_box=True, toolless_modules=True)


def _cassettes(chassis: RackChassis) -> list[Cassette]:
    return [c for c in chassis.children.values() if isinstance(c, Cassette)]


def _placed(plate: Plate, kind: type[Feature]) -> list[Part]:
    return [plate.placement * f.shape(plate) for f in plate.features if isinstance(f, kind)]


def _supports(chassis: RackChassis) -> list[Part]:
    plates = [*chassis.floor.segments.values(), *(c.shelf for c in _cassettes(chassis) if c.shelf is not None)]
    return [p.placement * p.body() for p in plates]


def _overlap(moving: list[Part], fixed: list[Part], dx: float = 0.0, dz: float = 0.0) -> float:
    total = 0.0
    for m in moving:
        for f in fixed:
            common = (Pos(dx, 0, dz) * m).intersect(f)
            total += sum(s.volume for s in common.solids()) if common is not None else 0.0
    return total


def test_no_screw_holds_a_module_in(chassis: RackChassis) -> None:
    screwed = chassis_19_inch(2, toolless_box=True)
    count = sum(n for item, n in chassis.bill_of_materials().items() if "countersunk" in item)
    before = sum(n for item, n in screwed.bill_of_materials().items() if "countersunk" in item)
    assert count < before


def test_every_module_rides_rails_and_has_a_detent(chassis: RackChassis) -> None:
    for cassette in _cassettes(chassis):
        tabs = [f for p in (cassette.left, cassette.right) for f in p.features if isinstance(f, toolless.RailTab)]
        detents = [f for f in cassette.left.features if isinstance(f, toolless.DetentBump)]
        assert len(tabs) + len(detents) >= 3, cassette.name
        assert len(detents) == 1, cassette.name
        assert toolless.DETENT_MIN_DROP <= detents[0].drop <= toolless.DETENT_DROP


def test_a_module_is_held_down_but_slides_out_the_front(chassis: RackChassis) -> None:
    supports = _supports(chassis)
    for cassette in _cassettes(chassis)[:2]:
        tabs = [t for p in (cassette.left, cassette.right) for t in _placed(p, toolless.RailTab)]
        assert _overlap(tabs, supports) == pytest.approx(0, abs=1e-6)
        assert _overlap(tabs, supports, dz=1.0) > 0.5
        for dx in (-5.0, -30.0, -cassette.x_back):
            assert _overlap(tabs, supports, dx=dx) == pytest.approx(0, abs=1e-6), (cassette.name, dx)


def test_the_detent_holds_until_lifted(chassis: RackChassis) -> None:
    supports = _supports(chassis)
    cassette = _cassettes(chassis)[0]
    bump = _placed(cassette.left, toolless.DetentBump)
    assert _overlap(bump, supports) == pytest.approx(0, abs=1e-6)
    # Pulled forward, its square face catches the notch's front, and the nose rides the groove floor ahead
    # of it (the arm must bend) all the way out past the floor's front edge.
    assert _overlap(bump, supports, dx=-1.0) > 0.05
    assert _overlap(bump, supports, dx=-3.0) > 0.05


@pytest.mark.parametrize(("build", "units"), [(chassis_10_inch, 2), (chassis_19_inch, 1), (chassis_19_inch, 3)])
def test_reference_chassis_take_drawers(build, units: int) -> None:  # type: ignore[no-untyped-def]
    built = build(units, toolless_box=True, toolless_modules=True)
    report = check(built)
    assert report.clean, report
    assert built.shelf_thickness == pytest.approx(lid.TAB_REACH + 4.0)
