# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for fasteners, seams, joints, plates and the sled."""

import math

import bd_warehouse.fastener as bdw
import pytest
from build123d import Box, BuildPart, GeomType, Location, Locations, Pos, Vector

from zephyrack.fasteners import INSERT_M3_LONG, INSERT_M3_SHORT, M3_CLEARANCE, screw_length
from zephyrack.joints import LapFastening, edge_joint, lap_joint, nut_lap_fit
from zephyrack.layout import Bed, Panel, plan_seams
from zephyrack.plate import Edge, EdgeInsert, Frame, Plate, ThroughHole, teardrop_prism
from zephyrack.printability import overhangs
from zephyrack.sled import FRONT_BAR_THICKNESS, Sled, SledGeometry
from zephyrack.standards import DRIVE_2_5, DRIVE_3_5


@pytest.mark.parametrize(("spec", "size"), [(INSERT_M3_LONG, "M3-0.5-5.7"), (INSERT_M3_SHORT, "M3-0.5-3")])
def test_insert_bores_match_bd_warehouse(spec, size) -> None:  # type: ignore[no-untyped-def]
    # bd_warehouse accepts CNCKitchen (see HeatSetNut.types()) but its type hint lists two vendors only.
    nut = bdw.HeatSetNut(size, fastener_type="CNCKitchen")  # type: ignore[arg-type]
    with BuildPart() as block:
        Box(20, 20, 20)
        with Locations((0, 0, 10)):
            bdw.InsertHole(nut, depth=12)
    assert block.part is not None
    radii = {round((f.radius or 0.0) * 2, 3) for f in block.part.faces().filter_by(GeomType.CYLINDER)}
    assert radii == {round(spec.bore_diameter, 3), spec.relief_diameter}
    assert nut.nut_thickness == pytest.approx(spec.length)
    assert bdw.CounterSunkScrew("M3-0.5", 10, "iso10642").clearance_hole_diameters["Normal"] == M3_CLEARANCE


def test_screw_length_picks_the_shortest_that_engages() -> None:
    assert screw_length(6, 5.7, 4) == 12
    assert screw_length(9, 5.7, 4) == 16
    with pytest.raises(ValueError):
        screw_length(9, 5.7, 0.1)


def test_nut_lap_sinks_the_nut_to_suit_a_standard_screw() -> None:
    length, pocket = nut_lap_fit(9, 9)
    assert length == 16
    assert pocket == pytest.approx(4.4)


def test_seams_split_evenly_and_respect_keepouts() -> None:
    assert plan_seams(200, 240, [], 14) == []
    assert plan_seams(400, 240, [], 14) == [200]
    seams = plan_seams(400, 240, [(190, 210)], 14)
    assert len(seams) == 1 and not 190 - 14 < seams[0] < 210 + 14
    assert all(b - a <= 240 for a, b in zip([0, *seams], [*seams, 400], strict=True))


def test_seam_planner_adds_a_segment_when_keepouts_block_the_even_split() -> None:
    seams = plan_seams(533.4, 200, [(157.8, 197.8), (335.6, 375.6)], 14.2)
    assert len(seams) == 3


def test_panel_splits_to_the_bed_and_splices_every_seam() -> None:
    panel = Panel("p", 450, 448, 7, Frame(Vector(0, 0, 0), Vector(1, 0, 0), Vector(0, 0, 1)), Bed())
    assert len(panel.segments) == 6
    for plate in panel.segments.values():
        assert Bed().fits((plate.length, plate.width, plate.thickness))
    expected = len(panel.seams_u) * (len(panel.v_bounds) - 1) + len(panel.seams_v) * (len(panel.u_bounds) - 1)
    assert len(panel.splice_plates) == expected


def test_edge_joint_holes_and_inserts_share_one_axis() -> None:
    floor = Plate("floor", 200, 100, 7, Frame(Vector(0, 0, 0), Vector(1, 0, 0), Vector(0, 0, 1)))
    wall = Plate("wall", 200, 60, 9, Frame(Vector(0, 9, 7), Vector(1, 0, 0), Vector(0, -1, 0)))
    edge_joint(floor, wall, Edge.V0)
    inserts = [f for f in wall.features if isinstance(f, EdgeInsert)]
    holes = [f for f in floor.features if isinstance(f, ThroughHole)]
    assert len(inserts) == len(holes) >= 2
    for insert, hole in zip(inserts, holes, strict=True):
        start, direction = insert.start_and_direction(wall)
        rack_start = wall.frame.to_rack(start)
        hole_axis_point = floor.frame.to_rack(Vector(hole.u, hole.v, floor.thickness))
        assert (rack_start - hole_axis_point).length == pytest.approx(0, abs=1e-6)
        assert abs(wall.frame.direction_to_rack(direction).dot(floor.frame.w)) == pytest.approx(1)


def test_edge_joint_refuses_plates_that_do_not_meet() -> None:
    floor = Plate("floor", 200, 100, 7, Frame(Vector(0, 0, 0), Vector(1, 0, 0), Vector(0, 0, 1)))
    wall = Plate("wall", 200, 60, 9, Frame(Vector(0, 9, 20), Vector(1, 0, 0), Vector(0, -1, 0)))
    with pytest.raises(ValueError):
        edge_joint(floor, wall, Edge.V0)


def test_lap_joint_puts_the_nut_on_the_far_face() -> None:
    a = Plate("a", 100, 40, 9, Frame(Vector(0, 0, 9), Vector(1, 0, 0), Vector(0, 0, 1)))
    b = Plate("b", 100, 40, 9, Frame(Vector(0, 40, 9), Vector(1, 0, 0), Vector(0, 0, -1)))
    hardware = lap_joint(a, b, [Vector(30, 20, 9), Vector(70, 20, 9)], LapFastening.NUT)
    assert hardware.items.count("M3 hex nut (ISO 4032)") == 2


def test_teardrop_is_one_solid_with_a_45_degree_roof() -> None:
    drop = teardrop_prism(Vector(0, 0, 10), Vector(0, 1, 0), 2.0, 5.0)
    assert len(drop.solids()) == 1
    block = Pos(0, 0, 10) * Box(30, 30, 20) - drop
    assert overhangs(block) == []
    top = drop.bounding_box().max.Z
    assert top == pytest.approx(10 + 2.0 * math.sqrt(2))


def test_a_flat_ceiling_is_caught() -> None:
    bridge = Box(20, 20, 10) - Pos(0, 0, -1) * Box(10, 30, 4)
    assert overhangs(bridge)


@pytest.mark.parametrize("drive", [DRIVE_3_5, DRIVE_2_5])
def test_sled_screw_holes_sit_on_the_sff_side_holes(drive) -> None:  # type: ignore[no-untyped-def]
    geometry = SledGeometry(drive, drive.width + 16)
    sled = Sled("s", geometry, Location()).solids()["part"]
    connector_end = FRONT_BAR_THICKNESS + drive.length
    hole_z = geometry.drive_base + drive.side_hole_height
    for offset in drive.side_hole_offsets:
        probe = Pos(connector_end - offset, geometry.rail_width / 2, hole_z) * Box(0.5, 0.5, 0.5)
        common = sled.intersect(probe)
        assert common is None or not common.solids()
    assert overhangs(sled) == []


def test_sled_rejects_rails_too_thin_for_the_screw_heads() -> None:
    with pytest.raises(ValueError):
        Sled("s", SledGeometry(DRIVE_3_5, DRIVE_3_5.width + 4), Location())
