# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test coupons: small prints of each critical fit, cut from the real parts, to calibrate clearances.

Every coupon is a box cut from a plate of a reference chassis, in that plate's own print frame, so it has
exactly the geometry the full part has; placed at the plate's position, each pair assembles mated. Print
a pair, try the fit, and adjust the clearance named on its sheet entry (`COUPON_NOTES`).

The tool-less coupons come from a 19 in 2U tool-less box (flat-printed walls), the drawer rail from a
19 in 1U with drawers, the sled pin from a pinned 3.5 in sled, the screwed edge joint from the screwed
19 in 2U, and the SATA collar from a bay with the placeholder adapter.
"""

from __future__ import annotations

from build123d import Box, Part, Pos, Vector

from . import lid, toolless
from .cassette import Cassette, DriveBay
from .chassis import FLOOR_THICKNESS, WALL_THICKNESS, RackChassis
from .component import Component
from .fasteners import EDGE_INSERT, EDGE_INSERT_RELIEF_DEPTH, screw_length
from .layout import Panel
from .passthrough import PLACEHOLDER_ADAPTER
from .plate import Edge, EdgeInsert, Plate, RectCut, Rib
from .print_settings import PrintSettings
from .reference import COLUMNS_3_5_19_INCH, DEPTH_19_INCH, chassis_19_inch
from .sled import DRIVE_SIDE_CLEARANCE, PIN_ENGAGE, Sled
from .standards import ATX, DRIVE_3_5, RACK_19_INCH

MARGIN = 10.0

COUPON_NOTES = {
    "floor_dovetail": "Drop the wall's tab into the floor's window and slide it back into the groove; it should "
    "slide by hand and not lift. Tune lid.CLEARANCE.",
    "cover_dovetail": "Drop the cover's tab into the wall's window from above and slide it forward into the "
    "groove. Tune lid.CLEARANCE.",
    "cover_latch": "Drop the cover strip in at the rear of the wall strip and slide it forward: the arm should "
    "bend and the tooth snap into the pocket; press the arm in to release. Tune lid.TOOTH and "
    "lid.LATCH_RELIEF.",
    "rear_latch": "Lower the rear-wall end into place against the side-wall strip: the tooth should click "
    "into its pocket and hold; press the arm's top inward to release. Tune toolless.REAR_TOOTH.",
    "rear_tenon": "The tenon should drop into the floor pocket without play. Tune lid.CLEARANCE.",
    "drawer_rail": "Slide the side-plate strip into the floor strip's rail from its front edge: the tabs should "
    "run freely, the detent click into its notch, and lifting the arm's front end release it. Tune "
    "lid.CLEARANCE and toolless.DETENT_DROP.",
    "sled_pin": "Press a 3.5 in drive's side hole onto the pin from below: the skin should spring aside and "
    "the pin snap into the hole and carry the drive; pushing the drive up should free it. Tune "
    "sled.PIN_CLEARANCE and sled.PIN_ENGAGE.",
    "edge_insert": "Press two M3x5.7 inserts into the wall's bottom edge and screw the floor strip on with "
    "M3 countersunk screws. Tune fasteners.EDGE_INSERT.",
    "sata_collar": "Press the adapter into the collar with its male side through the window; it should sit "
    "square and hold. Measure the adapter first (passthrough.SataAdapter).",
}


class Coupon(Component):
    """A box cut from one plate, in that plate's print frame, placed where the plate is."""

    def __init__(self, name: str, plate: Plate, box: tuple[float, float, float, float]) -> None:
        super().__init__(name)
        u0, v0, u1, v1 = box
        t = plate.thickness
        cut = Pos((u0 + u1) / 2, (v0 + v1) / 2, t / 2) * Box(u1 - u0, v1 - v0, t + 10)
        part = plate.body() & cut
        solids = part.solids()
        if len(solids) != 1:
            raise ValueError(f"{name}: the cut from {plate.name} falls into {len(solids)} pieces")
        self.part = Part(solids[0].wrapped)
        self.placement = plate.placement
        self.print_settings: PrintSettings = plate.print_settings
        if plate.print_up is not None:
            raise ValueError(f"{name}: {plate.name} prints upright; cut coupons from a flat-printed plate")

    def solids(self) -> dict[str, Part]:
        return {"part": self.part}


class SledCoupon(Component):
    """A box cut from a sled (one solid, printed in its own frame), placed where the sled is."""

    def __init__(self, name: str, sled: Sled, box: tuple[float, float, float, float, float, float]) -> None:
        super().__init__(name)
        x0, y0, z0, x1, y1, z1 = box
        cut = Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)
        solids = (sled.solids()["part"] & cut).solids()
        if len(solids) != 1:
            raise ValueError(f"{name}: the cut from {sled.name} falls into {len(solids)} pieces")
        self.part = Part(solids[0].wrapped)
        self.placement = sled.placement
        self.print_location = sled.print_location

    def solids(self) -> dict[str, Part]:
        return {"part": self.part}


def _first(panel: Panel, kind: type, where: object = None) -> tuple[Plate, object]:
    for plate in panel.segments.values():
        for feature in plate.features:
            if isinstance(feature, kind) and (where is None or where(feature)):  # type: ignore[operator]
                return plate, feature
    raise ValueError(f"No {kind.__name__} in {panel.name}")


class CouponSet(Component):
    def __init__(self) -> None:
        super().__init__("coupons")
        box = chassis_19_inch(2, toolless_box=True)
        self._floor_dovetail(box)
        self._cover_dovetail(box)
        self._cover_latch(box)
        self._rear(box)
        self._drawer(chassis_19_inch(1, toolless_box=True, toolless_modules=True))
        self._sled_pin()
        self._edge_insert(chassis_19_inch(2))
        self._sata_collar()
        screw = screw_length(FLOOR_THICKNESS, EDGE_INSERT.length, EDGE_INSERT_RELIEF_DEPTH)
        # The edge-insert coupon's two joints.
        self.hardware = [EDGE_INSERT.name, f"M3x{screw} countersunk (ISO 10642)"] * 2

    def solids(self) -> dict[str, Part]:
        return {}

    def _pair(
        self,
        name: str,
        a: tuple[Plate, tuple[float, float, float, float]],
        b: tuple[Plate, tuple[float, float, float, float]],
    ) -> None:
        self.add_child(Coupon(f"{name}_a", *a))
        self.add_child(Coupon(f"{name}_b", *b))

    def _floor_dovetail(self, box: RackChassis) -> None:
        wall, tab = _first(box.left_wall, lid.CoverTab, lambda f: f.edge_v == 0.0)
        assert isinstance(tab, lid.CoverTab)
        floor, socket = _first(box.floor, toolless.FloorSocket, lambda f: f.sign < 0)
        assert isinstance(socket, toolless.FloorSocket)
        lo, hi = min(*socket.lock, *socket.window), max(*socket.lock, *socket.window)
        edge = socket.edge_v + box.wall_inset
        self._pair(
            "floor_dovetail",
            (wall, (tab.u0 - MARGIN, -lid.TAB_REACH - 1, tab.u1 + MARGIN, 20.0)),
            (floor, (lo - MARGIN, edge - 25.0, hi + MARGIN, min(edge, floor.width))),
        )

    def _cover_dovetail(self, box: RackChassis) -> None:
        cover, tab = _first(box.cover, lid.CoverTab, lambda f: f.outward > 0)
        assert isinstance(tab, lid.CoverTab)
        wall, socket = _first(box.left_wall, lid.TabSocket)
        assert isinstance(socket, lid.TabSocket)
        lo, hi = min(*socket.lock, *socket.window), max(*socket.lock, *socket.window)
        self._pair(
            "cover_dovetail",
            (cover, (tab.u0 - MARGIN, tab.edge_v - 25.0, tab.u1 + MARGIN, tab.edge_v + lid.TAB_REACH + 1)),
            (wall, (lo - MARGIN, socket.floor_v - 15.0, hi + MARGIN, wall.width + 1)),
        )

    def _cover_latch(self, box: RackChassis) -> None:
        cover, tooth = _first(box.cover, lid.LatchTooth)
        assert isinstance(tooth, lid.LatchTooth)
        wall, pocket = _first(box.left_wall, lid.LatchPocket)
        assert isinstance(pocket, lid.LatchPocket)
        root = cover.length - lid.LATCH_ARM
        self._pair(
            "cover_latch",
            (cover, (root - MARGIN, tooth.edge_v - 25.0, cover.length + 1, tooth.edge_v + lid.TOOTH + 1)),
            # The wall strip runs from ahead of the pocket to the wall's rear end: the tooth's whole slide.
            (wall, (pocket.u0 - MARGIN, pocket.floor_v - 15.0, wall.length + 1, wall.width + 1)),
        )

    def _rear(self, box: RackChassis) -> None:
        rear, tooth = _first(box.rear_wall, toolless.SideTooth, lambda f: f.outward > 0)
        assert isinstance(tooth, toolless.SideTooth)
        side, pocket = _first(
            box.left_wall,
            RectCut,
            lambda f: f.depth is not None and abs(f.depth - (toolless.REAR_TOOTH + lid.CLEARANCE)) < 1e-6,
        )
        assert isinstance(pocket, RectCut)
        self._pair(
            "rear_latch",
            (rear, (tooth.edge_u - 30.0, -1.0, tooth.edge_u + toolless.REAR_TOOTH + 1, rear.width + 1)),
            (side, (pocket.u0 - MARGIN, pocket.v0 - 15.0, side.length + 1, side.width + 1)),
        )
        rear_t, tenon = _first(box.rear_wall, toolless.Tenon)
        assert isinstance(tenon, toolless.Tenon)
        floor, hole = _first(
            box.floor,
            RectCut,
            lambda f: f.depth is not None and abs(f.depth - (toolless.TENON_REACH + lid.CLEARANCE)) < 1e-6,
        )
        assert isinstance(hole, RectCut)
        self._pair(
            "rear_tenon",
            (rear_t, (tenon.u0 - MARGIN, -toolless.TENON_REACH - 1, tenon.u1 + MARGIN, 15.0)),
            (floor, (hole.u0 - MARGIN, hole.v0 - MARGIN, floor.length + 1, hole.v1 + MARGIN)),
        )

    def _drawer(self, drawers: RackChassis) -> None:
        cassette = next(c for c in drawers.children.values() if isinstance(c, Cassette))
        side = cassette.left
        bump = next(f for f in side.features if isinstance(f, toolless.DetentBump))
        tab = next(f for f in side.features if isinstance(f, toolless.RailTab))
        floor, groove = _first(drawers.floor, toolless.RailGroove)
        assert isinstance(groove, toolless.RailGroove)
        _, hi = sorted(groove.lock)
        v0, v1 = sorted((groove.edge_v - groove.sign * MARGIN, groove.edge_v + groove.sign * 20.0))
        # The floor's u behind the side plate's first rail tab.
        tab_back = floor.frame.to_local(side.frame.to_rack(Vector(tab.u1, 0, 0))).X
        self._pair(
            "drawer_rail",
            # The side plate's front, with its detent arm and first rail tab behind it.
            (side, (min(bump.u0, 0.0) - 1, -lid.TAB_REACH - bump.drop - 1, tab.u1 + 2, 20.0)),
            # The rail from the floor's front edge back past that tab, with the detent's notch.
            (floor, (-1.0, max(v0, 0.0), min(hi + 1, tab_back + MARGIN), min(v1, floor.width))),
        )

    def _edge_insert(self, screwed: RackChassis) -> None:
        wall = next(iter(screwed.left_wall.segments.values()))
        inserts = sorted(
            (f for f in wall.features if isinstance(f, EdgeInsert) and f.edge is Edge.V0), key=lambda f: f.position
        )[:2]
        if len(inserts) < 2:
            raise ValueError("The screwed wall's first segment has fewer than two bottom-edge inserts")
        u0, u1 = inserts[0].position - MARGIN, inserts[1].position + MARGIN
        # The floor strip under the same stretch of wall, out to the floor's edge.
        corners = [wall.frame.to_rack(Vector(u, 0, 0)) for u in (u0, u1)]
        floor = screwed.floor
        local = [floor.frame.to_local(c) for c in corners]
        mid_u = (local[0].X + local[1].X) / 2
        found = floor.segment_at(mid_u, local[0].Y - 5.0)
        assert found is not None
        fplate, fu, fv = found
        du, dv = fu - mid_u, fv - (local[0].Y - 5.0)
        lo, hi = sorted(c.X + du for c in local)
        edge = local[0].Y + dv
        self._pair(
            "edge_insert",
            (wall, (u0, 0.0, u1, 20.0)),
            (fplate, (lo, edge - 2 * MARGIN - WALL_THICKNESS, hi, min(edge, fplate.width))),
        )

    def _sled_pin(self) -> None:
        chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX, toolless_sleds=True)
        chassis.add_module(DriveBay(DRIVE_3_5, levels=1), COLUMNS_3_5_19_INCH[0], 0)
        chassis.build()
        sled = next(d for d in chassis.descendants() if isinstance(d, Sled))
        g = sled.geometry
        # The y = 0 rail around its front pin arm, with the pin standing out of its inner face.
        x, inner_y, inward, _ = min((a for a in g.pin_arms() if a[2] > 0), key=lambda a: a[0])
        lo, hi = next(span for span in g.pin_arm_spans() if span[0] <= x <= span[1])
        reach = DRIVE_SIDE_CLEARANCE + PIN_ENGAGE + 1
        # Stop short of the detent arm's slot behind the pin arm, or its stub would print as a loose piece.
        box = (lo - 4, -1.0, -1.0, hi + 1, inner_y + inward * reach, g.rail_height + 1)
        self.add_child(SledCoupon("sled_pin", sled, box))

    def _sata_collar(self) -> None:
        chassis = RackChassis(RACK_19_INCH, 1, DEPTH_19_INCH, ATX)
        chassis.add_module(DriveBay(DRIVE_3_5, levels=1, pass_through=PLACEHOLDER_ADAPTER), COLUMNS_3_5_19_INCH[0], 0)
        chassis.build()
        cassette = next(c for c in chassis.children.values() if isinstance(c, Cassette))
        stop = cassette.children[f"{cassette.name}_rear_stop"]
        assert isinstance(stop, Plate)
        ribs = [f for f in stop.features if isinstance(f, Rib)]
        u0, u1 = min(r.u0 for r in ribs) - 2, max(r.u1 for r in ribs) + 2
        v1 = max(r.v1 for r in ribs) + 2
        self.add_child(Coupon("sata_collar", stop, (u0, -1.0, u1, min(v1, stop.width))))
