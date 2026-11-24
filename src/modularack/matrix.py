# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every discrete configuration of a chassis, filled to its heaviest load.

A configuration picks one value on each axis: rack width, height, board, ear style, one-piece corners,
extra support, how tool-less the box is, and where the power supply goes. `configurations()` is every
combination. `Config.chassis()` builds one, filled the same way every time:

- a front power supply (`power.PowerSupplyBay`) at the left, on its edge if the box is tall enough,
  with a power button and the largest intake fan that fits beside it;
- then, row by row, a 3.5 in bay wherever one fits, else a 2.5 in bay, and blanks in what is left.

That fill is the heaviest the front grid takes, so a configuration that carries it carries any lighter
fill. A combination the parts can't make (an ATX board in a 10 in box, a tool-less ATX box at 14.5 in, a front
supply in 2U) is refused with a ValueError, and `build_matrix` records the reason.

`uv run python -m modularack.matrix [--render] [--fea] [--jobs N] [--only SUBSTRING]` builds and checks
every configuration (optionally rendering each and running its strength checks) and writes
`build/matrix/report.csv` and `build/matrix/index.html`.
"""

from __future__ import annotations

import argparse
import csv
import html
import itertools
import logging
import os
import traceback
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from pathlib import Path

from .cassette import Blank, DriveBay, ModuleKind, cells_for
from .chassis import GRID_COLUMNS, EarStyle, RackChassis
from .fans import FanBay
from .power import PowerButton, PowerSupplyBay, psu_on_edge_fits
from .standards import (
    ATX,
    CEB,
    DRIVE_2_5,
    DRIVE_3_5,
    E_ATX,
    EEB,
    FANS,
    MICRO_ATX,
    MINI_ITX,
    RACK_10_INCH,
    RACK_14_5_INCH,
    RACK_15_INCH,
    RACK_19_INCH,
    MotherboardFormFactor,
    RackStandard,
)
from .web import PostChannel

logger = logging.getLogger(__name__)

RACKS: dict[str, RackStandard] = {r.name: r for r in (RACK_10_INCH, RACK_14_5_INCH, RACK_15_INCH, RACK_19_INCH)}
BOARDS: dict[str, MotherboardFormFactor | None] = {
    "none": None,
    "mini-itx": MINI_ITX,
    "micro-atx": MICRO_ATX,
    "atx": ATX,
    "e-atx": E_ATX,
    "ssi-ceb": CEB,
    "ssi-eeb": EEB,
}
DEPTHS = {RACK_10_INCH.name: 380.0, RACK_14_5_INCH.name: 470.0, RACK_15_INCH.name: 470.0, RACK_19_INCH.name: 470.0}
"""The shortest depth each width is built at; a board behind deep modules makes it deeper."""
REAR_SPAN = (520.0, 640.0)
OUTPUT_DIR = Path("build/matrix")


class Support(StrEnum):
    NONE = "none"
    KNEE_1 = "knee1"
    KNEE_2 = "knee2"
    REAR = "rear"
    WEB = "web"


class Toolless(StrEnum):
    NONE = "none"
    COVER = "cover"
    BOX = "box"
    FULL = "full"
    """Box, drawers and pinned sleds."""


class Power(StrEnum):
    NONE = "none"
    REAR = "rear"
    FRONT = "front"


@dataclass(frozen=True)
class Config:
    rack: str
    units: int
    board: str
    ears: EarStyle
    one_piece: bool
    support: Support
    toolless: Toolless
    power: Power

    @property
    def name(self) -> str:
        parts = [self.rack, f"{self.units}U", self.board, str(self.ears)]
        parts += ["1p"] if self.one_piece else []
        parts += [f"support-{self.support}", f"tl-{self.toolless}", f"psu-{self.power}"]
        return "_".join(parts)

    @property
    def structure(self) -> tuple[object, ...]:
        """What the ear and wall strength depends on, apart from the load: one FEA run covers every
        configuration with the same structure at or below its load."""
        return (self.rack, self.units, self.ears, self.one_piece, self.support, self.toolless)

    def chassis(self) -> RackChassis:
        rack, board = RACKS[self.rack], BOARDS[self.board]
        toolless_box = self.toolless in (Toolless.BOX, Toolless.FULL)
        chassis = RackChassis(
            rack,
            self.units,
            DEPTHS[rack.name],
            board,
            ear_style=self.ears,
            one_piece=self.one_piece,
            knee_brace_units={Support.KNEE_1: 1, Support.KNEE_2: 2}.get(self.support),
            rear_support=REAR_SPAN if self.support is Support.REAR else None,
            web_clamp=PostChannel() if self.support is Support.WEB else None,
            toolless_cover=self.toolless is Toolless.COVER,
            toolless_box=toolless_box,
            toolless_modules=self.toolless is Toolless.FULL,
            toolless_sleds=self.toolless is Toolless.FULL,
            power_supply=self.power is Power.REAR,
        )
        populate(chassis, front_power=self.power is Power.FRONT)
        absorb_slivers(chassis)
        chassis.depth = max(chassis.depth, chassis.minimum_depth())
        chassis.build()
        return chassis


def configurations() -> Iterator[Config]:
    for values in itertools.product(RACKS, range(1, 5), BOARDS, EarStyle, (False, True), Support, Toolless, Power):
        yield Config(*values)


def _try(chassis: RackChassis, kind: ModuleKind, column: int, row: int, columns: int | None = None) -> bool:
    span = columns if columns is not None else cells_for(kind, chassis.cell_width)
    if span > chassis.max_module_columns or not chassis.is_available(column, row, span, kind.rows):
        return False
    if span * chassis.cell_width < kind.min_width() - 1e-6:
        return False
    if not chassis.face_fits(kind, column, row, span):
        return False
    chassis.add_module(kind, column, row, span)
    return True


def populate(chassis: RackChassis, front_power: bool) -> None:
    """The matrix's standard fill (see the module docstring)."""
    if front_power:
        on_edge = psu_on_edge_fits(chassis.inner_height)
        psu = PowerSupplyBay(rows=chassis.units, on_edge=on_edge)
        if not _try(chassis, psu, 0, 0):
            raise ValueError(f"{chassis.name}: no room for a front power supply")
        start = cells_for(psu, chassis.cell_width)
        button = PowerButton()
        button_columns = cells_for(button, chassis.cell_width)
        top = chassis.units - 1
        if not _try(chassis, button, GRID_COLUMNS - button_columns, top):
            raise ValueError(f"{chassis.name}: no room for a power button beside the power supply")
        # The largest fan in the block beside the supply, below the button's row (or beside it in 1U).
        fan_rows = max(chassis.units - 1, 1)
        for size in sorted(FANS, reverse=True):
            fan = FanBay(rows=fan_rows, size=size)
            if _try(chassis, fan, start, 0, cells_for(fan, chassis.cell_width)):
                break
    for row in range(chassis.units):
        column = 0
        while column < GRID_COLUMNS:
            if not chassis.is_available(column, row, 1, 1):
                column += 1
                continue
            end = column
            while end < GRID_COLUMNS and chassis.is_available(end, row, 1, 1):
                end += 1
            for drive in (DRIVE_3_5, DRIVE_2_5):
                bay = DriveBay(drive, pinned=chassis.toolless_sleds)
                span = cells_for(bay, chassis.cell_width)
                # A sliver too narrow for a blank goes to the bay instead.
                left = end - column - span
                if left > 0 and cells_for(Blank(), chassis.cell_width) > left:
                    span += left
                if _try(chassis, bay, column, row, span):
                    column += span
                    break
            else:
                column += 1


def absorb_slivers(chassis: RackChassis) -> None:
    """Widen a one-row module beside each free run too narrow for a blank, so the grid closes."""
    narrowest = cells_for(Blank(), chassis.cell_width)
    for row in range(chassis.units):
        column = 0
        while column < GRID_COLUMNS:
            if not chassis.is_available(column, row, 1, 1):
                column += 1
                continue
            end = column
            while end < GRID_COLUMNS and chassis.is_available(end, row, 1, 1):
                end += 1
            if end - column < narrowest:
                left = [
                    p
                    for p in chassis.placements
                    if p.row == row and p.kind.rows == 1 and p.column + p.columns == column
                ]
                right = [p for p in chassis.placements if p.row == row and p.kind.rows == 1 and p.column == end]
                grown = left[0] if left else right[0] if right else None
                if grown is None or grown.columns + end - column > chassis.max_module_columns:
                    raise ValueError(f"{chassis.name}: a {end - column}-column gap in row {row} is too narrow to close")
                if grown in right:
                    grown.column = column
                grown.columns += end - column
                for c in range(column, end):
                    chassis.occupied[row][c] = True
            column = end


@dataclass
class Outcome:
    name: str
    status: str
    """built, refused or error."""
    reason: str = ""
    parts: int = 0
    clean: bool = False
    mass_kg: float = 0.0
    depth: float = 0.0
    width: float = 0.0
    ear_in_layer: float = 0.0
    ear_interlayer: float = 0.0
    wall: float = 0.0
    strut: float = 0.0
    passes: bool | None = None
    render: str = ""


def run_one(config: Config, render: bool, fea: bool, output: Path) -> Outcome:
    from .checks import check

    outcome = Outcome(config.name, "error")
    try:
        chassis = config.chassis()
    except ValueError as refusal:
        outcome.status, outcome.reason = "refused", str(refusal)
        return outcome
    except Exception:
        outcome.reason = traceback.format_exc(limit=3)
        return outcome
    try:
        report = check(chassis)
        outcome.status = "built"
        outcome.parts, outcome.clean = report.parts, report.clean
        outcome.depth, outcome.width = chassis.depth, chassis.floor_width
        if not report.clean:
            outcome.reason = str(report)
        if render:
            from .render import render_views

            path = output / "renders" / f"{config.name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            render_views(chassis.assemble_with_bought_parts(), path, config.name)
            outcome.render = str(path.relative_to(output))
        if fea:
            _strength(config, chassis, outcome)
    except Exception:
        outcome.status = "error"
        outcome.reason = traceback.format_exc(limit=3)
    return outcome


def _strength(config: Config, chassis: RackChassis, outcome: Outcome) -> None:
    from .fea import SAFETY_FACTOR, chassis_mass, ear_as_printed, knee_brace_strut, wall_as_printed

    outcome.mass_kg = chassis_mass(chassis) / 1000
    ear = ear_as_printed(config.name, chassis)
    outcome.ear_in_layer, outcome.ear_interlayer = ear.in_layer_factor, ear.interlayer_factor
    outcome.wall = wall_as_printed(config.name, chassis).factor
    passes = ear.passes and outcome.wall >= SAFETY_FACTOR
    if chassis.knee_brace_units is not None:
        strut = knee_brace_strut(config.name, chassis)
        outcome.strut = min(strut.strength_factor, strut.buckling_factor)
        passes &= strut.passes
    outcome.passes = passes


def heaviest_per_structure(outcomes: list[Outcome], configs: dict[str, Config]) -> set[str]:
    """For each structure, the built configuration with the largest mass x depth: the one its FEA runs on."""
    best: dict[tuple[object, ...], tuple[float, str]] = {}
    for o in outcomes:
        if o.status != "built":
            continue
        key = configs[o.name].structure
        score = o.mass_kg * o.depth if o.mass_kg else o.depth * o.parts
        if key not in best or score > best[key][0]:
            best[key] = (score, o.name)
    return {name for _, name in best.values()}


def _write(outcomes: list[Outcome], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "report.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(Outcome)])
        writer.writeheader()
        for o in sorted(outcomes, key=lambda o: o.name):
            writer.writerow(asdict(o))
    rows = []
    for o in sorted(outcomes, key=lambda o: o.name):
        if o.status != "built":
            continue
        image = f'<img src="{html.escape(o.render)}" loading="lazy">' if o.render else ""
        verdict = "" if o.passes is None else ("pass" if o.passes else "BELOW x2")
        rows.append(
            f"<figure><figcaption>{html.escape(o.name)}<br>{o.parts} parts, "
            f"{'clean' if o.clean else 'PROBLEMS'} {verdict}</figcaption>{image}</figure>"
        )
    (output / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Modularack matrix</title>"
        "<style>body{font:14px sans-serif;margin:16px}figure{display:inline-block;width:480px;margin:8px}"
        "img{width:100%}</style>" + "\n".join(rows)
    )


def build_matrix(configs: list[Config], render: bool, fea: bool, jobs: int, output: Path = OUTPUT_DIR) -> list[Outcome]:
    """Build and check every configuration. With `fea`, strength runs on the heaviest of each structure."""
    by_name = {c.name: c for c in configs}
    outcomes: list[Outcome] = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_one, c, render, False, output): c for c in configs}
        for done, future in enumerate(as_completed(futures), 1):
            outcome = future.result()
            outcomes.append(outcome)
            logger.info("[%d/%d] %s: %s %s", done, len(configs), outcome.name, outcome.status, outcome.reason[:160])
    if fea:
        chosen = heaviest_per_structure(outcomes, by_name)
        strength: dict[str, Outcome] = {}
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures2 = {pool.submit(run_one, by_name[n], False, True, output): n for n in sorted(chosen)}
            for done, future in enumerate(as_completed(futures2), 1):
                result = future.result()
                strength[result.name] = result
                logger.info("[fea %d/%d] %s: %s", done, len(chosen), result.name, result.passes)
        for o in outcomes:
            if o.name in strength:
                s = strength[o.name]
                o.mass_kg, o.ear_in_layer, o.ear_interlayer = s.mass_kg, s.ear_in_layer, s.ear_interlayer
                o.wall, o.strut, o.passes = s.wall, s.strut, s.passes
                if s.status == "error":
                    o.status, o.reason = "error", s.reason
    _write(outcomes, output)
    return outcomes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Build and check every chassis configuration.")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--fea", action="store_true")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 4))
    parser.add_argument("--only", action="append", default=[], help="keep configurations whose name has this")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    configs = [c for c in configurations() if all(s in c.name for s in args.only)]
    outcomes = build_matrix(configs, args.render, args.fea, args.jobs, args.output)
    errors = [o for o in outcomes if o.status == "error" or (o.status == "built" and not o.clean)]
    failed = [o for o in outcomes if o.passes is False]
    logger.info(
        "%d configurations: %d built, %d refused, %d errors or unclean, %d below x2",
        len(outcomes),
        sum(o.status == "built" for o in outcomes),
        sum(o.status == "refused" for o in outcomes),
        len(errors),
        len(failed),
    )
    raise SystemExit(1 if errors or failed else 0)


if __name__ == "__main__":
    main()
