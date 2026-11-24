# SPDX-License-Identifier: AGPL-3.0-or-later
"""Printed rails and shelves for commercial servers in four-post square-hole racks."""

import pytest

from modularack.checks import check
from modularack.printability import overhangs
from modularack.servers import (
    DELL_R720,
    PITCH_A,
    PITCH_B,
    Sacrifice,
    ServerRails,
    ServerSpec,
    rail_capacity,
    rail_strength,
    shelf_capacity,
)


@pytest.mark.parametrize("sacrifice", list(Sacrifice))
def test_r720_rails_print_and_assemble(sacrifice: Sacrifice) -> None:
    rails = ServerRails(sacrifice=sacrifice)
    report = check(rails)
    assert report.clean, report
    for name, part in rails.printable_parts().items():
        assert part.is_valid and len(part.solids()) == 1, name
        assert not overhangs(part), name


@pytest.mark.parametrize("sacrifice", list(Sacrifice))
def test_the_rails_carry_an_r720_with_margin(sacrifice: Sacrifice) -> None:
    margins = rail_strength(ServerRails(sacrifice=sacrifice).layout)
    assert min(margins.bending, margins.lap_pins) >= 2.0
    assert margins.deflection < 1.0
    assert rail_capacity(ServerRails(sacrifice=sacrifice).layout) >= DELL_R720.mass


def test_the_vernier_sets_every_millimetre_of_the_span() -> None:
    layout = ServerRails().layout
    joint = len(layout.butts()) - 1
    plate = layout.holes(joint, "plate")[1:]
    rear = layout.holes(joint, "rear")
    for travel in range(int(layout.travel) + 1):
        assert min(abs(p - (r + travel)) for p in plate for r in rear) <= 0.5, travel
    assert pytest.approx(1.0) == PITCH_A - PITCH_B


def test_a_span_range_too_wide_for_one_vernier_is_refused() -> None:
    with pytest.raises(ValueError, match="adjusts over"):
        ServerRails(span=(600.0, 760.0))


def test_a_server_too_narrow_for_the_ledges_is_refused() -> None:
    with pytest.raises(ValueError, match="too narrow"):
        ServerRails(server=ServerSpec("narrow", 1, 400.0, 43.0, 500.0, 10.0))


def test_a_shelf_prints_assembles_and_is_rated() -> None:
    rails = ServerRails(shelf=True)
    report = check(rails)
    assert report.clean, report
    # Limited by the rails' lap pins, well above a heavy server.
    assert DELL_R720.mass < shelf_capacity(rails) <= rails.shelf.capacity()


def test_a_shelf_needs_the_sacrificed_unit() -> None:
    with pytest.raises(ValueError, match=r"Sacrifice\.UNIT"):
        ServerRails(sacrifice=Sacrifice.HOLE, shelf=True)
