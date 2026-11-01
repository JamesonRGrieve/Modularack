# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the reference set.

`uv run zephyrack-build [output_dir] [name ...]` writes, for each reference design:

- `stl/<part>.stl`: every printable part, already in its print orientation;
- `<design>.step`: the assembly;
- `assembled.png` and `exploded.png`: previews to check by eye;
- `bom.txt`: printed parts plus every screw, insert and nut;
- a line in `report.txt`: bed fit, validity, support-free and interference results.
"""

from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

from build123d import export_step, export_stl

from .checks import check
from .component import Component
from .reference import reference_builders
from .render import render_png

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("build")
EXPLODE_DISTANCE = 60.0


def bill_of_materials(design: Component, hardware: list[str]) -> str:
    lines = [f"# {design.name}", "", "## Printed parts", ""]
    lines += [f"- {name}" for name in design.printable_parts()]
    lines += ["", "## Hardware", ""]
    lines += [f"- {count} x {item}" for item, count in sorted(Counter(hardware).items())]
    return "\n".join(lines) + "\n"


def build_design(name: str, design: Component, output_dir: Path) -> str:
    target = output_dir / name
    stl_dir = target / "stl"
    stl_dir.mkdir(parents=True, exist_ok=True)
    for part_name, part in design.printable_parts().items():
        export_stl(part, stl_dir / f"{part_name}.stl")
    assembly = design.assemble()
    export_step(assembly, target / f"{name}.step")
    render_png(assembly, target / "assembled.png")
    render_png(design.assemble(EXPLODE_DISTANCE), target / "exploded.png")
    (target / "bom.txt").write_text(bill_of_materials(design, design.hardware))
    report = check(design)
    status = "clean" if report.clean else f"PROBLEMS {report}"
    return f"{name}: {report.parts} parts, {status}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    builders = reference_builders()
    names = sys.argv[2:] or list(builders)
    unknown = [n for n in names if n not in builders]
    if unknown:
        raise SystemExit(f"Unknown design(s): {', '.join(unknown)}. Known: {', '.join(builders)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in names:
        line = build_design(name, builders[name](), output_dir)
        logger.info("%s", line)
        lines.append(line)
    (output_dir / "report.txt").write_text("\n".join(lines) + "\n")
