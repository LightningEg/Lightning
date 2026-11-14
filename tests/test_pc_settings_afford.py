"""PC pass 2026-10-28: price upload from a spreadsheet, Settings as rows."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from lightning.assets.price_csv import read_prices


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


def test_price_file_never_guesses_a_comma_price_or_takes_an_impossible_or_future_day():
    data = b'Symbol,Date,Price\nCOMI,2026-10-01,"12,5"\nCOMI,2026-13-45,10\nCOMI,2026-11-02,10\nCOMI,2026-10-02,"1,250.50"\n'
    rows = read_prices(data, ASSETS, "2026-10-28")
    assert rows.matched == [(ASSETS[0].id, "2026-10-02", Decimal("1250.50"))] and len(rows.bad) == 3


def test_price_file_keeps_one_price_per_investment_and_day():
    rows = read_prices(b"Symbol,Date,Price\nCOMI,2026-10-02,10\nCOMI,2026-10-02,11\n", ASSETS, "2026-10-28")
    assert rows.matched == [(ASSETS[0].id, "2026-10-02", Decimal(11))]


def test_the_profile_app_lets_the_price_csv_through_as_one_bounded_file():
    from lightning.runtime.app import _form_file_limit
    from lightning.core.limits import MAX_CSV_UPLOAD_REQUEST_BYTES
    from lightning.runtime.http import PRICE_CSV_PATH, request_body_limit
    assert _form_file_limit(PRICE_CSV_PATH) == 1 and request_body_limit(PRICE_CSV_PATH) == MAX_CSV_UPLOAD_REQUEST_BYTES
