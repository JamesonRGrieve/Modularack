# Modularack

A modular rack system you can print on a 250 x 210 mm bed: 1U to 4U chassis for 10 in
(micro) and 19 in (full-size) racks, hot-swap drive bays, motherboard and power supply mounts,
fan grilles, a fully printed rack frame to put them in, and adjustable rails and shelves for
commercial servers in four-post racks. Every part prints without supports, and every connection
between parts comes apart again: a screw you can undo, or for square-hole racks a hook or a
spring catch, and a cover that slides off without tools.

Built in [build123d](https://github.com/gumyr/build123d). Every dimension is a parameter,
and the published standards it builds against live in `src/modularack/standards.py` with
their sources: EIA-310 rack holes, the Intel ATX / microATX / Mini-ITX mounting holes and
I/O aperture, the ATX12V power supply's rear face, the SFF-8301 (3.5 in) and SFF-8201 (2.5 in)
drive dimensions, the SFF-8323 / SFF-8223 drive connector position, and fan screw spacings.

## What you can build

- **Chassis** (`RackChassis`): 10 in or 19 in, 1U to 4U, any depth. The front is a grid of
  12 columns by one row per U, filled with modules:
  - `DriveBay(drive)`: tool-less hot-swap bays for 3.5 in (`DRIVE_3_5`) and 2.5 in drives
    (`DRIVE_2_5` 15 mm, `DRIVE_2_5_9_5MM`, `DRIVE_2_5_7MM`). Each sled is screwed to the
    drive's SFF side holes, slides in grooves and clicks home on a sprung detent. A bay stacks
    as many sleds per row as fit (two 7 mm drives in a 1U row), or `levels=` fixes it. Place
    as many bays as the grid holds, mixed sizes, anywhere: a 19 in 1U takes three 3.5 in bays
    or eight 7 mm 2.5 in drives.
  - `DriveBay(drive, pass_through=SataAdapter(...))`: a printed backplane. A cheap SATA 22-pin
    male-to-female adapter sits behind each sled, where SFF-8323 / SFF-8223 put the drive's connector,
    so a drive connects as it slides home; cables plug into the adapter from behind. Stops on the
    backplane halt the sled at full mate, so the connector never takes the push. No seller publishes
    the adapters' dimensions: `PLACEHOLDER_ADAPTER` is a guess, marked unmeasured, until you
    measure yours.
  - `Vent` and `Blank` faces. Any cells left empty are closed with blanks automatically.
  - Modules can span several rows; each one stands on the floor or the shelf of the module
    below it.
- **Motherboard**: Mini-ITX, microATX, ATX, SSI CEB or SSI EEB on printed standoff bosses at
  the Intel / SSI hole positions (EEB alternates such as F' are added per board with
  `alternate_holes=`), with the rear I/O aperture cut where the spec puts it. The chassis refuses a
  board that doesn't fit, or one that would collide with the front modules.
- **Power supply** (`power_supply=True`): an ATX12V supply of any length up to 220 mm, screwed to the
  rear wall through its four 6-32 holes, around an opening for its fan and inlet. Floor ribs guide
  its body. It lies flat from 3U, or on its side in 4U beside an ATX board; the board moves against the
  far wall to make room. The chassis refuses a supply that would reach the front modules.
- **Fans** (`rear_fans=`, `cover_fans=`): honeycomb grilles with screw holes for 40, 50, 60, 70, 80,
  92, 120, 140 and 200 mm fans, placed clear of seams and every other feature. `standards.FANS` gives
  each screw spacing's source; the 40, 60, 80 and 92 mm spacings are the commonly cited ones, not yet
  confirmed against a maker's drawing. `FanPlate(sizes)` packs
  one or more fans of any mix of sizes onto a separate plate, as long as they fit the bed, for fans
  too big for a panel segment.
- **Tool-less box** (`toolless_box=True`), or just the cover (`toolless_cover=True`). No screws join
  the box's panels, and it all comes apart by hand:
  1. The side walls drop onto the floor, with dovetail tabs on their bottom edges in windows in the
     floor, and slide 12.5 mm back into the grooves, which carry the floor.
  2. The rear wall drops in between them. Tenons locate it in the floor, and a printed spring arm at
     each end snaps a tooth into a side wall, so the rear wall can't lift and the side walls can't slide
     back out.
  3. The cover drops between the walls, with its dovetail tabs in windows at their top edges, and slides
     12.5 mm forward into the grooves. A spring arm at its rear left corner snaps a tooth into the wall.

  With `toolless_modules=True` the front modules become drawers, with the cover on or off:
  - Dovetail tabs on their side plates slide in rails that run back from the floor's front edge (or from
    the front of the shelf below), and a sprung detent clicks into a notch when the module is home.
  - To take a module out, lift the detent arm's front end and pull.
  - Each tab's hold is on the side away from its bed face, so two neighbouring modules' plates, standing
    back to back, share one groove.
  - Shelves thicken to 7 mm to take the rails, and sit on tenons up from their own module's side plates.
  - A short module (a vent or blank) gets short tabs and a detent sized to its arm.

  With `toolless_sleds=True` the drive sleds take no screws:
  - A printed pin on a sprung skin of each rail sits in each of the drive's side holes.
  - Each pin is flat on top, where the drive hangs, and comes to a 45 degree point underneath. Press the
    drive up between the rails from below, and push it up and out to remove it: about 20 N for four pins,
    over twice a 3.5 in drive's weight.

  With one-piece hook or snap corners (`one_piece=True`), nothing joins an ear to its wall and nothing
  needs a tool to rack the chassis: `chassis_19in_2U_drawers` and `chassis_10in_2U_drawers` are fully
  tool-less. In a two-post rack those ears want a brace (see Strength).

  To open, reverse it: press the cover's arm in, slide the cover back and lift; press each rear arm's
  top end in and lift the rear wall; slide the side walls forward and lift. The side walls stand 3 mm in
  from the floor's edges, so the floor keeps a solid lip outboard of each groove. The ears, the panel
  splices and the front modules stay screwed: they go together once.
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
  - `rear_support=(shortest, longest)` (four-post racks): two arms per side, hung on the wall and
    pegged into the rear posts' square holes, locked at any length in the rack-depth range by a
    printed pin through a 1 mm vernier of holes. Both arms must fit the bed, which limits the range
    (about 120 mm for a 470 mm chassis).
  - `web_clamp=PostChannel(...)` (two-post channel racks): a jaw on each side wall grips the post's
    side web, tightened by an M5 thumbscrew into a captive nut. `PostChannel` defaults to a common
    3 in channel of 2.5 mm steel; measure your posts and pass their sizes.
- **Server rails and shelves** (`ServerRails`): for commercial rack servers (a Dell R720 by default,
  `ServerSpec` for others) in four-post square-hole racks such as APC's. A server fills the rack
  opening, so each rail is an L outboard of it: a web between the posts and a ledge under the server's
  edge. Segments butt end to end and are joined by pinned splice plates; a 10/9 mm vernier at the rear
  joint sets any post spacing in the range (690 to 750 mm by default) to the millimetre, and end plates
  peg into every square hole they span. `Sacrifice.UNIT` gives the rails the U below the server and
  keeps its ears on the hole pattern; `Sacrifice.HOLE` raises the server about one square hole instead.
  `shelf=True` hangs cross-beams and deck plates on the ledges.
- **Printed rack** (`PrintedRack`): posts with the EIA-310 hole pattern and captive M6 nuts,
  side panels, base and top. Two-post or four-post. Chassis also fit any bought EIA-310 rack;
  their ear holes are slotted for the variation between brands (10 in racks have no formal
  standard).

`src/modularack/reference.py` has a reference design for every width and height.

## How it's built

**Almost every part is a flat plate printed outer face down**; the drive sleds print in the
orientation they're used in, and square-hole ears and one-piece corners print standing up,
upside down. A printed plate is strong in its own plane (along the layers) and weak across
them, so the structure is arranged so the real loads run along the layers:

| Part | On the bed | Main load | Direction in the print |
|---|---|---|---|
| Floor, cover, shelves | outer face (a tool-less cover: inner face, so its dovetails rise from the bed) | equipment weight, spanning between walls | bending in the plate: along the layers |
| Rear wall in a tool-less box | inner face (its tenons and teeth sit at that face) | the cover's hold-down; latching the side walls | in-plane: along the layers |
| Latch arms (cover, rear wall) | in their plate's plane | bending as the tooth rides the wall (1.2 % strain) | along the layers |
| Server rail segments, splice plates | outer face | the server's weight, bending the rail | along the layers |
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
- *Interrupted dovetail* (the tool-less box): short tabs whose 45 degree flank rises from a 1 mm flat
  on the bed. The floor's grooves undercut at 45 degrees; the walls' grooves for the cover slope their
  lower sides at 45 degrees too, so they still print in a one-piece corner standing upright. Tests sweep
  every panel through its motion: locked it can't lift, slid back it lifts clear, and the latches hold
  only when home.

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
uv run modularack-build build                      # every reference design
uv run modularack-build build chassis_19in_2U      # just one
uv run pytest
```

For each design, `build/<design>/` gets `stl/` (every part already in print orientation),
a STEP assembly, `assembled.png` and `exploded.png` (lit six-view sheets drawn by three.js in headless
Chromium, the newest build in the Playwright cache or `MODULARACK_CHROMIUM`) and `bom.txt` (printed parts plus every
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

`uv run modularack-fea` checks the worst real mounting: a fully loaded chassis hanging from its
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

| Ears | Separate ear | One-piece corner | Corner + brace 1U down | Corner + brace 2U down | Corner + web clamp |
|---|---|---|---|---|---|
| Screw | x3.1 / x2.5 (flat) | x3.6 / x3.9 | x4.7 / x5.3 | | |
| Hook | x1.8 / x1.5 | x2.1 / x1.7 | x2.8 / x2.3 | x6.1 / x5.5 | x7.8 / x5.0 |
| Snap | x1.0 / x0.8 | x1.0 / x0.8 | x1.3 / x1.1 | x4.7 / x3.3 | x7.6 / x4.9 |

So in a two-post rack, hook ears want at least a one-piece corner with a brace one unit down,
and snap ears a brace two units down; screw ears pass on their own. The brace's strut itself
carries at most 341 N (19 in 4U, anchor one unit down): x21 on strength and x7.8 on buckling.
The web clamp holds the chassis up 79 mm behind the ears, so it carries 2.9 times the side's share of
the weight (the ears then hold the front down); its grip (two faces of PLA on painted steel at a
hand-tight 1 kN) holds twice that up to a 19 in 4U chassis. In a four-post rack the rear support
takes the overturning moment off the front ears entirely.

The set-up is cross-checked by five independent codes on the same linear mesh and loads: CalculiX,
scikit-fem, FEniCSx (micromamba env `modularack-fenicsx`), Code_Aster (`simvia/code_aster` container)
and Elmer (`openeuler/elmer` container). All five give the same displacement (19 in 1U ear:
0.1852 mm); the four element-stress codes agree on stress to four figures (18.79 MPa in-layer,
8.206 MPa interlayer shear), and Elmer's nodal-averaged stresses to within 10 %. The design
is judged on CalculiX's second-order (C3D10) solution. `MODULARACK_MICROMAMBA` names the micromamba
binary, and `MODULARACK_PODMAN` the podman command, flags included (for example
`podman --root /var/lib/modularack-containers --runroot /run/modularack-containers` to keep the images
on a local disk).

**Material and layer stiffness.** `--material petg` swaps in Prusament PETG (data sheet v1.1: 47 MPa
printed tensile, 1.5 GPa, 18 MPa interlayer adhesion). The 19 in 1U screw ear goes from x3.1 / x2.4 to
x2.9 / x2.6 (in-layer / across the layers, with interlayer shear and tension combined): slightly weaker
in the layers, stronger across them. `--layer-modulus 0.6` makes the
plastic orthotropic, 60 % as stiff across the layers as along them. That moves load off the interlayer
and raises the same ear's across-layer factor from x2.4 to x2.7, so the isotropic result is the
conservative one.

**Tool-less joints** (`uv run python -m modularack.joint_fea`). Each joint is solved in CalculiX in its
print frame, with stresses peaked over 1 mm^3 rather than the ears' 45 mm^3, since a tab is only about
160 mm^3. The demand is the whole chassis hanging on the floor's tabs, shared evenly; the cover is
pulled straight up with 200 N. Worst factors at x2 over every tool-less box (10 in and 19 in, 1U to 4U):

| Joint | Load path | Capacity per tab | Worst case | Factor |
|---|---|---|---|---|
| Wall tab (on the floor) | the floor hangs on its 45 degree flank | 161-166 N (85 N in an upright one-piece corner) | 19 in 4U, 16.9 N a tab | x20 |
| Floor lip over the tab | bent up, across the floor's layers | 33 N | 19 in 4U, 16.9 N a tab | x3.9 |
| Wall lip over a cover tab | the cover pulled up | 78-82 N | 10 in, 25 N a tab | x6.2 |

Drawer rails (`toolless_modules`), with the heaviest module lifted at 1 g, as if the chassis were turned
over: each rail tab carries 143 N at x2 against about 1.4 N, and the floor's rail lip 50 N (x74 at
worst). The detent arm strains 0.64 % by FEA (0.50 % closed form; the slot's root concentrates it).
A sled's pin arm strains 0.93 % by FEA (1.14 % closed form).

The floor's lip is the weak side, as expected for a lip loaded across its layers. The latch arms bend in
their plate's plane: FEA puts the cover arm at 1.15 % strain (closed form 1.16 %) and the rear arm at
1.13 % (1.22 %), under PLA's 2 %. In a tool-less box the ears are 3 mm longer: the 19 in 1U screw ear goes
from x3.13 / x2.44 to x2.86 / x2.52, and wall bending stays x3.3.

**Server rails.** A Dell R720 (29.5 kg) on a pair of rails at their longest span, half its weight as a
point load at mid-span (worse than its spread weight): bending x30, splice pins x6.0, sag 0.28 mm with
`Sacrifice.UNIT`; bending x16, pins x3.5, sag 0.73 mm with `Sacrifice.HOLE`. A pair of rails carries
88 kg at x2 (51 kg on `HOLE`). The shelf's beams carry 207 kg, so a shelf is limited by its rails' pins
to 88 kg.

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

Print the coupons first: `uv run modularack-build build coupons` writes them to `build/coupons/stl/`. Each
one is cut from a real part in its own print orientation, so it has that part's exact geometry, and each
pair assembles mated:

| Coupon | What to try | Tune |
|---|---|---|
| `floor_dovetail_a/b` | drop the wall's tab into the floor's window, slide it back into the groove: it should slide by hand and not lift | `lid.CLEARANCE` |
| `cover_dovetail_a/b` | drop the cover's tab into the wall's window and slide it forward into the groove | `lid.CLEARANCE` |
| `cover_latch_a/b` | slide the cover strip forward along the wall strip: the arm bends and the tooth snaps in; press the arm to release | `lid.TOOTH`, `lid.LATCH_RELIEF` |
| `rear_latch_a/b` | lower the rear-wall end against the side-wall strip: the tooth clicks in and holds; press the arm's top to release | `toolless.REAR_TOOTH` |
| `rear_tenon_a/b` | the tenon drops into its floor pocket without play | `lid.CLEARANCE` |
| `drawer_rail_a/b` | slide the side-plate strip into the rail from the front: the tabs run freely, the detent clicks into its notch, and lifting the arm's front end releases it | `lid.CLEARANCE`, `toolless.DETENT_DROP` |
| `sled_pin` | press a 3.5 in drive's side hole onto the pin from below: the skin springs aside and the pin snaps in and carries the drive; pushing the drive up frees it | `sled.PIN_CLEARANCE`, `sled.PIN_ENGAGE` |
| `edge_insert_a/b` | press two M3x5.7 inserts into the wall's edge and screw the floor strip on | `fasteners.EDGE_INSERT` |
| `sata_collar` | press the adapter into the collar, male side through the window | `passthrough.SataAdapter` (measure yours first) |

Also print one sled in its bay, and an ear against your rack. The clearances are starting values; record
what fits in the CAD SOP.

**Measuring sheet:** `uv run python -m modularack.calibration` writes A4 and Letter PDFs to
`build/calibration/`.
- Page 1 is a millimetre grid with four oriented corner markers and a corner stop. Print it at 100 %,
  check the grid with calipers, and photograph a part lying on it from straight above. The photo can then
  be corrected for perspective and measured.
- Page 2 records what a photo can't give: caliper readings for the SATA adapter and how each coupon fit.

Measure before printing a backplane: the SATA pass-through adapter's body (width, height, and its
depth with a drive fully mated), its male side's size, and where its receptacle sits on the body, then
pass them as a `SataAdapter`. Measure your channel posts for a web clamp the same way.

Hardware is M3 throughout (countersunk ISO 10642 screws, CNC Kitchen M3x5.7 and M3x3
heat-set inserts, ISO 4032 nuts), M6 nuts in printed rack posts, and the drives' own
6-32 / M3 screws for the sleds.

## Development

The pre-commit hook runs `ruff format --check`, `ruff check`, `mypy --strict`, the tests and
`uv lock --check`. Install it with `uv run pre-commit install`.

## License

AGPL-3.0-or-later. See `LICENSE`.
