# SPDX-License-Identifier: AGPL-3.0-or-later
"""Front power: an ATX supply in a front bay with its fan and inlet facing out, and a power button.

`PowerSupplyBay` is a front module. The supply's rear face (fan grille, inlet and switch) screws to the
bay's face plate through its four 6-32 holes, so the cord plugs in at the front and the supply's steel case
stiffens the front of the box. Its body rests on the floor (or the shelf below) between the bay's side
plates, which guide any length up to the spec's longest. On its edge it is 86 mm across and 150 mm tall
(a 4U box); flat it is 150 across and 86 tall (3U). Behind it the board sits at the rear wall, so a
board-width box with the supply in front is as narrow as the board allows.

`PowerButton` is a face with a round cut-out for a panel-mount momentary switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cassette import FACE_THICKNESS, REAR_GAP, SIDE_THICKNESS, VENT_MARGIN, Blank, Cassette, CassetteSlot, ModuleKind
from .joints import Hardware, edge_joint
from .plate import Edge, Plate, RectCut, ThroughHole
from .standards import ATX_PSU, PowerSupplySpec

PSU_SIDE_CLEARANCE = 1.0
"""Between the supply's body and each side plate."""
PSU_TOP_CLEARANCE = 2.0
"""Above the supply's body, under the shelf or cover."""
PSU_OPENING_INSET = 12.0
"""The face's opening for the supply's fan and inlet stops this far inside its outline, clear of the screws."""
PSU_SCREW = "6-32 UNC x 1/4 in pan head (power supply)"
BUTTON_DIAMETER = 16.0
"""A common panel cut-out for a momentary anti-vandal switch (12, 16, 19 and 22 mm are all sold); pass yours."""
BUTTON_MARGIN = 6.0
"""Plastic kept round the button's cut-out, above and below."""


def psu_on_edge_fits(height: float, spec: PowerSupplySpec = ATX_PSU) -> bool:
    """Whether a supply stands on its edge in this much height."""
    return spec.width + PSU_TOP_CLEARANCE <= height


@dataclass
class PowerSupplyBay(ModuleKind):
    rows: int = 1
    on_edge: bool = True
    """Standing on its long edge (86 across, 150 tall), or flat (150 across, 86 tall)."""
    length: float = ATX_PSU.lengths[1]
    """The longest body the bay takes; the side plates run this far back."""
    spec: PowerSupplySpec = ATX_PSU

    @property
    def across(self) -> float:
        return self.spec.height if self.on_edge else self.spec.width

    @property
    def tall(self) -> float:
        return self.spec.width if self.on_edge else self.spec.height

    def min_width(self) -> float:
        return self.across + 2 * PSU_SIDE_CLEARANCE + 2 * SIDE_THICKNESS

    def front_x(self) -> float:
        return FACE_THICKNESS

    def depth(self) -> float:
        return self.length + REAR_GAP

    def fits(self, slot: CassetteSlot) -> bool:
        return self.tall + PSU_TOP_CLEARANCE <= slot.z_top - slot.z_bottom

    def build(self, cassette: Cassette) -> Hardware:
        s = cassette.slot
        if not self.fits(s):
            orientation = "on its edge" if self.on_edge else "flat"
            raise ValueError(
                f"{cassette.name}: a {self.spec.name} supply {orientation} is {self.tall:.0f} mm tall; the bay has "
                f"{s.z_top - s.z_bottom:.1f} mm"
            )
        face = cassette.add_face(f"{cassette.name}_face")
        self._cut_face(face, s.z_bottom - s.face_bottom)
        hardware = edge_joint(face, cassette.left, Edge.U0)
        hardware.items += edge_joint(face, cassette.right, Edge.U1).items
        hardware.items += [PSU_SCREW] * len(self.spec.holes)
        return hardware

    def to_face(self, face: Plate, bottom: float, x: float, y: float) -> tuple[float, float]:
        """A point of the supply's rear face (spec x right, y up, as seen from the front of the chassis) in the
        face plate's (u, v). The plate's u runs toward the chassis's left, so it runs against the viewer's x.
        On its edge the supply is turned a quarter, not mirrored."""
        across, up = (self.spec.height - y, x) if self.on_edge else (x, y)
        return face.length / 2 + self.across / 2 - across, bottom + up

    def _cut_face(self, face: Plate, bottom: float) -> None:
        spec = self.spec
        for x, y in spec.holes:
            u, v = self.to_face(face, bottom, x, y)
            face.add(ThroughHole(u, v, spec.screw_clearance))
        corners = [
            self.to_face(face, bottom, PSU_OPENING_INSET, PSU_OPENING_INSET + 6),
            self.to_face(face, bottom, spec.width - PSU_OPENING_INSET, spec.height - PSU_OPENING_INSET),
        ]
        us, vs = sorted(c[0] for c in corners), sorted(c[1] for c in corners)
        face.add(RectCut(us[0], vs[0], us[1], vs[1]))


@dataclass
class PowerButton(Blank):
    """A face with a round cut-out for a panel-mount power switch."""

    diameter: float = BUTTON_DIAMETER

    def min_width(self) -> float:
        return max(self.width, self.diameter + 2 * (SIDE_THICKNESS + VENT_MARGIN))

    def fits(self, slot: CassetteSlot) -> bool:
        return self.diameter + 2 * BUTTON_MARGIN <= slot.face_top - slot.face_bottom

    def decorate(self, face: Plate) -> None:
        if face.width < self.diameter + 2 * BUTTON_MARGIN:
            raise ValueError(f"A {self.diameter:.0f} mm button needs a {self.diameter + 2 * BUTTON_MARGIN:.0f} mm face")
        face.add(ThroughHole(face.length / 2, face.width / 2, self.diameter))
