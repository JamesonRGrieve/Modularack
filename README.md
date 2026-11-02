# Zephyrack

A modular rack system you can print on a 250 x 210 mm bed: 1U to 4U chassis for 10 in
(micro) and 19 in (full-size) racks, hot-swap drive bays, motherboard mounts, and a fully
printed rack frame to put them in. Every part prints without supports, and every connection
between parts comes apart again: a screw you can undo, or for square-hole racks a hook or a
spring catch.

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
- **Mounting** (`ear_style=`, `one_piece=`, `knee_brace_units=`), for the worst case of a chassis
  hung from two front posts:
  - `EarStyle.SCREW`: slotted ears for M6 rack screws, in round, threaded or cage-nut holes.
  - `EarStyle.HOOK` (square holes, no tools): a rigid hook in every hole. Push in, drop 2.3 mm
    and the hooks seat behind the post's flange; taking the chassis out needs that much room above it.
  - `EarStyle.SNAP` (square holes, push straight in): pegs carry the weight and a spring hook in
    the top hole snaps sideways behind the flange; push it inboard to release. Works in a full rack.
  - `one_piece=True`: each ear and the front of its side wall print as one upright part, with no
    joint between them.
  - `knee_brace_units=1` or `2`: a strut fitted from the side (open-frame racks, or with a side
    panel off) props each side wall from a square hole one or two units below the chassis. Those
    units' hole columns must be free.
- **Printed rack** (`PrintedRack`): posts with the EIA-310 hole pattern and captive M6 nuts,
  side panels, base and top. Two-post or four-post. Chassis also fit any bought EIA-310 rack;
  their ear holes are slotted for the variation between brands (10 in racks have no formal
  standard).

`src/zephyrack/reference.py` has a reference design for every width and height.

## How it's built

**Almost every part is a flat plate printed outer face down**; the drive sleds print in the
orientation they're used in, and square-hole ears and one-piece corners print standing up,
upside down. A printed plate is strong in its own plane (along the layers) and weak across
them, so the structure is arranged so the real loads run along the layers:

| Part | On the bed | Main load | Direction in the print |
|---|---|---|---|
| Floor, cover, shelves | outer face | equipment weight, spanning between walls | bending in the plate: along the layers |
| Side and rear walls, module sides | outer face | weight carried to the ears; racking | in-plane: along the layers |
| Screw ears, face plates, posts | front face | rack screws bearing on their holes | in-plane bearing: along the layers |
| Square-hole ears, one-piece corners | the chassis's top edge (upright) | hooks and pegs pulling on and bearing in the post's holes | the post's face cuts across the layers: each hook's pull reaches the wall inside its own layer |
| Knee brace strut | its outer side | compression from the post to the wall | along the layers |
| Splice strips | either face | tension across a panel seam | in-plane tension: along the layers |
| Drive sled | rails standing | drive weight bending the rails; handle pull | rails bend in their own vertical plane; the handle bar bends in the bed plane: both along the layers |

**Joints.** Two kinds, both detachable:

- *Edge joint* (corners): a countersunk M3 screw through plate A into a heat-set insert
  pressed into the edge of plate B. The insert lies in B's plane, so pulling on it shears
  along B's layers; the screw bears on A along A's layers. Walls stand *on* the floor, so
  weight bears in compression rather than hanging on the inserts. The side walls run the
  chassis's full height (so a corner can print upright in one piece); the 7 mm cover sits
  between them, 1 mm below their top, held by screws into captive nuts in T-slots in its edges.
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
opens on the top face. In a part printed standing up, every hole, pocket, rebate and slot is
roofed toward the print's top instead, and anything standing out (a hook, a peg) has a 45
degree top above a flat bearing face.

## Building

```sh
uv sync
pnpm --dir render install                         # three.js renderer (headless Chromium)
uv run zephyrack-build build                      # every reference design
uv run zephyrack-build build chassis_19in_2U      # just one
uv run pytest
```

For each design, `build/<design>/` gets `stl/` (every part already in print orientation),
a STEP assembly, `assembled.png` and `exploded.png` (lit six-view sheets drawn by three.js in headless
Chromium, the newest build in the Playwright cache or `ZEPHYRACK_CHROMIUM`) and `bom.txt` (printed parts plus every
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
separately from in-layer stress. Peaks are the stress exceeded over the most-stressed 45 mm^3
of plastic, which ignores single-node spikes at loads and supports without flattering a big
model. The side walls, which carry the same moment in their own plane, are checked in closed form.

The load is the printed parts as solid PLA, plus 750 g per 3.5 in drive, 150 g per 2.5 in
drive, 2 kg of board and 2.5 kg of power supply. Material data is the Prusament PLA data sheet
(v1.1, 2022): 51 MPa printed tensile strength, 17 MPa interlayer adhesion. Every reference
chassis holds at least twice that load:

| Chassis (screw ears) | Mass | Ear, in-layer | Ear, across layers | Ear deflection | Wall bending (as printed) |
|---|---|---|---|---|---|
| 10 in 1U | 7.1 kg | 8.2 MPa (x6.2) | 3.5 MPa shear (x4.8) | 0.08 mm | x6.4 |
| 19 in 1U | 11.2 kg | 16.3 MPa (x3.1) | 6.8 MPa shear (x2.5) | 0.16 mm | x3.3 |
| 19 in 2U | 13.3 kg | 8.0 MPa (x6.4) | 3.4 MPa shear (x5.1) | 0.10 mm | x9.9 |
| 19 in 4U | 20.7 kg | 5.5 MPa (x9.2) | 2.4 MPa shear (x7.0) | 0.07 mm | x23 |

**Mounting options, 19 in 1U (the worst case), two posts.** A one-piece corner is solved with
the rest of the chassis as the shear and bending moment at its splice to the next wall
segment; a knee brace is its strut's own stiffness as springs from the anchor hole.
In-layer / across-layer factors:

| Ears | Separate ear | One-piece corner | Corner + brace 1U down | Corner + brace 2U down |
|---|---|---|---|---|
| Screw | x3.1 / x2.5 (flat) | x3.6 / x3.9 | x4.7 / x5.3 | |
| Hook | x1.8 / x1.5 | x2.1 / x1.7 | x2.8 / x2.3 | x6.1 / x5.5 |
| Snap | x1.0 / x0.8 | x1.0 / x0.8 | x1.3 / x1.1 | x4.7 / x3.3 |

So in a two-post rack, hook ears want at least a one-piece corner with a brace one unit down,
and snap ears a brace two units down; screw ears pass on their own. The brace's strut itself
carries at most 341 N (19 in 4U, anchor one unit down): x21 on strength and x7.8 on buckling.
In a four-post rack a support to the rear posts takes the overturning moment off the front ears
entirely (rear supports are not built yet).

The set-up is cross-checked by five independent codes on the same linear mesh and loads: CalculiX,
scikit-fem, FEniCSx (micromamba env `zephyrack-fenicsx`), Code_Aster (`simvia/code_aster` container)
and Elmer (`openeuler/elmer` container). All five give the same displacement (19 in 1U ear:
0.1852 mm); the four element-stress codes agree on stress to four figures (18.79 MPa in-layer,
8.206 MPa interlayer shear), and Elmer's nodal-averaged stresses to within 10 %. The design
is judged on CalculiX's second-order (C3D10) solution.

The analysis drove two design changes: the ears are 9 mm thick (at 6 mm the 19 in 1U ear
reached 14.7 MPa interlayer shear around its top screw, x1.2), and wall seams are staggered
against floor and cover seams so no seam cuts the whole box.

### As printed

A sliced part isn't solid: PrusaSlicer's stock MK3 profile (0.20mm QUALITY) lays 2 perimeters
(0.9 mm), 4 bottom and 5 top layers and fills the rest with 15 % gyroid. `infill.py` splits a
plate into that solid shell and its sparse core and meshes both together, so the FEA can check
a part at the settings it is really printed with. Published infill tests disagree on how stiff
each pattern is, so the core is bracketed rather than guessed: once carrying nothing (the floor
for any pattern) and once at its full material fraction (the ceiling).

On the stock profile the 19 in 1U ear falls to x0.39 in-layer and x0.28 across the layers with
the core ignored, and x1.45 / x0.95 even at the ceiling. No sparse setting tried (up to 4
perimeters, 8 + 8 skin layers, 40 % infill) reaches x2, so **ears print at 100 % infill**,
which is the solid case in the table above. Side walls with the infill ignored:

| Chassis | Stock (2 perimeters) | Structural (4 perimeters) |
|---|---|---|
| 10 in 1U | x4.8 | x6.4 |
| 19 in 1U | x2.5 | x3.3 |
| 19 in 2U | x8.3 | x9.9 |
| 19 in 4U | x21 | x23 |

So every part carries the print settings it is verified at (`print_settings.py`), and `bom.txt`
lists them: **ears and one-piece corners solid; everything else the stock profile with 4 perimeters**. Only the ears
and side walls are checked as printed so far; the joints (insert pull-out, nut laps, splices)
and the printed rack posts are not, and nor is print quality, which the coupon prints below are
for.

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
