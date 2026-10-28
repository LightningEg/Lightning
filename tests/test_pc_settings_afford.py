"""PC pass 2026-10-28: Can I afford this?, price upload from a spreadsheet, Settings as rows."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from lightning.assets.price_csv import read_prices
from lightning.planning.afford import can_afford


def test_fits_inside_safe_to_spend_is_yes():
    a = can_afford(Decimal(3000), Decimal(5000), Decimal(9000), "2026-11-01")
    assert a.verdict == "yes" and a.left == Decimal(2000)


def test_fits_only_in_free_cash_eats_the_plan():
    a = can_afford(Decimal(7000), Decimal(5000), Decimal(9000), None)
    assert a.verdict == "plan" and a.left == Decimal(-2000) and a.short == 0


def test_past_free_cash_is_no_with_the_shortfall():
    a = can_afford(Decimal(12000), Decimal(5000), Decimal(9000), None)
    assert a.verdict == "no" and a.short == Decimal(3000)


def test_zero_or_negative_amount_is_refused():
    with pytest.raises(ValueError):
        can_afford(Decimal(0), Decimal(5000), Decimal(9000), None)


ASSETS = [SimpleNamespace(id=1, name="Commercial International Bank", ticker="COMI", isin="EGS60121C018"),
          SimpleNamespace(id=2, name="Gold 21K", ticker="", isin=None)]


def test_price_file_matches_symbol_isin_and_name():
    data = b"Symbol,Date,Price\nCOMI,2026-10-27,80.5\nEGS60121C018,2026-10-28,81\ngold 21k,,4100\n"
    rows = read_prices(data, ASSETS, "2026-10-28")
    assert rows.matched == [(1, "2026-10-27", Decimal("80.5")), (1, "2026-10-28", Decimal("81")),
                            (2, "2026-10-28", Decimal("4100"))]


def test_price_file_reports_unknown_and_bad_rows_without_guessing():
    rows = read_prices(b"Name,Price\nNOPE,10\nCOMI,abc\nCOMI,-3\n", ASSETS, "2026-10-28")
    assert rows.matched == [] and rows.unmatched == ["NOPE"] and len(rows.bad) == 2


def test_price_file_without_a_price_column_is_refused():
    with pytest.raises(ValueError):
        read_prices(b"Symbol,Amount\nCOMI,1\n", ASSETS, "2026-10-28")
