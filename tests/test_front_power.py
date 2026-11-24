# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 14.5 and 15 in widths and the front power supply: which box takes an ATX board, the I/O aperture clear
of the rear wall's end, and the supply's screws on its face turned (not mirrored)."""

import pytest
from build123d import Vector

from modularack.cassette import Cassette
from modularack.chassis import RackChassis, board_floor_width, io_reach, rear_end_margin
from modularack.plate import Frame, Plate, RectCut, ThroughHole
from modularack.power import PowerButton, PowerSupplyBay
from modularack.reference import chassis_compact_atx, reference_builders
from modularack.standards import (
    ATX,
    ATX_PSU,
    E_ATX,
    RACK_14_5_INCH,
    RACK_15_INCH,
    RACK_19_INCH,
    MotherboardFormFactor,
    RackStandard,
)


def _fits(rack: RackStandard, width: float) -> bool:
    return width <= rack.opening - 2 * 1.0 + 1e-6


@pytest.mark.parametrize(
    ("rack", "toolless", "fits"),
    [
        (RACK_14_5_INCH, False, True),
        (RACK_14_5_INCH, True, False),
        (RACK_15_INCH, True, True),
        (RACK_15_INCH, False, True),
    ],
)
def test_the_new_widths_take_an_atx_box(rack: RackStandard, toolless: bool, fits: bool) -> None:
    assert _fits(rack, board_floor_width(ATX, toolless)) is fits
    if not fits:
        with pytest.raises(ValueError, match="I/O aperture"):
            RackChassis(rack, 4, 470, ATX, toolless_box=toolless).build()


@pytest.mark.parametrize(
    ("rack", "board", "toolless"),
    [(RACK_14_5_INCH, ATX, False), (RACK_15_INCH, ATX, True), (RACK_19_INCH, E_ATX, True)],
)
def test_the_aperture_stays_clear_of_the_rear_wall_end(
    rack: RackStandard, board: MotherboardFormFactor, toolless: bool
) -> None:
    chassis = RackChassis(rack, 3, 470, board, toolless_box=toolless)
    chassis.build()
    left_edge = chassis.inner_width / 2 - board.width / 2 - chassis._board_shift()
    right_room = chassis.inner_width - left_edge - io_reach(board)
    assert left_edge >= 1.0 - 1e-6
    assert right_room >= rear_end_margin(toolless) - 1e-6
    for plate in chassis.rear_wall.segments.values():
        assert len(plate.solids()["plate"].solids()) == 1


@pytest.mark.parametrize("on_edge", [True, False])
def test_the_supply_face_is_turned_not_mirrored(on_edge: bool) -> None:
    bay = PowerSupplyBay(on_edge=on_edge)
    face = Plate("face", 120.0, 170.0, 6.0, Frame(Vector(0, 0, 0), Vector(0, 1, 0), Vector(1, 0, 0)))
    a, b, c = (bay.to_face(face, 0.0, *p) for p in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)))
    # Seen from the front the face's u runs right to left, so a turn shows as a negative determinant in (u, v).
    det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    assert det == pytest.approx(-1.0)


def test_the_compact_atx_layout() -> None:
    chassis = chassis_compact_atx(RACK_15_INCH, toolless_box=True)
    kinds = {type(c.kind).__name__: c for c in chassis.children.values() if isinstance(c, Cassette)}
    psu = kinds["PowerSupplyBay"]
    assert isinstance(psu.kind, PowerSupplyBay) and psu.kind.on_edge
    # The supply runs the box's full height, against the floor, and the board starts behind it.
    assert psu.slot.z_bottom == pytest.approx(7.0)
    assert psu.x_back < chassis._board_rear_x() - ATX.depth
    face = next(p for p in psu.children.values() if isinstance(p, Plate) and p.name.endswith("_face"))
    psu_holes = [f for f in face.features if isinstance(f, ThroughHole) and f.diameter == ATX_PSU.screw_clearance]
    assert len(psu_holes) == len(ATX_PSU.holes)
    assert any(isinstance(f, RectCut) for f in face.features)
    assert isinstance(kinds["PowerButton"].kind, PowerButton)


@pytest.mark.parametrize(
    ("name", "rack"),
    [("chassis_14.5in_4U_atx", RACK_14_5_INCH), ("chassis_15in_4U_atx_toolless", RACK_15_INCH)],
)
def test_the_new_widths_fill_their_rack(name: str, rack: RackStandard) -> None:
    chassis = reference_builders()[name]()
    assert isinstance(chassis, RackChassis)
    assert pytest.approx(rack.panel_width) == chassis.assemble().bounding_box().size.Y
