# SPDX-License-Identifier: AGPL-3.0-or-later
"""Printed rails and shelves for commercial servers in four-post square-hole racks (APC-style).

A rack server is about as wide as the rack opening (an R720 is 444 mm in a 450 mm opening), so there is
no room for a printed rail beside it. Each rail is instead an L: an upright web outboard of the opening,
running between the front and rear posts, and a ledge reaching in under the server's side edge. The
server sits on the two ledges, against a lip at their rear; its own ears stop it at the front.

`Sacrifice.UNIT` gives the rail the whole U below the server: the ledge's top is that U's top, the web
is a deep beam, and the server's ears stay on the EIA hole pattern. `Sacrifice.HOLE` keeps the rail
within the server's own units and raises the server `HOLE_LIFT` (about a square hole's worth) onto the
ledge instead; its ears then sit off the hole pattern.

A rail is longer than the bed, so it prints as full-thickness segments butted end to end (each lying on
its outer face, so bending runs along the layers), joined by splice plates on the web's outer face:
printed diamond pins through plate and web at the top and bottom of the web carry the bending couple.
The joint nearest the rear (where bending is smallest) is a vernier, the plate's holes 10 mm apart against
the rear segment's 9 mm, so the rail sets to any post spacing in its range to the millimetre. End plates
bear on the posts' inner faces with a peg through every square hole the rail spans.

`shelf=True` adds cross-beams hung on the ledges and deck plates on them, for gear that isn't rack-mounted
(it needs `Sacrifice.UNIT`: the beams hang in the sacrificed U).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from enum import StrEnum

from build123d import Box, Location, Part, Plane, RegularPolygon, Vector, extrude

from .component import Component
from .hooks import HOOK_VERTICAL_CLEARANCE, SQUARE_HOLE
from .layout import MK3S_BED, Bed
from .standards import RACK_19_INCH, RACK_UNIT, U_HOLE_OFFSETS, RackStandard

GRAVITY = 9.81e-3
"""N per g."""


@dataclass(frozen=True)
class ServerSpec:
    """A rack server's body (not its ears or bezel) and the most it weighs."""

    name: str
    units: int
    width: float
    height: float
    depth: float
    mass: float
    """kg, fully populated."""


DELL_R720 = ServerSpec("Dell PowerEdge R720", 2, 444.0, 87.3, 683.7, 29.5)
"""Dell R720 Getting Started Guide / Technical Guide: 87.3 x 444 mm, 755.8 mm deep with bezel (683.7 without),
29.5 kg with 2.5 in drives (the heavier of its two maximums)."""


class Sacrifice(StrEnum):
    UNIT = "unit"
    """The rail takes the whole U below the server: deepest beam, ears stay on the hole pattern."""
    HOLE = "hole"
    """The rail stays in the server's units; the server rides HOLE_LIFT high on the ledge."""


WEB_THICKNESS = 12.0
RAIL_GAP = 1.0
"""Between the rack opening's edge and the web."""
LEDGE_REACH = 14.0
"""How far the ledge reaches in under the server, beyond the opening's edge."""
LEDGE_THICKNESS = 10.0
HOLE_LIFT = 12.0
"""Sacrifice.HOLE: the ledge's top above the server's U boundary."""
WEB_TOP_MARGIN = 6.0
"""The web stops this far under the server's top."""
LIP_HEIGHT = 8.0
LIP_LENGTH = 8.0
END_THICKNESS = 10.0
FLANGE_THICKNESS = 2.66
"""The thickest (12 gauge) post flange: pegs reach through it."""
PEG_WIDTH = 6.0
PEG_PROUD = 1.0
SEGMENT_MAX = 230.0
"""Longest segment the bed takes lying flat, with a margin."""
ENGAGE = 45.0
"""How far a splice plate reaches along each segment at a fixed joint."""
SPLICE_THICKNESS = 6.0
SPLICE_GAP = 0.3
PIN = 5.0
"""Diamond pin, across its flats."""
PIN_CLEARANCE = 0.2
PIN_INSET = 10.0
"""Pin rows sit this far inside the web's top and bottom."""
PITCH_A = 10.0
PITCH_B = 9.0
VERNIER_ENGAGE = 100.0
"""How far the vernier splice reaches along the rear segment at the longest span: a full cycle of ten
PITCH_B holes."""


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Part:
    """A box with its position in its geometry (translate), not its location: Component.assemble sets each
    part's location, which would put a lone `Pos(...) * Box(...)` back at the origin."""
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Box(x1 - x0, y1 - y0, z1 - z0).translate(Vector((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))


def _pin(x: float, y0: float, y1: float, z: float, size: float) -> Part:
    lo, hi = sorted((y0, y1))
    shape = Plane(origin=(x, lo, z), x_dir=(1, 0, 0), z_dir=(0, 1, 0)) * RegularPolygon(size / math.sqrt(2), 4)
    return extrude(shape, amount=hi - lo)


@dataclass(frozen=True)
class RailLayout:
    """One side's rail in the rack frame: x rearward from the front posts' front face, y across (the left
    rail at +y), z up from the bottom of the lowest unit the rail uses."""

    rack: RackStandard
    server: ServerSpec
    span: tuple[float, float]
    """Front posts' inner face to rear posts' inner face, shortest and longest; built at the shortest."""
    sacrifice: Sacrifice
    side: float

    @property
    def ledge_top(self) -> float:
        return RACK_UNIT if self.sacrifice is Sacrifice.UNIT else HOLE_LIFT

    @property
    def units(self) -> int:
        """Units the rail spans (the server's, plus the sacrificed one)."""
        return self.server.units + (1 if self.sacrifice is Sacrifice.UNIT else 0)

    @property
    def top(self) -> float:
        return self.ledge_top + self.server.height - WEB_TOP_MARGIN

    def y(self, inner: float, outer: float) -> tuple[float, float]:
        edge = self.rack.opening / 2
        return self.side * (edge + inner), self.side * (edge + outer)

    @property
    def web(self) -> tuple[float, float]:
        outer = max(RAIL_GAP + WEB_THICKNESS, self.rack.hole_spacing / 2 + PEG_WIDTH / 2 + 2 - self.rack.opening / 2)
        return self.y(RAIL_GAP, outer)

    @property
    def half(self) -> float:
        """The y splitting the web into its inner and outer halves, at the laps."""
        a, b = self.web
        return (a + b) / 2

    @property
    def front(self) -> float:
        return FLANGE_THICKNESS

    def rear(self, span: float) -> float:
        return FLANGE_THICKNESS + span

    @property
    def pin_rows(self) -> tuple[float, float]:
        """The pins' rows, as far apart as the web allows and clear of the ledge (a pin hole under the
        ledge would end in a ceiling): below it in the sacrificed U, else just above it."""
        low = self.bottom + PIN_INSET if self.sacrifice is Sacrifice.UNIT else self.ledge_top + PIN_INSET
        return low, self.top - PIN_INSET

    @property
    def bottom(self) -> float:
        return 0.0 if self.sacrifice is Sacrifice.UNIT else self.ledge_top - LEDGE_THICKNESS

    @property
    def travel(self) -> float:
        return self.span[1] - self.span[0]

    def butts(self) -> list[float]:
        """Rack x of each butt joint at the shortest span; the last is the vernier (near the rear, where the
        bending moment is smallest)."""
        reach = self.rear(self.span[0]) - self.front
        count = math.ceil(reach / SEGMENT_MAX)
        return [self.front + reach * k / count for k in range(1, count)]

    def segments(self) -> list[tuple[float, float]]:
        bounds = [self.front, *self.butts(), self.rear(self.span[0])]
        return list(itertools.pairwise(bounds))

    def splice(self, joint: int) -> tuple[float, float]:
        """A splice plate's rack x range at the shortest span."""
        butt = self.butts()[joint]
        if joint < len(self.butts()) - 1:
            return butt - ENGAGE, butt + ENGAGE
        return butt - ENGAGE, butt + VERNIER_ENGAGE + self.travel

    def is_vernier(self, joint: int) -> bool:
        return joint == len(self.butts()) - 1

    def splice_y(self) -> tuple[float, float]:
        _, wo = self.web
        return wo + self.side * SPLICE_GAP, wo + self.side * (SPLICE_GAP + SPLICE_THICKNESS)

    def holes(self, joint: int, piece: str) -> list[float]:
        """Pin holes at a joint, in the front segment, the rear segment or the plate. A fixed joint takes one
        column each side of the butt; the vernier's plate holes are PITCH_A apart over its rear reach and the
        rear segment's PITCH_B apart, the first of each lined up at the shortest span."""
        butt = self.butts()[joint]
        front = butt - ENGAGE / 2
        if not self.is_vernier(joint):
            rear = butt + ENGAGE / 2
            return {"front": [front], "rear": [rear], "plate": [front, rear]}[piece]
        first = butt + PITCH_A / 2
        if piece == "front":
            return [front]
        if piece == "rear":
            return [first + n * PITCH_B for n in range(int((VERNIER_ENGAGE - PITCH_A / 2 - PIN) // PITCH_B) + 1)]
        reach = VERNIER_ENGAGE + self.travel - PITCH_A / 2 - PIN
        return [front] + [first + n * PITCH_A for n in range(int(reach // PITCH_A) + 1)]

    def hole_heights(self) -> list[float]:
        heights = []
        for unit in range(self.units + 1):
            for offset in U_HOLE_OFFSETS:
                z = unit * RACK_UNIT + offset
                if self.bottom + 1 <= z - SQUARE_HOLE / 2 and z + SQUARE_HOLE / 2 <= self.top - 1:
                    heights.append(z)
        return heights

    def check(self) -> None:
        if self.server.width / 2 > self.rack.opening / 2:
            raise ValueError(f"{self.server.name} is wider than the {self.rack.name} opening")
        if self.server.width / 2 < self.rack.opening / 2 - LEDGE_REACH + 4:
            raise ValueError(f"The ledges would miss the {self.server.name}'s sides: it is too narrow for them")
        if self.span[1] < self.span[0]:
            raise ValueError(f"Rail span {self.span} runs backwards")
        limit = SEGMENT_MAX - ENGAGE - VERNIER_ENGAGE
        if self.travel > limit:
            raise ValueError(f"A rail adjusts over {limit:.0f} mm at most; build a kit for your rack's span range")


class RailSegment(Component):
    """One segment of a rail, placed for the shortest span. At each lap the front segment keeps the web's
    outer half and the rear one its inner half with the ledge, so the web stays whole across the joint."""

    def __init__(self, name: str, layout: RailLayout, index: int) -> None:
        super().__init__(name)
        self.layout, self.index = layout, index
        # Lying on its outer face: inboard is up in the print.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -layout.side, 0))).inverse()

    def solids(self) -> dict[str, Part]:
        g, k = self.layout, self.index
        segs = g.segments()
        x0, x1 = segs[k]
        wi, wo = g.web
        ledge_y = g.y(-LEDGE_REACH, RAIL_GAP)
        part = _box(x0, x1, wi, wo, g.bottom, g.top)
        part += _box(x0, x1, *ledge_y, g.ledge_top - LEDGE_THICKNESS, g.ledge_top)
        if k > 0:
            for x in g.holes(k - 1, "rear"):
                part -= self._holes(x)
        if k < len(segs) - 1:
            for x in g.holes(k, "front"):
                part -= self._holes(x)
        if k == 0:
            part += self._end(g.front, +1)
        if k == len(segs) - 1:
            rear = g.rear(g.span[0])
            part += self._end(rear, -1)
            lip_x = rear - END_THICKNESS
            part += _box(lip_x - LIP_LENGTH, lip_x, *ledge_y, g.ledge_top, g.ledge_top + LIP_HEIGHT)
        return {"part": part}

    def _holes(self, x: float) -> Part:
        g = self.layout
        wi, wo = g.web
        return _pin_pair(g, x, wi - g.side, wo + g.side, PIN + PIN_CLEARANCE)

    def _end(self, face: float, inward: float) -> Part:
        """An end plate bearing on a post's inner face, with a peg through every square hole it spans."""
        g = self.layout
        wi, wo = g.web
        plate = _box(face, face + inward * END_THICKNESS, wi, wo, g.bottom, g.top)
        hole_y = g.side * g.rack.hole_spacing / 2
        for z in g.hole_heights():
            low = z - SQUARE_HOLE / 2
            peg_y = (hole_y - g.side * PEG_WIDTH / 2, wo)
            plate += _box(
                face + inward * 0.5,
                face - inward * (FLANGE_THICKNESS + PEG_PROUD),
                *peg_y,
                low,
                low + SQUARE_HOLE - HOOK_VERTICAL_CLEARANCE,
            )
        return plate


def _pin_pair(g: RailLayout, x: float, y0: float, y1: float, size: float) -> Part:
    low, high = g.pin_rows
    return _pin(x, y0, y1, low, size) + _pin(x, y0, y1, high, size)


class SplicePlate(Component):
    """The plate on a rail's outer face that joins two segments, pinned to both."""

    def __init__(self, name: str, layout: RailLayout, joint: int) -> None:
        super().__init__(name)
        self.layout, self.joint = layout, joint
        # Lying flat on its outer face.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, -layout.side, 0))).inverse()

    def solids(self) -> dict[str, Part]:
        g = self.layout
        x0, x1 = g.splice(self.joint)
        y0, y1 = g.splice_y()
        plate = _box(x0, x1, y0, y1, g.bottom, g.top)
        for x in g.holes(self.joint, "plate"):
            plate -= _pin_pair(g, x, y0 - g.side, y1 + g.side, PIN + PIN_CLEARANCE)
        return {"part": plate}


class RailPin(Component):
    """A diamond pin through a lap, printed lying on a flat face so it shears across its layers."""

    def __init__(self, name: str, layout: RailLayout, x: float, z: float) -> None:
        super().__init__(name)
        self.layout, self.x, self.z = layout, x, z
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 1))).inverse()

    def solids(self) -> dict[str, Part]:
        g = self.layout
        wi, _ = g.web
        _, outer = g.splice_y()
        return {"part": _pin(self.x, wi, outer + g.side * 1.0, self.z, PIN)}


@dataclass(frozen=True)
class Strength:
    """Closed-form margins for one rail carrying half the server (x2 is the target, on PLA's 51 MPa)."""

    bending: float
    lap_pins: float
    deflection: float
    """mm at mid-span."""


def rail_strength(layout: RailLayout, strength: float = 51.0, modulus: float = 2300.0) -> Strength:
    """Half the server as a point load at mid-span (worse than its spread weight), the rail a simply
    supported beam at its longest span: bending at the half-web laps, and the pins' bearing in a half web
    (the lap moment as a couple between the two pin rows)."""
    load = layout.server.mass * 1000 * GRAVITY / 2
    span = layout.span[1]
    moment = load * span / 4
    height = layout.top - layout.bottom
    thickness = abs(layout.web[1] - layout.web[0])
    # At a joint the moment passes through the splice plate (the thinner part) and its pins' couple.
    bending = moment / (SPLICE_THICKNESS * height**2 / 6)
    couple = moment / (layout.pin_rows[1] - layout.pin_rows[0])
    bearing = couple / (PIN * SPLICE_THICKNESS)
    second = thickness * height**3 / 12
    return Strength(strength / bending, strength / bearing, load * span**3 / (48 * modulus * second))


class ServerRails(Component):
    """A pair of rails for one server in a four-post square-hole rack, with their pins."""

    def __init__(
        self,
        server: ServerSpec = DELL_R720,
        span: tuple[float, float] = (690.0, 750.0),
        sacrifice: Sacrifice = Sacrifice.UNIT,
        rack: RackStandard = RACK_19_INCH,
        bed: Bed = MK3S_BED,
        shelf: bool = False,
    ) -> None:
        super().__init__(f"rails_{server.name.split()[-1].lower()}_{sacrifice.value}")
        self.server, self.bed = server, bed
        for side_name, side in (("left", 1.0), ("right", -1.0)):
            layout = RailLayout(rack, server, span, sacrifice, side)
            layout.check()
            for k in range(len(layout.segments())):
                self.add_child(RailSegment(f"{self.name}_{side_name}_{k}", layout, k))
            for j in range(len(layout.butts())):
                self.add_child(SplicePlate(f"{self.name}_{side_name}_splice_{j}", layout, j))
                # At the shortest span the vernier's first plate hole lines up with the rear segment's first.
                pins = [layout.holes(j, "front")[0], layout.holes(j, "rear")[0]]
                for n, x in enumerate(pins):
                    for m, z in enumerate(layout.pin_rows):
                        self.add_child(RailPin(f"{self.name}_{side_name}_pin_{j}{n}{m}", layout, x, z))
            self.layout = layout
        if shelf:
            if sacrifice is not Sacrifice.UNIT:
                raise ValueError("A shelf's beams hang in the sacrificed unit: use Sacrifice.UNIT")
            self.shelf = ShelfLayout(self.layout)
            for n, x in enumerate(self.shelf.beams()):
                for half, side_name in ((1.0, "left"), (-1.0, "right")):
                    self.add_child(ShelfBeam(f"{self.name}_beam_{n}_{side_name}", self.shelf, x, half))
                self.add_child(BeamSplice(f"{self.name}_beam_{n}_splice", self.shelf, x))
            for n, tile in enumerate(deck_tiles(self.shelf, bed)):
                self.add_child(DeckPlate(f"{self.name}_deck_{n}", self.shelf, *tile))

    def solids(self) -> dict[str, Part]:
        return {}


BEAM_THICKNESS = 10.0
"""A shelf cross-beam, along the rack."""
BEAM_TAB = 6.0
"""A beam's end, over the ledge it sits on."""
BEAM_SPACING = 150.0
"""Most a deck plate spans between beams."""
DECK_THICKNESS = 6.0
BEAM_SPLICE = 60.0
"""A beam's centre splice plate, each side of the joint."""
STRENGTH_PLA = 51.0
SAFETY = 2.0


@dataclass(frozen=True)
class ShelfLayout:
    rails: RailLayout
    """The left rail's layout (the right mirrors it)."""

    @property
    def beam_span(self) -> tuple[float, float]:
        """y of a beam's ends: over each ledge, short of the webs."""
        edge = self.rails.rack.opening / 2
        return -(edge + RAIL_GAP - 0.5), edge + RAIL_GAP - 0.5

    @property
    def beam_z(self) -> tuple[float, float]:
        """A beam hangs in the sacrificed U; its notched ends sit on the ledges with BEAM_TAB of plastic
        above them, and the deck lies on its top."""
        return 0.5, self.rails.ledge_top + BEAM_TAB

    def beams(self) -> list[float]:
        g = self.rails
        x0, x1 = (
            g.front + END_THICKNESS + BEAM_THICKNESS,
            g.rear(g.span[0]) - END_THICKNESS - LIP_LENGTH - BEAM_THICKNESS,
        )
        count = math.ceil((x1 - x0) / BEAM_SPACING) + 1
        return [x0 + (x1 - x0) * k / (count - 1) for k in range(count)]

    def pin_rows(self) -> tuple[float, float]:
        z0, z1 = self.beam_z
        return z0 + PIN_INSET, z1 - PIN_INSET

    def capacity(self) -> float:
        """kg the shelf carries at x2: each beam a point load at its centre (worse than a spread load),
        limited by bending at the splice plate and the bearing of its pins' couple."""
        z0, z1 = self.beam_z
        height, span = z1 - z0, self.beam_span[1] - self.beam_span[0]
        allow = STRENGTH_PLA / SAFETY
        moment = min(allow * BEAM_THICKNESS * height**2 / 6, allow * PIN * BEAM_THICKNESS * (z1 - z0 - 2 * PIN_INSET))
        per_beam = 4 * moment / span
        return len(self.beams()) * per_beam / (1000 * GRAVITY)


def deck_tiles(shelf: ShelfLayout, bed: Bed) -> list[tuple[float, float, float, float]]:
    """Deck plates: each spans between two neighbouring beams (held on both those edges) and, across the
    rack, a bed-sized share of the width between the webs."""
    edge = shelf.rails.rack.opening / 2 + RAIL_GAP - 0.5
    beams = shelf.beams()
    chunks = math.ceil(2 * edge / min(bed.usable_x, bed.usable_y))
    ys = [-edge + 2 * edge * k / chunks for k in range(chunks + 1)]
    tiles = []
    for n, (a, b) in enumerate(itertools.pairwise(beams)):
        # Neighbouring plates share a beam's top, half each; the end plates take the whole end beam.
        x0 = a if n == 0 else a + BEAM_THICKNESS / 2 + 0.25
        x1 = b + BEAM_THICKNESS if n == len(beams) - 2 else b + BEAM_THICKNESS / 2 - 0.25
        for y0, y1 in itertools.pairwise(ys):
            tiles.append((x0, x1, y0 + 0.25, y1 - 0.25))
    return tiles


class ShelfBeam(Component):
    """Half a cross-beam (`half` +1 left, -1 right): hangs from a ledge by its notched end."""

    def __init__(self, name: str, shelf: ShelfLayout, x: float, half: float) -> None:
        super().__init__(name)
        self.shelf, self.x, self.half = shelf, x, half
        # Lying on its rear face: forward is up.
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))).inverse()

    def solids(self) -> dict[str, Part]:
        s, g = self.shelf, self.shelf.rails
        z0, z1 = s.beam_z
        end = s.beam_span[1] * self.half
        beam = _box(self.x, self.x + BEAM_THICKNESS, 0.0, end, z0, z1)
        # Its end sits on the ledge: cut away below the ledge's top over the ledge's width.
        ledge_inner = self.half * (g.rack.opening / 2 - LEDGE_REACH - 0.5)
        beam -= _box(self.x - 1, self.x + BEAM_THICKNESS + 1, ledge_inner, end + self.half, z0 - 1, g.ledge_top)
        for y in _beam_pins(self.half):
            for z in s.pin_rows():
                beam -= _cross_pin(self.x - 1, self.x + BEAM_THICKNESS + 1, y, z, PIN + PIN_CLEARANCE)
        return {"part": beam}


def _beam_pins(half: float) -> list[float]:
    return [half * BEAM_SPLICE / 2]


def _cross_pin(x0: float, x1: float, y: float, z: float, size: float) -> Part:
    shape = Plane(origin=(x0, y, z), x_dir=(0, 1, 0), z_dir=(1, 0, 0)) * RegularPolygon(size / math.sqrt(2), 4)
    return extrude(shape, amount=x1 - x0)


class BeamSplice(Component):
    """The plate on a beam's front face joining its two halves, pinned to both."""

    def __init__(self, name: str, shelf: ShelfLayout, x: float) -> None:
        super().__init__(name)
        self.shelf, self.x = shelf, x
        self.print_location = Location(Plane(origin=(0, 0, 0), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))).inverse()

    def solids(self) -> dict[str, Part]:
        s = self.shelf
        z0, z1 = s.beam_z
        x0 = self.x - SPLICE_GAP - SPLICE_THICKNESS
        # Below the deck: the splice stops under the beam's top.
        plate = _box(x0, self.x - SPLICE_GAP, -BEAM_SPLICE, BEAM_SPLICE, z0, z1 - DECK_THICKNESS)
        for y in _beam_pins(1.0) + _beam_pins(-1.0):
            for z in s.pin_rows():
                plate -= _cross_pin(x0 - 1, self.x + 1, y, z, PIN + PIN_CLEARANCE)
        return {"part": plate}


class DeckPlate(Component):
    """A deck plate lying across the beams, between the rails' webs."""

    def __init__(self, name: str, shelf: ShelfLayout, x0: float, x1: float, y0: float, y1: float) -> None:
        super().__init__(name)
        self.shelf, self.bounds = shelf, (x0, x1, y0, y1)

    def solids(self) -> dict[str, Part]:
        x0, x1, y0, y1 = self.bounds
        top = self.shelf.beam_z[1]
        return {"part": _box(x0, x1, y0, y1, top, top + DECK_THICKNESS)}


def rail_capacity(layout: RailLayout) -> float:
    """kg a pair of rails carries at x2: rail_strength's margins scale with the load."""
    margins = rail_strength(layout)
    return layout.server.mass * min(margins.bending, margins.lap_pins) / SAFETY


def shelf_capacity(rails: ServerRails) -> float:
    """kg a shelf carries at x2: the weaker of its beams and the rails under them."""
    return min(rails.shelf.capacity(), rail_capacity(rails.layout))
