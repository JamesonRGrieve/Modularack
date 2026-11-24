# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every strength check for every common printing material, at ambient temperatures in 5 degree steps.

The analysis is linear and each part is one material, so a stress field doesn't depend on the material's
stiffness, only on the load. One run in PLA (`fea`, `joint_fea`) therefore gives every material, two
scalings apart:

- **load:** the printed parts weigh in at the material's density (`fea.chassis_mass`), so every stress the
  chassis's weight drives scales by that mass over PLA's. (The tool-less cover's 200 N lift does not.)
- **allowable:** the material's own strength (in the layers, and across them for interlayer stresses), times
  its retention at that temperature, `retention`.

Retention is a conservative piecewise-linear model, not a measured curve: strength is taken to fall with the
storage modulus E', which the one DMA study found for these materials (Polymers 2024, 16(21), 3018, PMC11548368,
three-point bend, 3 Hz, 2 K/min) reports from 20 to 40 degrees C (its Table 9), and to reach nothing at
`Softening.end`: the lower of the E' onset of the glass transition from the same study and the material's heat
deflection temperature at 1.80 MPa (ISO 75, from its data sheet). A real E' curve stays flatter to near Tg and
then falls steeply, so the straight line under-rates the middle of the range: a factor here is a floor.

It is short-term strength. A part held at load near its softening point also creeps, which no factor here
covers: for PLA in particular, keep the ambient well under the temperature its factor first falls below x2, and
alarm on it (see `alarm_temperature`).
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from .chassis import RackChassis
from .fea import (
    ABS,
    ASA,
    PA,
    PC,
    PETG,
    PLA,
    SAFETY_FACTOR,
    Material,
    chassis_mass,
    ear_as_printed,
    knee_brace_strut,
    wall_as_printed,
)

logger = logging.getLogger(__name__)

REFERENCE_TEMPERATURE = 23.0
"""Data sheet values are measured at room temperature."""
DMA_PLATEAU_END = 40.0
"""The top of the DMA study's tabulated 20-40 degree range."""
TEMPERATURES = tuple(range(20, 125, 5))
OUTPUT_DIR = Path("build/thermal")


@dataclass(frozen=True)
class Softening:
    material: Material
    retention_40: float | None
    """E' at 40 degrees over E' at 20, from the DMA study's Table 9; None where no DMA was found."""
    end: float
    """Degrees C taken as no strength left."""
    source: str


SOFTENING: dict[str, Softening] = {
    "pla": Softening(PLA, 1820 / 1980, 59.1, "E' 1980 -> 1820 (20-40 C); E' onset of Tg 59.1 C"),
    "petg": Softening(
        PETG, 883 / 1100, 68.0, "E' 1100 -> 883 (20-40 C); E' onset 80.7 C; Prusament PETG HDT (1.80 MPa) 68 C"
    ),
    "abs": Softening(ABS, 875 / 1030, 98.0, "E' 1030 -> 875 (20-40 C); E' onset 110.8 C; PolyLite ABS HDT 98 C"),
    "asa": Softening(ASA, 976 / 1210, 86.0, "E' 1210 -> 976 (20-40 C); E' onset 105.7 C; Prusament ASA HDT 86 C"),
    "pc": Softening(PC, None, 93.0, "no DMA found: straight from 23 C to Prusament PC Blend's HDT (1.80 MPa), 93 C"),
    "pa": Softening(PA, 726 / 891, 44.4, "E' 891 -> 726 (20-40 C); E' onset 44.4 C (CoPA HDT 70 C)"),
}


def retention(softening: Softening, temperature: float) -> float:
    """Strength at `temperature` as a fraction of the data sheet's (see the module docstring)."""
    if temperature <= REFERENCE_TEMPERATURE:
        return 1.0
    if temperature >= softening.end:
        return 0.0
    if softening.retention_40 is None or softening.end <= DMA_PLATEAU_END:
        start, at_start = REFERENCE_TEMPERATURE, 1.0
    else:
        if temperature <= DMA_PLATEAU_END:
            span = DMA_PLATEAU_END - REFERENCE_TEMPERATURE
            return 1.0 - (1.0 - softening.retention_40) * (temperature - REFERENCE_TEMPERATURE) / span
        start, at_start = DMA_PLATEAU_END, softening.retention_40
    return at_start * (softening.end - temperature) / (softening.end - start)


@dataclass(frozen=True)
class Row:
    design: str
    material: str
    temperature: int
    retention: float
    ear_in_layer: float
    ear_across_layers: float
    wall: float
    strut: float | None
    joints: float | None
    """The weakest tool-less joint (dovetail tabs and lips, drawer rails), if the design has any."""

    @property
    def worst(self) -> float:
        factors = [self.ear_in_layer, self.ear_across_layers, self.wall]
        factors += [f for f in (self.strut, self.joints) if f is not None]
        return min(factors)


@dataclass(frozen=True)
class Basis:
    """The PLA stresses one design's checks found, at PLA's weight, from which every row is scaled."""

    ear_in_layer: float
    ear_across_layers: float
    wall: float
    strut_stress: float | None
    strut_buckling_margin: float | None
    """Euler load over axial force, in PLA."""
    joints: list[tuple[float, float, bool]]
    """(in-layer stress, interlayer stress, driven by the chassis's weight) per joint, MPa at its demand."""


def basis(name: str, chassis: RackChassis, joints: bool = True) -> Basis:
    ear = ear_as_printed(name, chassis)
    across = max(ear.across_layer_tension, ear.interlayer_shear, ear.interlayer_combined)
    wall = wall_as_printed(name, chassis)
    stress = margin = None
    if chassis.knee_brace_units is not None:
        strut = knee_brace_strut(name, chassis)
        stress, margin = strut.stress, strut.buckling_load / strut.axial_force
    found: list[tuple[float, float, bool]] = []
    if joints and chassis.toolless_box:
        from .joint_fea import REFERENCE_LOAD, analyse_dovetails, analyse_rails

        results = analyse_dovetails(name, chassis)
        if chassis.toolless_modules:
            results += analyse_rails(name, chassis)[0]
        for r in results:
            scale = r.demand_n / REFERENCE_LOAD
            worst = max(r.result.across_layer_tension, r.result.interlayer_shear, r.result.interlayer_combined)
            found.append((r.result.in_layer * scale, worst * scale, r.joint != "cover lip"))
    return Basis(ear.in_layer, across, wall.bending_stress, stress, margin, found)


def rows(name: str, chassis: RackChassis, base: Basis) -> list[Row]:
    pla_mass = chassis_mass(chassis)
    out: list[Row] = []
    for key, softening in SOFTENING.items():
        m = softening.material
        weight = chassis_mass(chassis, m) / pla_mass
        for temperature in TEMPERATURES:
            r = retention(softening, temperature)
            inside, across = m.in_layer_strength * r, m.interlayer_strength * r
            strut = None
            if base.strut_stress is not None and base.strut_buckling_margin is not None:
                buckling = base.strut_buckling_margin * (m.modulus / PLA.modulus) * r / weight
                strut = min(inside / (base.strut_stress * weight), buckling)
            joint = None
            if base.joints:
                joint = min(
                    min(inside / (s_in * (weight if w else 1.0)), across / (s_across * (weight if w else 1.0)))
                    for s_in, s_across, w in base.joints
                )
            out.append(
                Row(
                    name,
                    key,
                    temperature,
                    r,
                    inside / (base.ear_in_layer * weight),
                    across / (base.ear_across_layers * weight),
                    inside / (base.wall * weight),
                    strut,
                    joint,
                )
            )
    return out


def alarm_temperature(design_rows: list[Row], material: str) -> int | None:
    """The highest 5 degree step at which every check of the design still holds x2 in `material`."""
    ok = [r.temperature for r in design_rows if r.material == material and r.worst >= SAFETY_FACTOR]
    return max(ok) if ok else None


def write(all_rows: list[Row], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "thermal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*asdict(all_rows[0]), "worst"])
        writer.writeheader()
        for r in all_rows:
            writer.writerow({**asdict(r), "worst": r.worst})
    designs = sorted({r.design for r in all_rows})
    lines = ["# Strength against temperature", ""]
    lines += [
        "Worst factor of every check (ears, walls, struts, tool-less joints), by material and ambient temperature."
    ]
    lines += ["x2 passes. The highest passing step is the temperature to alarm at, with margin for creep.", ""]
    for design in designs:
        sub = [r for r in all_rows if r.design == design]
        lines += [f"## {design}", "", "| C | " + " | ".join(SOFTENING) + " |", "|---|" + "---|" * len(SOFTENING)]
        for t in TEMPERATURES:
            cells = [next(r for r in sub if r.material == k and r.temperature == t).worst for k in SOFTENING]
            lines.append(f"| {t} | " + " | ".join(f"x{c:.2f}" if c > 0 else "0" for c in cells) + " |")
        alarms = {k: alarm_temperature(sub, k) for k in SOFTENING}
        lines += ["", "Highest step at x2: " + ", ".join(f"{k} {v} C" if v else f"{k} none" for k, v in alarms.items())]
        lines.append("")
    lines += ["## Sources", ""] + [f"- {k}: {s.material.name}; {s.source}" for k, s in SOFTENING.items()]
    (output / "thermal.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    from .reference import reference_builders

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Strength of the reference chassis by material and temperature.")
    parser.add_argument("names", nargs="*", help="reference designs (default: every chassis)")
    parser.add_argument("--no-joints", action="store_true", help="skip the tool-less joints' FEA")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    builders = reference_builders()
    names = args.names or [n for n in builders if n.startswith("chassis_")]
    all_rows: list[Row] = []
    for name in names:
        chassis = builders[name]()
        assert isinstance(chassis, RackChassis)
        design_rows = rows(name, chassis, basis(name, chassis, joints=not args.no_joints))
        all_rows += design_rows
        logger.info(
            "%s: highest step at x2 %s",
            name,
            ", ".join(f"{k} {alarm_temperature(design_rows, k)}" for k in SOFTENING),
        )
    write(all_rows, args.output)


if __name__ == "__main__":
    main()
