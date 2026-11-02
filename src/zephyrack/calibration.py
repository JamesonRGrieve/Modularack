# SPDX-License-Identifier: AGPL-3.0-or-later
"""A printable measuring sheet: photograph a part on it, and the photo can be measured.

Page 1 is a millimetre grid with four corner markers at known positions. A photo of a part lying on the
grid can be corrected for perspective (the markers' centres give the homography) and scaled (the grid),
the way the CAD SOP's scan-to-CAD section measures flat parts. Each marker holds one to four dots, so the
sheet's orientation reads from any photo. A printed corner stop gives the part a square datum, and
the grid's own outer lines check the printer printed at 100 %: measure them with calipers in each axis
and write the result in.

Page 2 is for numbers a photo can't give: caliper readings for a SATA pass-through adapter (see
`passthrough.SataAdapter`) and the fit of each coupon (see `coupons`). Photograph it filled in.

`uv run python -m zephyrack.calibration` writes A4 and US Letter PDFs to build/calibration/.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .coupons import COUPON_NOTES

MM = 72 / 25.4
"""PDF points per millimetre."""
MARGIN = 12.0
GRID_WIDTH = 160.0
GRID_HEIGHT = 150.0
MARKER = 12.0
"""Corner marker side."""
MARKER_GAP = 3.0
"""Between a marker and the grid."""
STOP = 40.0
"""Length of each arm of the corner stop."""


@dataclass(frozen=True)
class PageSize:
    name: str
    width: float
    height: float


A4 = PageSize("a4", 210.0, 297.0)
LETTER = PageSize("letter", 215.9, 279.4)


def grid_origin(page: PageSize) -> tuple[float, float]:
    """The grid's bottom-left corner on the page (mm from the page's bottom-left)."""
    x = (page.width - GRID_WIDTH) / 2
    y = page.height - MARGIN - 22.0 - MARKER - MARKER_GAP - GRID_HEIGHT
    return x, y


def marker_centres(page: PageSize) -> dict[int, tuple[float, float]]:
    """Each marker's centre in grid millimetres (origin at the grid's bottom-left), by its dot count:
    1 top-left, 2 top-right, 3 bottom-right, 4 bottom-left."""
    out = MARKER_GAP + MARKER / 2
    return {
        1: (-out, GRID_HEIGHT + out),
        2: (GRID_WIDTH + out, GRID_HEIGHT + out),
        3: (GRID_WIDTH + out, -out),
        4: (-out, -out),
    }


class _Canvas:
    """Just enough PDF drawing: lines, filled rectangles and Helvetica text, in millimetres."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def gray(self, level: float, stroke: bool = True) -> None:
        self.ops.append(f"{level:.3f} {'G' if stroke else 'g'}")

    def width(self, mm: float) -> None:
        self.ops.append(f"{mm * MM:.3f} w")

    def line(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.ops.append(f"{x0 * MM:.3f} {y0 * MM:.3f} m {x1 * MM:.3f} {y1 * MM:.3f} l S")

    def rect(self, x: float, y: float, w: float, h: float, fill: bool) -> None:
        self.ops.append(f"{x * MM:.3f} {y * MM:.3f} {w * MM:.3f} {h * MM:.3f} re {'f' if fill else 'S'}")

    def text(self, x: float, y: float, size: float, value: str, bold: bool = False) -> None:
        safe = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        font = "F2" if bold else "F1"
        self.ops.append(f"BT /{font} {size:.2f} Tf {x * MM:.3f} {y * MM:.3f} Td ({safe}) Tj ET")

    def stream(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def _marker(c: _Canvas, cx: float, cy: float, dots: int) -> None:
    half = MARKER / 2
    c.gray(0.0, stroke=False)
    c.rect(cx - half, cy - half, MARKER, MARKER, fill=True)
    inner = MARKER * 0.6
    c.gray(1.0, stroke=False)
    c.rect(cx - inner / 2, cy - inner / 2, inner, inner, fill=True)
    c.gray(0.0, stroke=False)
    # Dots on a 2 x 2 lattice, filled in reading order, so the count and its layout give the orientation.
    spots = [(-1, 1), (1, 1), (1, -1), (-1, -1)][:dots]
    d = inner / 4
    for sx, sy in spots:
        c.rect(cx + sx * d - 0.9, cy + sy * d - 0.9, 1.8, 1.8, fill=True)


def _grid_page(page: PageSize) -> bytes:
    c = _Canvas()
    gx, gy = grid_origin(page)
    top = page.height - MARGIN
    c.gray(0.0, stroke=False)
    c.text(MARGIN, top - 6, 14, "Zephyrack measuring sheet", bold=True)
    c.text(
        MARGIN, top - 12, 8, "Print at 100 % (Actual size, no scaling). Check the grid's size with calipers before use."
    )
    c.text(
        MARGIN,
        top - 16.5,
        8,
        "Lay the part flat against the corner stop, square to the grid. Photograph from straight above,",
    )
    c.text(
        MARGIN, top - 21, 8, "the whole grid and all four markers in frame, in even light. Turn the part for each face."
    )
    # Grid: 1 mm, 5 mm, 10 mm lines.
    for i in range(int(GRID_WIDTH) + 1):
        weight, level = (0.3, 0.0) if i % 10 == 0 else (0.18, 0.45) if i % 5 == 0 else (0.08, 0.7)
        c.width(weight)
        c.gray(level)
        c.line(gx + i, gy, gx + i, gy + GRID_HEIGHT)
    for j in range(int(GRID_HEIGHT) + 1):
        weight, level = (0.3, 0.0) if j % 10 == 0 else (0.18, 0.45) if j % 5 == 0 else (0.08, 0.7)
        c.width(weight)
        c.gray(level)
        c.line(gx, gy + j, gx + GRID_WIDTH, gy + j)
    c.gray(0.0, stroke=False)
    for i in range(0, int(GRID_WIDTH) + 1, 10):
        c.text(gx + i - 1.5, gy - 3.2, 5, str(i))
    for j in range(10, int(GRID_HEIGHT) + 1, 10):
        c.text(gx - 6.5, gy + j - 0.8, 5, str(j))
    # Corner stop: a heavy L at the grid's origin to butt the part against.
    c.width(0.8)
    c.gray(0.0)
    c.line(gx, gy, gx + STOP, gy)
    c.line(gx, gy, gx, gy + STOP)
    c.text(gx + 2, gy + STOP + 1.5, 6, "corner stop")
    for dots, (mx, my) in marker_centres(page).items():
        _marker(c, gx + mx, gy + my, dots)
    # The scale check: the grid's own outer lines, measured centre to centre in each axis (a printer can
    # scale the two axes differently).
    by = gy - MARKER - MARKER_GAP - 12
    c.text(gx, by, 7, f"Scale check, grid's outer lines centre to centre:  X (0 to {GRID_WIDTH:.0f}) = __________ mm")
    c.text(gx + 69, by - 5, 7, f"Y (0 to {GRID_HEIGHT:.0f}) = __________ mm")
    legend = ", ".join(f"{d} ({x:.0f}, {y:.0f})" for d, (x, y) in marker_centres(page).items())
    c.text(gx, by - 12, 6, f"Marker centres by dot count, mm from the grid's 0,0: {legend}")
    c.text(gx, by - 19, 7, "Part: ______________________   Face shown: ______________   Date: __________")
    return c.stream()


def _table(c: _Canvas, x: float, y: float, widths: list[float], rows: list[list[str]], height: float = 7.0) -> float:
    """A ruled table; returns the y below it."""
    c.width(0.2)
    c.gray(0.0)
    total = sum(widths)
    for r, row in enumerate(rows):
        top = y - r * height
        c.line(x, top, x + total, top)
        cx = x
        for w, cell in zip(widths, row, strict=True):
            c.text(cx + 1.2, top - height + 2.2, 6.5, cell, bold=r == 0)
            cx += w
    bottom = y - len(rows) * height
    c.line(x, bottom, x + total, bottom)
    cx = x
    for w in [0.0, *widths]:
        cx += w
        c.line(cx, y, cx, bottom)
    return bottom


ADAPTER_ROWS = [
    ["Measurement (calipers)", "Field in SataAdapter", "Adapter 1", "Adapter 2"],
    ["Body width, across the connectors", "body_width", "", ""],
    ["Body height", "body_height", "", ""],
    ["Depth with a drive plugged in: drive's end to the", "body_depth", "", ""],
    ["  face the adapter rests on (its male side's shoulder)", "", "", ""],
    ["Male side width (reaches back through the plate)", "plug_width", "", ""],
    ["Male side height", "plug_height", "", ""],
    ["Female socket's centre, across from body centre", "receptacle_offset[0]", "", ""],
    ["  (toward the drive's left seen from its connector end, +)", "", "", ""],
    ["Female socket's centre, up from body centre", "receptacle_offset[1]", "", ""],
    ["Screw holes? count, diameter, spacing", "(notes)", "", ""],
]


def _record_page(page: PageSize) -> bytes:
    c = _Canvas()
    top = page.height - MARGIN
    c.gray(0.0, stroke=False)
    c.text(MARGIN, top - 6, 14, "Zephyrack measurement record", bold=True)
    c.text(
        MARGIN,
        top - 12,
        8,
        "Fill in, then photograph this page. Millimetres. Photograph each adapter face on page 1 too.",
    )
    c.text(MARGIN, top - 20, 9, "SATA pass-through adapter", bold=True)
    width = page.width - 2 * MARGIN
    y = _table(c, MARGIN, top - 23, [width * 0.46, width * 0.22, width * 0.16, width * 0.16], ADAPTER_ROWS)
    c.text(MARGIN, y - 8, 9, "Coupons (build/coupons/stl)", bold=True)
    rows = [["Coupon", "Too tight", "Good", "Too loose", "Notes"]]
    rows += [[name, "", "", "", ""] for name in COUPON_NOTES]
    y = _table(c, MARGIN, y - 11, [width * 0.28, width * 0.12, width * 0.12, width * 0.12, width * 0.36], rows)
    c.text(MARGIN, y - 6, 6.5, "Printer: __________   Filament: __________   Profile: __________   Nozzle: ______")
    return c.stream()


def pdf(page: PageSize) -> bytes:
    """A two-page PDF of the sheet at the page's exact size."""
    pages = [_grid_page(page), _record_page(page)]
    w, h = page.width * MM, page.height * MM
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # pages, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    kids = []
    for content in pages:
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        stream_id = len(objects)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.3f} {h:.3f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>"
            ).encode()
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the measuring sheet PDFs")
    parser.add_argument("--out", type=Path, default=Path("build/calibration"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for page in (A4, LETTER):
        path = args.out / f"measuring_sheet_{page.name}.pdf"
        path.write_bytes(pdf(page))
        print(path)


if __name__ == "__main__":
    main()
