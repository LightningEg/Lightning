"""Audit regressions: conversion rate winners, bounded reads and atomic writes.

Uses unittest so these financial checks also run without optional pytest tooling.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightning.bootstrap import build
from lightning.core.errors import ValidationError
from lightning.transactions import conversion


class BackendEngineAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.c = build(Path(self.folder.name) / "audit.db")
        self.addCleanup(self.c.db.close)
        self.bank = self.c.account_flows.open_account("Bank", "BANK", "2026-01-01", "1000000")
        self.accounts = {"EGP": self.bank}
        for currency, rate in (("USD", "50"), ("EUR", "60")):
            self.c.currencies.register(currency)
            self.c.fx.save(currency, "2026-01-01", rate)
            self.accounts[currency] = self.c.account_flows.open_account(
                currency, "BANK", "2026-01-01", "0", currency=currency)

    def buy(self, sent="50", received="1", day="2026-01-02", currency="USD"):
        return self.c.transactions.record_conversion(
            day, self.bank.id, self.accounts[currency].id, sent, received)

    def rates(self):
        return [tuple(row) for row in self.c.db.all(
            "SELECT date,base,quote,rate_e6,source FROM fx_rates ORDER BY date,base,quote,source")]

    def assert_matches_repair(self):
        actual = self.rates()
        conversion.rebuild_trade_rates(self.c.transactions)
        self.assertEqual(self.rates(), actual)

    def test_latest_same_day_winner_edit_void_restore_and_bulk_delete_match_repair(self):
        first = self.buy("50")
        second = self.buy("55")
        unrelated = self.buy("60", currency="EUR")
        self.assert_matches_repair()
        self.c.transactions.void(second.id)
        self.assertEqual(self.c.db.scalar(
            "SELECT rate_e6 FROM fx_rates WHERE source='TRADE' AND base='USD'"), 50_000_000)
        self.assert_matches_repair()
        self.c.transactions.restore(second.id)
        self.assert_matches_repair()
        # Move both date and pair; the old USD key falls back to the first conversion.
        self.c.transactions.update_conversion(second.id, "2026-01-03", self.bank.id,
                                              self.accounts["EUR"].id, "65", "1")
        self.assert_matches_repair()
        self.c.transactions.delete_many([first.id, second.id, unrelated.id])
        self.assertFalse(self.c.db.scalar("SELECT 1 FROM fx_rates WHERE source='TRADE'"))
        self.assert_matches_repair()

    def test_editing_an_older_conversion_does_not_replace_same_day_winner(self):
        older = self.buy("50")
        self.buy("55")
        self.c.transactions.update_conversion(older.id, "2026-01-02", self.bank.id,
                                              self.accounts["USD"].id, "52", "1")
        self.assertEqual(self.c.db.scalar(
            "SELECT rate_e6 FROM fx_rates WHERE source='TRADE' AND base='USD'"), 55_000_000)
        self.assert_matches_repair()

    def test_reverse_and_foreign_cross_conversions_preserve_full_rebuild_semantics(self):
        self.buy("500", "10")
        self.c.transactions.record_conversion("2026-01-03", self.accounts["USD"].id,
                                             self.bank.id, "1", "51", fee="0.10")
        self.c.transactions.record_conversion("2026-01-04", self.accounts["USD"].id,
                                             self.accounts["EUR"].id, "1", "0.80")
        self.assert_matches_repair()

    def test_unrelated_rates_are_not_rewritten(self):
        self.buy("60", currency="EUR")
        before = [tuple(row) for row in self.c.db.all(
            "SELECT * FROM fx_rates WHERE base='EUR' OR source='MANUAL' ORDER BY id")]
        self.buy("50")
        self.assertEqual([tuple(row) for row in self.c.db.all(
            "SELECT * FROM fx_rates WHERE base='EUR' OR source='MANUAL' ORDER BY id")], before)

    def test_transaction_reads_stay_bounded_with_same_day_history(self):
        reads = []
        original = self.c.transactions.get
        def counted(*args, **kwargs):
            reads.append(args[0])
            return original(*args, **kwargs)
        with patch.object(self.c.transactions, "get", counted):
            for index in range(30):
                reads.clear()
                self.buy(str(50 + index))
                self.assertLessEqual(len(reads), 3)

    def test_rate_save_failure_rolls_back_conversion_create_and_edit(self):
        txn = self.buy()
        before_rates = self.rates()
        before_rows = [tuple(row) for row in self.c.db.all("SELECT * FROM transactions ORDER BY id")]
        before_lines = [tuple(row) for row in self.c.db.all("SELECT * FROM ledger_entries ORDER BY id")]
        with patch.object(conversion, "save_rate", side_effect=RuntimeError("rate write failed")):
            for operation in (
                lambda: self.buy("55"),
                lambda: self.c.transactions.update_conversion(
                    txn.id, "2026-01-03", self.bank.id, self.accounts["USD"].id, "55", "1"),
            ):
                with self.assertRaisesRegex(RuntimeError, "rate write failed"):
                    operation()
                self.assertEqual(self.rates(), before_rates)
                self.assertEqual([tuple(row) for row in self.c.db.all(
                    "SELECT * FROM transactions ORDER BY id")], before_rows)
                self.assertEqual([tuple(row) for row in self.c.db.all(
                    "SELECT * FROM ledger_entries ORDER BY id")], before_lines)

    def test_split_precision_is_refused_without_changing_balances(self):
        food = self.c.categories.get_by_code("EXP.PERSONAL.FOOD")
        txn = self.c.transactions.record_outflow("2026-01-02", self.bank.id, "1000", food.id)
        before = self.c.reporting.account_balance(self.bank.id, "2026-01-02")
        with self.assertRaises(ValidationError):
            self.c.transactions.update_expense_split(
                txn.id, [(food.id, "333.334"), (food.id, "333.333"), (food.id, "333.333")])
        self.assertEqual(self.c.reporting.account_balance(self.bank.id, "2026-01-02"), before)
        self.c.transactions.update_expense_split(txn.id, [(food.id, "333.34"), (food.id, "666.66")])
        self.assertEqual(self.c.reporting.account_balance(self.bank.id, "2026-01-02"), before)

    def test_manual_overspend_and_cash_in_physical_accounts_are_refused(self):
        food = self.c.categories.get_by_code("EXP.PERSONAL.FOOD")
        with self.assertRaises(ValidationError):
            self.c.transactions.record_outflow("2026-01-02", self.bank.id, "1000001", food.id)
        physical = self.c.account_flows.open_account("Gold", "PHYSICAL_ASSET", "2026-01-01", "0")
        with self.assertRaises(ValidationError):
            self.c.transactions.record_outflow("2026-01-02", physical.id, "10", food.id)
        self.assertEqual(self.c.reporting.account_balance(self.bank.id, "2026-01-02"), Decimal("1000000"))


if __name__ == "__main__":
    unittest.main()
