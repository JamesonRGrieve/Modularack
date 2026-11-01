# Zephyrack

A modular rack system you can print on a 250 x 210 mm bed: 1U to 4U chassis for 10 in
(micro) and 19 in (full-size) racks, hot-swap drive bays, motherboard mounts, and a fully
printed rack frame to put them in. Every part prints flat, without supports, and every
connection between parts is a screw you can undo.

Built in [build123d](https://github.com/gumyr/build123d). Every dimension is a parameter,
and the published standards it builds against live in `src/zephyrack/standards.py` with
their sources: EIA-310 rack holes, the Intel ATX / microATX / Mini-ITX mounting holes and
I/O aperture, and the SFF-8301 (3.5 in) and SFF-8201 (2.5 in) drive dimensions.

## What you can build

- **Chassis** (`RackChassis`): 10 in or 19 in, 1U to 4U, any depth. The front is a grid of
  12 columns by one row per U, filled with modules:
  - `DriveBay(drive)`: tool-less hot-swap bays for 3.5 in (`DRIVE_3_5`) and 2.5 in drives
    (`DRIVE_2_5` 15 mm, `DRIVE_2_5_9_5MM`, `DRIVE_2_5_7MM`). Each sled is screwed to the
    drive's SFF side holes, slides in grooves and clicks home on a sprung detent. A bay stacks
    as many sleds per row as fit (two 7 mm drives in a 1U row), or `levels=` fixes it. Place
    as many bays as the grid holds, mixed sizes, anywhere: a 19 in 1U takes three 3.5 in bays
    or eight 7 mm 2.5 in drives.
  - `Vent` and `Blank` faces. Any cells left empty are closed with blanks automatically.
  - Modules can span several rows; each one stands on the floor or the shelf of the module
    below it.
- **Motherboard**: Mini-ITX, microATX, ATX, SSI CEB or SSI EEB on printed standoff bosses at
  the Intel / SSI hole positions (EEB alternates such as F' are added per board with
  `alternate_holes=`), with the rear I/O aperture cut where the spec puts it. The chassis refuses a
  board that doesn't fit, or one that would collide with the front modules.
- **Printed rack** (`PrintedRack`): posts with the EIA-310 hole pattern and captive M6 nuts,
  side panels, base and top. Two-post or four-post. Chassis also fit any bought EIA-310 rack;
  their ear holes are slotted for the variation between brands (10 in racks have no formal
  standard).

`src/zephyrack/reference.py` has a reference design for every width and height.

## How it's built

**Every part is a flat plate printed outer face down**, plus the drive sleds, which print
in the orientation they're used in. A flat-printed plate is strong in its own plane (along
the layers) and weak across them, so the structure is arranged so the real loads run in
each plate's plane:

| Part | On the bed | Main load | Direction in the print |
|---|---|---|---|
| Floor, cover, shelves | outer face | equipment weight, spanning between walls | bending in the plate: along the layers |
| Side and rear walls, module sides | outer face | weight carried to the ears; racking | in-plane: along the layers |
| Rack ears, face plates, posts | front face | rack screws bearing on their holes | in-plane bearing: along the layers |
| Splice strips | either face | tension across a panel seam | in-plane tension: along the layers |
| Drive sled | rails standing | drive weight bending the rails; handle pull | rails bend in their own vertical plane; the handle bar bends in the bed plane: both along the layers |

**Joints.** Two kinds, both detachable:

- *Edge joint* (corners): a countersunk M3 screw through plate A into a heat-set insert
  pressed into the edge of plate B. The insert lies in B's plane, so pulling on it shears
  along B's layers; the screw bears on A along A's layers. Walls stand *on* the floor and
  carry the cover, so weight bears in compression rather than hanging on the inserts.
- *Flush splice* (seams in parts bigger than the bed): a strip set into matching rebates
  on the inner faces of both pieces, screwed down into inserts. Both faces stay flush, so
  modules slide over seams and the outside of the chassis stays flat.
- Neighbouring modules are bolted together side by side (screw and captive nut), and the
  outer modules to the chassis walls.

Joint holes on both parts come from one point in the rack frame, so they line up by
construction. A joint whose parts don't meet, or whose screw would hit another feature
(a groove, an aperture, another joint), slides along the edge to a clear spot or fails
the build with a precise error.

**Support-free.** Holes through a plate are vertical in the print. Holes running in a
plate's plane (edge inserts, sled screws) are teardrops with a 45 degree roof. Countersinks
are 90 degree cones, vents in the sled bar are diamonds, and every pocket, groove and rebate
opens on the top face.

## Building

```sh
uv sync
uv run zephyrack-build build                      # every reference design
uv run zephyrack-build build chassis_19in_2U      # just one
uv run pytest
```

For each design, `build/<design>/` gets `stl/` (every part already in print orientation),
a STEP assembly, `assembled.png`, `exploded.png` and `bom.txt` (printed parts plus every
screw, insert and nut). `build/report.txt` summarises the checks.

## What the checks prove

For every reference design, the test suite and the build report check that:

- every part fits the bed (MK3S / MK3S+ 250 x 210 x 210 mm less a 5 mm margin);
- every part is one valid solid;
- no surface of any part faces down more steeply than 45 degrees off the bed, sampled
  across every face (so teardrops and countersinks are checked over their whole extent);
- no two parts of the assembled design overlap.

Representative parts (a wall segment, a sled, an ear, a rack post, a splice strip) slice
cleanly in PrusaSlicer 2.9 with supports off.

## Strength

`uv run zephyrack-fea` checks the worst real mounting: a fully loaded chassis hanging from its
two front ears in a two-post rack. Each ear is meshed with gmsh and solved in CalculiX, with
stresses read in the ear's print frame, so tension and shear *across* the layers are reported
separately from in-layer stress. The side walls, which carry the same moment in their own
plane, are checked in closed form.

The load is the printed parts as solid PLA, plus 750 g per 3.5 in drive, 150 g per 2.5 in
drive, 2 kg of board and 2.5 kg of power supply. Material data is the Prusament PLA data sheet
(v1.1, 2022): 51 MPa printed tensile strength, 17 MPa interlayer adhesion. Every reference
chassis holds at least twice that load:

| Chassis | Mass | Ear, in-layer | Ear, across layers | Ear deflection | Wall bending |
|---|---|---|---|---|---|
| 10 in 1U | 7.1 kg | 11.3 MPa (x4.5) | 4.2 MPa shear (x4.0) | 0.09 mm | x10 |
| 19 in 1U | 11.2 kg | 21.5 MPa (x2.4) | 8.1 MPa shear (x2.1) | 0.18 mm | x5.2 |
| 19 in 2U | 13.4 kg | 7.5 MPa (x6.8) | 3.1 MPa shear (x5.4) | 0.11 mm | x27 |
| 19 in 4U | 19.3 kg | 3.9 MPa (x13) | 1.6 MPa shear (x11) | 0.07 mm | x91 |

The set-up is cross-checked by a second, independent solver: scikit-fem and CalculiX, given the
same linear mesh and loads, agree to four significant figures (19 in 1U ear: 0.185 mm, 18.8 MPa
in-layer, 8.21 MPa interlayer shear), so the mesh import, supports and loads are right. The design
is judged on CalculiX's second-order (C3D10) solution.

The analysis drove two design changes: the ears are 9 mm thick (at 6 mm the 19 in 1U ear
reached 14.7 MPa interlayer shear around its top screw, x1.2), and wall seams are staggered
against floor and cover seams so no seam cuts the whole box. FEA assumes solid, isotropic
material; infill, perimeters and print quality move the real numbers, which the coupon prints
below are for.

## Before you print a full set

Print coupons first: a short wall segment with two edge inserts, a splice strip and its two
mating corners, one sled in its bay, and an ear against your rack. The clearances (sled
groove, detent, insert bores, drive-screw recesses) are starting values; tune them in
`cassette.py`, `sled.py` and `fasteners.py`.

Hardware is M3 throughout (countersunk ISO 10642 screws, CNC Kitchen M3x5.7 and M3x3
heat-set inserts, ISO 4032 nuts), M6 nuts in printed rack posts, and the drives' own
6-32 / M3 screws for the sleds.

## Development

The pre-commit hook runs `ruff format --check`, `ruff check`, `mypy --strict`, the tests and
`uv lock --check`. Install it with `uv run pre-commit install`.

## License

AGPL-3.0-or-later. See `LICENSE`.
