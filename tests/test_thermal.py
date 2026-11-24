# SPDX-License-Identifier: AGPL-3.0-or-later
"""Material and temperature scaling of the strength checks (no FEA: a made-up basis)."""

import itertools

import pytest

from modularack.fea import PLA, chassis_mass
from modularack.reference import chassis_10_inch
from modularack.thermal import SOFTENING, TEMPERATURES, Basis, alarm_temperature, retention, rows


@pytest.mark.parametrize("key", list(SOFTENING))
def test_retention_falls_from_one_to_nothing(key: str) -> None:
    softening = SOFTENING[key]
    values = [retention(softening, t) for t in TEMPERATURES]
    assert values[0] == 1.0
    assert all(a >= b for a, b in itertools.pairwise(values))
    assert retention(softening, softening.end) == 0.0
    if softening.retention_40 is not None and softening.end > 40:
        assert retention(softening, 40) == pytest.approx(softening.retention_40)


def test_pla_keeps_92_percent_at_40_and_nothing_at_its_glass_transition() -> None:
    pla = SOFTENING["pla"]
    assert retention(pla, 40) == pytest.approx(1820 / 1980)
    assert retention(pla, 55) == pytest.approx(1820 / 1980 * (59.1 - 55) / (59.1 - 40))
    assert retention(pla, 60) == 0.0


def test_rows_scale_by_strength_retention_and_weight() -> None:
    chassis = chassis_10_inch(1)
    base = Basis(
        ear_in_layer=10.0, ear_across_layers=4.0, wall=5.0, strut_stress=None, strut_buckling_margin=None, joints=[]
    )
    table = rows("x", chassis, base)
    at = {(r.material, r.temperature): r for r in table}
    pla20 = at[("pla", 20)]
    assert pla20.ear_in_layer == pytest.approx(PLA.in_layer_strength / 10.0)
    assert pla20.ear_across_layers == pytest.approx(PLA.interlayer_strength / 4.0)
    abs20 = at[("abs", 20)]
    weight = chassis_mass(chassis, SOFTENING["abs"].material) / chassis_mass(chassis)
    assert abs20.wall == pytest.approx(SOFTENING["abs"].material.in_layer_strength / (5.0 * weight))
    assert at[("pla", 60)].worst == 0.0
    assert alarm_temperature(table, "pla") is not None
