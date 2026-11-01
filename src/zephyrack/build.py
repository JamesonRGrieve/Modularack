# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the reference set: one chassis per height, every bay filled, exported and rendered.

Run with `uv run zephyrack-build [output_dir]`. Writes the exploded view as STEP
and PNG, and every printable part as STL.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from build123d import export_step, export_stl

from .chassis import DEFAULT_FLOOR_THICKNESS, RackChassis
from .floor import FORM_FACTORS_BY_SIZE, Floor
from .render import TOP_VIEW, render_png
from .standards import MM_PER_INCH
from .view import ExplodedView

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("build")
PREVIEW_FLOOR_MARGIN = 40.0
"""Floor previews are the board outline plus this much, so the hole pattern fills the frame."""
REFERENCE_WIDTH = 17.75 * MM_PER_INCH
REFERENCE_UNITS_AND_DEPTHS = (
    (1, 36 * MM_PER_INCH),
    (2, 42 * MM_PER_INCH),
    (3, 48 * MM_PER_INCH),
    (4, 50 * MM_PER_INCH),
)


def reference_view() -> ExplodedView:
    view = ExplodedView()
    for units, depth in REFERENCE_UNITS_AND_DEPTHS:
        view.add(RackChassis(depth, REFERENCE_WIDTH, units)).fill_with_drive_bays()
    return view


def build(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    view = reference_view()
    assembly = view.assemble()
    export_step(assembly, output_dir / "reference_view.step")
    render_png(assembly, output_dir / "reference_view.png")
    for form_factor in FORM_FACTORS_BY_SIZE:
        floor = Floor(
            form_factor.width + PREVIEW_FLOOR_MARGIN,
            form_factor.depth + PREVIEW_FLOOR_MARGIN,
            DEFAULT_FLOOR_THICKNESS,
            form_factor,
        )
        render_png(floor.solids()["floor"], output_dir / f"floor_{form_factor.name}_top.png", TOP_VIEW)
    stl_dir = output_dir / "stl"
    stl_dir.mkdir(exist_ok=True)
    for chassis in view.chassis:
        for path, part in chassis.printable_parts().items():
            export_stl(part, stl_dir / f"{path.replace('/', '__')}.stl")
    logger.info("Wrote %s", output_dir)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR)
