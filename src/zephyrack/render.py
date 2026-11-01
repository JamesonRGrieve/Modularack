# SPDX-License-Identifier: AGPL-3.0-or-later
"""Headless shaded previews, so a model can be checked by eye without a CAD viewer."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from build123d import Compound, Part
from matplotlib.colors import to_rgb
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

TESSELLATION_TOLERANCE = 0.2
FIGURE_SIZE_INCHES = (12.0, 9.0)
DPI = 120
ISOMETRIC_VIEW = (25.0, -135.0)
"""(elevation, azimuth) in degrees: looking at the front-left corner from above."""
TOP_VIEW = (90.0, -90.0)
FACE_COLOUR = "#9db4c0"
LIGHT_DIRECTION = np.array([-0.5, -0.4, 0.77]) / np.linalg.norm([-0.5, -0.4, 0.77])
"""Unit vector toward the light: above, in front and to the right of the default view."""
AMBIENT = 0.35


def render_png(shape: Compound | Part, path: Path, view: tuple[float, float] = ISOMETRIC_VIEW) -> None:
    vertices, triangles = shape.tessellate(TESSELLATION_TOLERANCE)
    points = np.array([(v.X, v.Y, v.Z) for v in vertices])
    faces = points[np.array(triangles)]
    normals = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), np.finfo(float).eps)
    brightness = AMBIENT + (1 - AMBIENT) * np.abs(normals @ LIGHT_DIRECTION)
    colours = np.clip(np.outer(brightness, to_rgb(FACE_COLOUR)), 0, 1)
    figure = plt.figure(figsize=FIGURE_SIZE_INCHES)
    axes = figure.add_subplot(projection="3d")
    axes.add_collection3d(Poly3DCollection(faces, facecolors=colours, edgecolors=colours, linewidths=0.1))
    box = shape.bounding_box()
    axes.set_xlim(box.min.X, box.max.X)
    axes.set_ylim(box.min.Y, box.max.Y)
    axes.set_zlim(box.min.Z, box.max.Z)
    axes.set_box_aspect((box.size.X, box.size.Y, max(box.size.Z, 1.0)))
    axes.view_init(elev=view[0], azim=view[1])
    axes.set_axis_off()
    figure.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(figure)
