# SPDX-License-Identifier: AGPL-3.0-or-later
"""SATA pass-through boards behind the hot-swap sleds: a printed backplane for cheap adapters.

A SATA 22-pin (7+15) male-to-female adapter sits behind each sled. Its female side faces the drive and
takes the drive's connector as the sled slides home; a SATA data cable and power lead plug into its male
side from behind. The bay's rear stop moves back by the adapter's depth and becomes the backplane:

- a collar on its front face around each adapter's body locates the adapter across and up and down;
- a window lets the adapter's male side reach back through for the cables;
- stop blocks in front of the sled's rails stop the sled where the connectors are fully mated, so the
  adapter never takes the sled's push (SFF-8223 warns against loading a drive's connector).

Where the connector sits on a drive is sourced, from SFF-8223 Rev 2.7 (2.5 in) and SFF-8323 Rev 1.6
(3.5 in), Table 3-1 and Figure 3-1: both put the connector's datum B (its contact blade) A13 + A3 / 2 =
30.125 mm from the drive's datum-Y side (its left, seen from the connector end with the cover up) and
A7 = 3.50 mm above its base, flush with the drive's connector end.

The adapter's own dimensions are not published by any seller (STC-BB016 and microSATAcables
SATA-22P-1232 were checked). `PLACEHOLDER_ADAPTER` holds guesses and is marked unmeasured: measure the
adapter you buy and pass a `SataAdapter` built from your numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

CONNECTOR_FROM_Y_SIDE = 13.43 + 33.39 / 2
"""SFF-8223 / SFF-8323 A13 + A3 / 2: datum B's centre from the drive's datum-Y side."""
CONNECTOR_HEIGHT = 3.50
"""SFF-8223 / SFF-8323 A7: datum B above the drive's base."""
CONNECTOR_WIDTH = 42.73
"""A2: the drive connector's overall width."""
COLLAR_WALL = 1.6
COLLAR_CLEARANCE = 0.2
COLLAR_SHORT = 1.0
"""The collar stops this far short of the adapter's front face, clear of the drive."""


@dataclass(frozen=True)
class SataAdapter:
    """A pass-through adapter, seen from the drive with the drive's cover up. Lengths in mm."""

    name: str
    body_width: float
    body_height: float
    body_depth: float
    """With a drive fully mated: from the drive's connector end back to the face the adapter rests on
    (its male side's shoulder). Measure it with a drive plugged in."""
    plug_width: float
    plug_height: float
    """The male side that reaches back through the plate's window."""
    receptacle_offset: tuple[float, float]
    """The female receptacle's datum-B centre from the body's centre: across (toward the drive's datum-Y
    side positive) and up."""
    measured: bool


PLACEHOLDER_ADAPTER = SataAdapter(
    "SATA 22-pin male-to-female pass-through (PLACEHOLDER: measure yours)",
    body_width=52.0,
    body_height=8.0,
    body_depth=12.0,
    plug_width=46.0,
    plug_height=6.0,
    receptacle_offset=(0.0, 0.0),
    measured=False,
)
"""Unmeasured guesses: a 22-pin housing is about 43 mm wide (A2), so a board and shroud a little wider."""
