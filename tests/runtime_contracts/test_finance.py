"""Dependency-free financial contracts, runnable by unittest on the minimum Python.

Run: python -m unittest discover -s tests/runtime_contracts -v
No pytest/conftest, web framework, native wheels, network or user profile is required.
"""
from datetime import date
from decimal import Decimal as D
import unittest

from lightning.bank_imports import decode_csv
from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError
from lightning.core.money import fmt, from_e6, to_decimal, to_e6
from lightning.investments.xirr import xirr
from lightning.planning.domain import Frequency, PlanKind, PlannedItem, WeekendMove
from lightning.planning.schedule import scheduled_dates


class MinimumRuntimeFinance(unittest.TestCase):
    def test_exact_arabic_amounts_roundtrip_and_half_up_display(self):
        value = to_decimal("١٬٢٥٠٫٥٠") + D("0.000001")
        self.assertEqual(value, D("1250.500001"))
        self.assertEqual(to_e6(value), 1_250_500_001)
        self.assertEqual(from_e6(to_e6(value)), value)
        self.assertEqual(fmt(D("468.50"), 0), "469")
        with self.assertRaises(ValidationError):
            to_e6(D("0.0000001"))

    def test_leap_day_and_arabic_day_first_dates(self):
        self.assertEqual(parse_date("٢٩/٠٢/٢٠٢٤"), date(2024, 2, 29))
        with self.assertRaises(ValidationError):
            parse_date("2025-02-29")

    def test_statement_bom_quoted_fields_and_exact_amount(self):
        columns, rows = decode_csv('\ufeffDate,Amount,Counterparty\n2024-02-29,"-1,250.50","Café, Cairo"\n'.encode())
        self.assertEqual(columns, ["Date", "Amount", "Counterparty"])
        self.assertEqual(rows, [{"Date": "2024-02-29", "Amount": "-1,250.50", "Counterparty": "Café, Cairo", "__line__": "2"}])
        self.assertEqual(to_e6(to_decimal(rows[0]["Amount"])), -1_250_500_000)

    def test_month_end_schedule_retains_anchor_across_leap_february(self):
        item = PlannedItem(id=1, kind=PlanKind.BILL, name="Dummy bill", amount=D("100"),
                           frequency=Frequency.MONTHLY, interval_count=1, start_date="2024-01-31",
                           end_date=None, payment_count=3, account_id=None, category_id=None,
                           counterparty_id=None, principal=None, active=True, notes="", weekend_move=WeekendMove.NONE)
        self.assertEqual(scheduled_dates(item, "2024-03-31"), [
            (1, "2024-01-31", "2024-01-31"), (2, "2024-02-29", "2024-02-29"),
            (3, "2024-03-31", "2024-03-31")])

    def test_unique_annual_return_and_inadequate_history(self):
        self.assertAlmostEqual(xirr([("2023-01-01", D("-1000")), ("2024-01-01", D("1100"))]), D("0.1"), places=10)
        self.assertIsNone(xirr([("2023-01-01", D("100"))]))


if __name__ == "__main__":
    unittest.main()
