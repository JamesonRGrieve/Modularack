# SPDX-License-Identifier: AGPL-3.0-or-later
"""The measuring sheet: a well-formed PDF at exact size, with its markers clear of the paper's edge."""

import re

import pytest

from modularack.calibration import A4, LETTER, MARKER, MM, PageSize, grid_origin, marker_centres, pdf

PRINTABLE_MARGIN = 8.0
"""mm: most printers can't print the outer 3-6 mm of a sheet."""


@pytest.mark.parametrize("page", [A4, LETTER])
def test_the_sheet_is_a_two_page_pdf_at_exact_size(page: PageSize) -> None:
    data = pdf(page)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    # Every xref offset points at its own object.
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))  # type: ignore[union-attr]
    entries = re.findall(rb"(\d{10}) 00000 n ", data[xref:])
    for number, offset in enumerate(entries, start=1):
        assert data[int(offset) :].startswith(b"%d 0 obj" % number)
    assert data.count(b"/Type /Page ") == 2
    box = f"/MediaBox [0 0 {page.width * MM:.3f} {page.height * MM:.3f}]".encode()
    assert data.count(box) == 2


@pytest.mark.parametrize("page", [A4, LETTER])
def test_every_marker_prints_clear_of_the_paper_edge(page: PageSize) -> None:
    gx, gy = grid_origin(page)
    for x, y in marker_centres(page).values():
        cx, cy = gx + x, gy + y
        assert cx - MARKER / 2 >= PRINTABLE_MARGIN and cx + MARKER / 2 <= page.width - PRINTABLE_MARGIN
        assert cy - MARKER / 2 >= PRINTABLE_MARGIN and cy + MARKER / 2 <= page.height - PRINTABLE_MARGIN


def test_each_marker_has_its_own_dot_count() -> None:
    assert sorted(marker_centres(A4)) == [1, 2, 3, 4]
