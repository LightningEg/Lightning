"""2K: every Integrity check compares two separate computations, so a wrong figure on one side makes it fail."""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from lightning.bootstrap import build
from lightning.samples import SAMPLE_TODAY, load_mohab_2026

FREE_CASH = "Free cash matches the ledger"


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
        c = build(tmp_path_factory.mktemp("sample") / "s.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def _checks(c, day=None):
    return {check.name: check for check in c.integrity.checks(day or SAMPLE_TODAY)}


def test_mohab_sample_passes_every_check(sample, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    checks = _checks(sample)
    assert FREE_CASH in checks
    assert {name: check.status for name, check in checks.items() if check.status != "PASS"} == {}
    # The free-cash check reads the figure the screens show.
    assert checks[FREE_CASH].actual == sample.position.at(SAMPLE_TODAY, match_payments=False).free_cash


def test_a_wrong_screen_free_cash_fails_the_check(sample, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    real = sample.reporting.owned_liquid_cash
    monkeypatch.setattr(sample.reporting, "owned_liquid_cash", lambda as_of: real(as_of) + D("100"))
    check = _checks(sample)[FREE_CASH]
    assert check.status == "ISSUE" and check.difference == D("100")


def test_a_wrong_ledger_side_fails_the_check(sample, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    real = sample.reporting.money_from_others.cash_total_for_account
    monkeypatch.setattr(sample.reporting.money_from_others, "cash_total_for_account",
                        lambda account_id, day: real(account_id, day) + D("1"))
    assert _checks(sample)[FREE_CASH].status == "ISSUE"


def test_removed_checks_that_compared_a_figure_with_itself(tmp_path):
    c = build(tmp_path / "ledger.db")
    try:
        names = set(_checks(c, "2026-09-30"))
        assert not names & {"Account balances equal asset classes", "Ownership split by account",
                            "What I own plus money held for others equals account balances",
                            "Asset-class report adds to owned net worth",
                            "Free cash plus reserves and bills due equals spendable cash"}
        assert FREE_CASH in names
    finally:
        c.db.close()


# ---- NF-5C: the holdings' lots against the ledger ----
UNITS, NEVER_SHORT, SALES = ("Units held match the ledger", "Nothing was sold that was not held",
                             "Sales match the ledger")


@pytest.fixture
def traded(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    broker = accounts["thndr"].id
    c.investments.buy("2026-02-01", broker, comi.id, "10", "100")
    c.investments.buy("2026-03-01", broker, comi.id, "10", "200")
    c.investments.sell("2026-04-01", broker, comi.id, "12", "250")
    return c, broker, comi


@pytest.mark.parametrize("method", ["average", "fifo"])
def test_the_investment_checks_pass_for_a_normal_history(traded, method):
    c, broker, _ = traded
    c.accounts.set_cost_method(broker, method)
    checks = _checks(c, "2026-12-31")
    assert {name: checks[name].status for name in (UNITS, NEVER_SHORT, SALES)} == dict.fromkeys(
        (UNITS, NEVER_SHORT, SALES), "PASS")


def test_a_sale_of_units_that_were_not_held_is_reported(traded):
    c, _, comi = traded
    c.db.execute("UPDATE ledger_entries SET quantity_e6=quantity_e6*3 WHERE asset_id=? AND quantity_e6<0", (comi.id,))
    check = _checks(c, "2026-12-31")[NEVER_SHORT]
    assert check.status == "ISSUE" and check.actual == D(1)


def test_lots_that_lose_units_break_the_units_check(traded, monkeypatch):
    import lightning.investments.service as service
    real = service.build_lots

    def drop_a_unit(lines, method="average", owner_id=None):
        book = real(lines, method, owner_id)
        if book.lots:
            book.lots[0].quantity -= 1
        return book

    monkeypatch.setattr(service, "build_lots", drop_a_unit)
    check = _checks(traded[0], "2026-12-31")[UNITS]
    assert check.status == "ISSUE" and check.difference == D(-1)


def test_sales_credited_with_the_wrong_proceeds_break_the_sales_check(traded, monkeypatch):
    import lightning.investments.service as service
    real = service.build_lots

    def lose_a_pound(lines, method="average", owner_id=None):
        book = real(lines, method, owner_id)
        for piece in book.disposals:
            piece.proceeds -= 1
        return book

    monkeypatch.setattr(service, "build_lots", lose_a_pound)
    check = _checks(traded[0], "2026-12-31")[SALES]
    assert check.status == "ISSUE" and check.difference == D(-1)
