# Zephyrack

A modular, 3D-printable rack system for 10 in (micro) and 19 in (full) racks, built in
[build123d](https://github.com/gumyr/build123d). Every dimension is a parameter, and the
published standards it builds against (EIA-310 rack holes, ATX-family motherboard holes)
live in one module, `src/zephyrack/standards.py`, each with its source.

## What's here

- **`RackChassis`**: an nU box. Its walls are stacked from 1U and 2U segments; its floor is
  drilled for the largest motherboard it supports and every smaller one (Mini-ITX, microATX,
  ATX), at the hole positions in the Intel specs.
- **Front-panel grid**: 12 cells wide and 2 per U. Modules such as `Bay35` (a 3.5 in drive
  bay face) take a block of cells, and overlapping or off-grid placement raises an error.
- **`ExplodedView`**: several chassis side by side, exploded, for review.

Units are millimetres. +X runs from the front of the rack to the back, +Y to the left
when facing +X, and +Z up.

## Building

```sh
uv sync
uv run zephyrack-build build   # STEP + PNG previews + one STL per printable part
uv run pytest
```

`build/reference_view.png` is the exploded reference set. `build/floor_*_top.png` shows
each floor's standoff pattern from above.

## Development

The pre-commit hook runs `ruff format --check`, `ruff check`, `mypy --strict`, the tests and
`uv lock --check`. Install it with `uv run pre-commit install`.

## License

AGPL-3.0-or-later. See `LICENSE`.
