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
