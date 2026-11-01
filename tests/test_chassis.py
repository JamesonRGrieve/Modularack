# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from build123d import Vector

from zephyrack.chassis import GRID_COLUMNS, GridOccupiedError, RackChassis
from zephyrack.floor import Floor, standoff_positions, supported_holes
from zephyrack.front_panel import Bay35, FrontPanelModule
from zephyrack.standards import ATX, MICRO_ATX, MINI_ITX, RACK_UNIT, MountingHole
from zephyrack.wall import WallSegment, WallSide, stack_units

WIDTH = 450.85
DEPTH = 914.4


def test_wall_stacks_use_2u_segments_then_a_1u() -> None:
    assert stack_units(1) == [1]
    assert stack_units(2) == [2]
    assert stack_units(3) == [2, 1]
    assert stack_units(5) == [2, 2, 1]
    with pytest.raises(ValueError):
        stack_units(0)


def test_wall_segment_rejects_other_heights() -> None:
    with pytest.raises(ValueError):
        WallSegment(WallSide.FRONT, WIDTH, DEPTH, 3, 6.35, 0, "w")


def test_floor_takes_every_smaller_board() -> None:
    assert supported_holes(MINI_ITX) == MINI_ITX.holes
    assert supported_holes(MICRO_ATX) == MINI_ITX.holes | MICRO_ATX.holes
    assert supported_holes(ATX) == MINI_ITX.holes | MICRO_ATX.holes | ATX.holes


def test_standoffs_keep_spec_spacing_in_chassis_frame() -> None:
    positions = standoff_positions(ATX, DEPTH)
    c, f, h = positions[MountingHole.C], positions[MountingHole.F], positions[MountingHole.H]
    # Rear edge toward +X: H is 154.94 toward the front (lower X) of C.
    assert c[0] - h[0] == pytest.approx(154.94)
    assert c[1] == pytest.approx(h[1])
    # F is 157.48 along the I/O edge and 22.86 toward the front of C.
    assert c[0] - f[0] == pytest.approx(22.86)
    assert abs(c[1] - f[1]) == pytest.approx(157.48)


def test_floor_is_one_valid_solid_with_one_hole_per_standoff() -> None:
    floor = Floor(WIDTH, DEPTH, 3.175, ATX).solids()["floor"]
    assert floor.is_valid
    assert len(floor.solids()) == 1
    holes = len(supported_holes(ATX))
    plate = WIDTH * DEPTH * 3.175
    hole = 3.141592653589793 * (6.35 / 2) ** 2 * 3.175
    assert floor.volume == pytest.approx(plate - holes * hole, rel=1e-6)


def test_floor_too_small_for_its_board_fails_loudly() -> None:
    with pytest.raises(ValueError, match="falls outside"):
        Floor(200.0, 200.0, 3.0, ATX).solids()


def test_chassis_builds_four_walls_of_the_right_height() -> None:
    chassis = RackChassis(DEPTH, WIDTH, 3)
    walls = [c for c in chassis.children.values() if isinstance(c, WallSegment)]
    assert len(walls) == 4 * len(stack_units(3))
    box = chassis.assemble().bounding_box()
    assert pytest.approx(3 * RACK_UNIT) == box.size.Z
    assert pytest.approx(DEPTH) == box.size.X
    assert pytest.approx(WIDTH) == box.size.Y


def test_grid_rejects_overlap_and_overflow() -> None:
    chassis = RackChassis(DEPTH, WIDTH, 1)
    chassis.add_front_module(Bay35("a"), 0, 0)
    with pytest.raises(GridOccupiedError):
        chassis.add_front_module(Bay35("b"), 2, 0)
    with pytest.raises(GridOccupiedError):
        chassis.add_front_module(Bay35("c"), GRID_COLUMNS - 2, 0)
    chassis.add_front_module(Bay35("d"), 3, 0)


def test_drive_bays_fill_every_row() -> None:
    chassis = RackChassis(DEPTH, WIDTH, 2)
    chassis.fill_with_drive_bays()
    bays = [c for c in chassis.children.values() if isinstance(c, Bay35)]
    assert len(bays) == (GRID_COLUMNS // 3) * chassis.rows
    assert all(all(row) for row in chassis.occupied)


def test_bay_handle_recess_is_in_the_front_face() -> None:
    bay = Bay35()
    bay.fit(WIDTH / GRID_COLUMNS, RACK_UNIT / 2)
    body = bay.solids()["panel"]
    solid = FrontPanelModule(3, 1, bay.depth, "plain")
    solid.fit(WIDTH / GRID_COLUMNS, RACK_UNIT / 2)
    assert body.volume < solid.solids()["panel"].volume
    # The recess opens at -X (the front); the rear face stays whole.
    rear = max(body.faces(), key=lambda face: face.center().X)
    assert rear.area == pytest.approx(bay.width * bay.height)


def test_explode_moves_parts_apart_without_changing_printable_parts() -> None:
    chassis = RackChassis(DEPTH, WIDTH, 2)
    chassis.fill_with_drive_bays()
    before = {k: v.volume for k, v in chassis.printable_parts().items()}
    closed = chassis.assemble().bounding_box()
    exploded = chassis.assemble(127.0).bounding_box()
    assert exploded.size.X > closed.size.X
    assert exploded.size.Y > closed.size.Y
    assert exploded.size.Z > closed.size.Z
    after = {k: v.volume for k, v in chassis.printable_parts().items()}
    assert before == after


def test_child_names_must_be_unique() -> None:
    chassis = RackChassis(DEPTH, WIDTH, 1)
    with pytest.raises(ValueError):
        chassis.add_child("floor", Floor(WIDTH, DEPTH, 3.0, MINI_ITX), Vector(0, 0, 0))
