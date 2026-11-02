# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lit inspection renders from six angles, drawn by three.js in headless Chromium.

`render_views` exports the shape as GLB and hands it to `render/render.mjs`, which draws front-left
and rear-right isometrics, front, rear, top and side views with a real depth buffer, key/fill/rim
lighting and feature edges only (creases over 25 degrees, never tessellation seams).

Needs Node and the render/ package installed (`pnpm install` in render/), and a Chromium build:
the newest in the Playwright cache, or ZEPHYRACK_CHROMIUM.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from build123d import Compound, Part, export_gltf

RENDER_DIR = Path(__file__).resolve().parents[2] / "render"
NODE = os.environ.get("ZEPHYRACK_NODE", "node")
RENDER_TIMEOUT = 600
GLTF_LINEAR_DEFLECTION = 0.05
GLTF_ANGULAR_DEFLECTION = 0.2


def render_views(shape: Compound | Part, path: Path, title: str = "") -> None:
    """A lit six-view contact sheet of `shape`, written to `path` as PNG."""
    with tempfile.TemporaryDirectory() as directory:
        model = Path(directory) / "model.glb"
        export_gltf(
            # Wrapped, because the exporter drops a top-level shape's own location (a part moved
            # into its print orientation would render unmoved); children keep theirs.
            Compound(children=[shape]),
            model,
            binary=True,
            linear_deflection=GLTF_LINEAR_DEFLECTION,
            angular_deflection=GLTF_ANGULAR_DEFLECTION,
        )
        result = subprocess.run(
            [NODE, str(RENDER_DIR / "render.mjs"), str(model), str(path.resolve()), title],
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Render failed: {result.stderr[-2000:]}")
