"""2I: changing the profile currency reaches every service that keeps a copy, without a reopen."""
from __future__ import annotations

from lightning.bootstrap import build
from lightning.database.currencies import CurrencyRegistry


def test_usd_profile_lists_no_foreign_usd_without_reopen(tmp_path):
    c = build(tmp_path / "ledger.db")
    try:
        c.currencies.register("USD")  # as new-profile setup does (runtime/session.py)
        c.set_profile_currency("USD")
        c.accounts.create("Wallet", "CASH", "2026-01-01")
        assert c.accounts.list()[0].currency == "USD"
        assert c.reporting.fx_positions.currencies() == []
        assert c.reporting.fx_positions.base == c.reporting.valuer.base == "USD"
        assert {c.assets.base_currency, c.accounts.base_currency, c.transactions.base_currency,
                c.reporting.base_currency, c.fx.profile_currency} == {"USD"}
    finally:
        c.db.close()


def test_refresh_follows_a_stored_change(tmp_path):
    """A replica that writes the settings row directly needs only `refresh_profile_currency`."""
    c = build(tmp_path / "ledger.db")
    try:
        CurrencyRegistry(c.db).register("USD")
        CurrencyRegistry(c.db).set_base_currency("USD")
        c.reporting.base_currency = "USD"  # what the journal's settings refresh assigns today
        assert c.reporting.fx_positions.base == c.reporting.valuer.base == "USD"
        c.refresh_profile_currency()
        assert c.fx.profile_currency == c.accounts.base_currency == "USD"
    finally:
        c.db.close()
