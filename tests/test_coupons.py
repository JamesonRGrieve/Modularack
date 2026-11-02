# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coupons: small prints of every critical fit, cut from the real parts."""

import pytest

from zephyrack.checks import check
from zephyrack.coupons import COUPON_NOTES, Coupon, CouponSet


@pytest.fixture(scope="module")
def coupons() -> CouponSet:
    return CouponSet()


def test_every_coupon_prints_alone_and_the_pairs_mate(coupons: CouponSet) -> None:
    report = check(coupons)
    assert report.clean, report


def test_every_fit_has_its_coupon_and_its_instructions(coupons: CouponSet) -> None:
    names = {c.name.removesuffix("_a").removesuffix("_b") for c in coupons.children.values() if isinstance(c, Coupon)}
    assert names == set(COUPON_NOTES)


def test_the_edge_insert_coupon_lists_its_hardware(coupons: CouponSet) -> None:
    assert sum("insert" in item.lower() for item in coupons.hardware) == 2
    assert sum("countersunk" in item for item in coupons.hardware) == 2
