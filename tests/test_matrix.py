# SPDX-License-Identifier: AGPL-3.0-or-later
"""The configuration matrix: every combination either builds or is refused with a reason, never crashes.

The gate lays out a fixed sample (layout only, no solids); `python -m modularack.matrix` builds and checks
the whole matrix on a runner, with renders and strength runs. MODULARACK_FULL_MATRIX=1 lays out all of it here.
"""

import os
import random

import pytest

from modularack.chassis import EarStyle
from modularack.matrix import RACKS, Config, Power, Support, Toolless, configurations

ALL = list(configurations())
SAMPLE = ALL if os.environ.get("MODULARACK_FULL_MATRIX") else random.Random(7).sample(ALL, 400)


def test_the_matrix_covers_every_axis() -> None:
    assert {c.rack for c in ALL} == set(RACKS)
    assert {c.power for c in ALL} == set(Power)
    assert {c.toolless for c in ALL} == set(Toolless)
    assert {c.support for c in ALL} == set(Support)
    assert len({c.name for c in ALL}) == len(ALL)


@pytest.mark.parametrize("config", SAMPLE, ids=lambda c: c.name)
def test_a_configuration_builds_or_is_refused(config: Config) -> None:
    try:
        chassis = config.chassis()
    except ValueError:
        return
    assert chassis.built
    assert all(chassis.occupied[r][c] for r in range(chassis.units) for c in range(len(chassis.occupied[r])))


@pytest.mark.parametrize(
    "config",
    [
        Config("15in", 4, "atx", EarStyle.SCREW, False, Support.NONE, Toolless.FULL, Power.FRONT),
        Config("14.5in", 4, "atx", EarStyle.SCREW, False, Support.NONE, Toolless.NONE, Power.FRONT),
        Config("19in", 4, "e-atx", EarStyle.HOOK, True, Support.KNEE_2, Toolless.FULL, Power.REAR),
        Config("10in", 2, "mini-itx", EarStyle.SNAP, True, Support.KNEE_2, Toolless.FULL, Power.NONE),
        Config("19in", 3, "mini-itx", EarStyle.SCREW, False, Support.REAR, Toolless.NONE, Power.REAR),
    ],
    ids=lambda c: c.name,
)
def test_the_layouts_people_build_are_not_refused(config: Config) -> None:
    assert config.chassis().built
