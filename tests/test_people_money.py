"""NF-12G2: money lent to a person, paid back and forgiven. One Owed to you account per person; lending and
repayment are transfers (Net worth unchanged), forgiving is spending; below zero is what you owe them."""
from __future__ import annotations

import shutil
from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError

D = Decimal


def _spent(c, day="2026-12-31"):
    return sum((row["value"] for row in c.reporting.spending_lines("2026-01-01", day)), D(0))


def test_lend_repay_and_forgive_move_cash_owed_to_you_and_net_worth_as_they_should(c, setup):
    accounts, cats = setup
    cib = accounts["cib"]
    brother = c.counterparties.ensure_person("Ahmed")
    gift = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    cash0, net0, spent0 = c.reporting.account_balance(cib.id), c.position.at().net_worth, _spent(c)

    c.people_money.lend("2026-10-01", brother, cib.id, "5000")
    p = c.position.at()
    assert c.reporting.account_balance(cib.id) == cash0 - 5000
    assert c.people_money.owed_to_you() == p.owed_to_you == D(5000) and p.other_you_own >= D(5000)
    assert p.net_worth == net0 and _spent(c) == spent0
    assert c.people_money.account_for(brother).account_type == "RECEIVABLE"

    c.people_money.repay("2026-11-01", brother, cib.id, "3000")
    p = c.position.at()
    assert c.reporting.account_balance(cib.id) == cash0 - 2000
    assert p.owed_to_you == D(2000) and p.net_worth == net0 and _spent(c) == spent0
    with pytest.raises(ValidationError, match="owes you"):
        c.people_money.repay("2026-11-02", brother, cib.id, "2001")

    c.people_money.forgive("2026-12-01", brother, "2000", gift)
    p = c.position.at()
    assert p.owed_to_you == 0 and c.people_money.balance(brother) == 0
    assert p.net_worth == net0 - 2000 and _spent(c) == spent0 + 2000
    with pytest.raises(ValidationError, match="cannot forgive"):
        c.people_money.forgive("2026-12-02", brother, "1", gift)


def test_lending_more_cash_than_you_own_is_refused_and_owed_to_you_is_not_a_holding(c, setup):
    accounts, _ = setup
    friend = c.counterparties.ensure_person("Sara")
    with pytest.raises(ValidationError, match="of your cash"):
        c.people_money.lend("2026-10-01", friend, accounts["wallet"].id, "5000")  # the wallet holds 1,200
    c.people_money.lend("2026-10-01", friend, accounts["wallet"].id, "1000")
    holdings, _ = c.position.owned_holdings("2026-12-31")
    assert all(h.class_code != "RECEIVABLE" for h in holdings)
    assert c.position.at().holdings_value == c.position.at("2026-09-30").holdings_value


def test_a_person_account_below_zero_counts_in_what_you_owe(c, setup):
    accounts, _ = setup
    friend = c.counterparties.ensure_person("Omar")
    account = c.people_money.account_for(friend, "2026-09-01")
    before = c.position.at()
    c.transactions.record_transfer("2026-10-01", account.id, accounts["cib"].id, "700", "Omar lent me")
    after = c.position.at()
    assert after.you_owe_people == D(700) and after.owed_to_you == 0
    assert after.what_you_owe == before.what_you_owe + 700 and after.net_worth == before.net_worth
    assert after.in_your_accounts == before.in_your_accounts


def test_an_older_profile_upgrades_and_takes_the_owed_to_you_class(monkeypatch, tmp_path):
    from lightning.database import migrator
    from lightning.database.connection import Database

    old = tmp_path / "migrations_77"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 77:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    migrator.migrate(db)
    assert db.scalar("SELECT name FROM asset_classes WHERE code='RECEIVABLE'") == "Owed to you"
    assert db.scalar("SELECT COUNT(*) FROM owed_to_you_accounts") == 0
    migrator.migrate(db)
    db.close()
