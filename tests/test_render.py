# SPDX-License-Identifier: AGPL-3.0-or-later
"""The renderer draws small parts too (needs Node and Playwright's Chromium, like the build)."""

from pathlib import Path

import numpy as np
from build123d import Box
from matplotlib.image import imread

from modularack.render import render_views

MODEL_PIXELS = 2000
"""Shaded pixels a six-view sheet of a cube shows at least; a blank sheet (white, black labels) has none."""


def model_pixels(image: np.ndarray) -> int:
    """The model's blue-grey shading: neither paper white nor label black, and bluer than it is red."""
    rgb = image[..., :3]
    shaded = (rgb.max(axis=-1) < 0.9) & (rgb.min(axis=-1) > 0.15) & (rgb[..., 2] > rgb[..., 0] + 0.03)
    return int(np.count_nonzero(shaded))


def test_a_blank_sheet_scores_no_model_pixels() -> None:
    blank = np.ones((600, 900, 3))
    blank[20:40, 100:400] = 0.0  # a black title
    assert model_pixels(blank) == 0


def test_a_20_mm_part_is_not_clipped_by_the_near_plane(tmp_path: Path) -> None:
    # gltf is in metres and the camera stands 4 radii off: a fixed 0.1 m near plane put any part under
    # about 50 mm wholly in front of it, and the sheet came out blank.
    png = tmp_path / "cube.png"
    render_views(Box(20, 20, 20), png, "20 mm cube")
    assert model_pixels(imread(png)) > MODEL_PIXELS
