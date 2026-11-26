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
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app

    accounts, _ = setup
    friend = c.counterparties.ensure_person("Omar")
    account = c.people_money.account_for(friend, "2026-09-01")
    before = c.position.at()
    c.transactions.record_transfer("2026-10-01", account.id, accounts["cib"].id, "700", "Omar lent me")
    after = c.position.at()
    assert after.you_owe_people == D(700) and after.owed_to_you == 0
    assert after.what_you_owe == before.what_you_owe + 700 and after.net_worth == before.net_worth
    assert after.in_your_accounts == before.in_your_accounts
    with TestClient(create_app(c)) as browser:
        home = browser.get("/").text
    debt = home.split("What you owe</span>", 1)[1].split("</details>", 1)[0]
    assert "You owe people" in debt and "<b>700</b>" in debt


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


def test_a_dinner_split_with_two_friends_spends_only_your_share_and_each_repays_their_own(c, setup):
    """NF-12G3: a 1,200 dinner split with two people at 400 each."""
    accounts, _ = setup
    cib = accounts["cib"]
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    sara, omar = c.counterparties.ensure_person("Sara"), c.counterparties.ensure_person("Omar")
    cash0, net0, spent0 = c.reporting.account_balance(cib.id), c.position.at().net_worth, _spent(c)

    txn = c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "400"), (omar, "400")], notes="Dinner")
    p = c.position.at()
    assert c.reporting.account_balance(cib.id) == cash0 - 1200
    assert _spent(c) == spent0 + 400
    assert p.owed_to_you == D(800) and c.people_money.balance(sara) == c.people_money.balance(omar) == D(400)
    assert p.net_worth == net0 - 400
    assert txn.ref.startswith("OUT") and txn.description == "Split with Sara and Omar"
    assert c.transactions.summarize(txn).amount == D(-1200)  # what the account paid, not the net
    assert [r.amount for r in c.reporting.register(cib.id, "2026-10-01", "2026-10-31")] == [D(-1200)]

    c.people_money.repay("2026-10-10", sara, cib.id, "400")
    assert c.people_money.balance(sara) == 0 and c.people_money.balance(omar) == D(400)
    assert c.position.at().owed_to_you == D(400) and c.position.at().net_worth == net0 - 400
    assert c.reporting.account_balance(cib.id) == cash0 - 800

    # Editing moves every line together, and the ref stays; voiding takes them all away.
    edited = c.people_money.update_split(txn.id, "2026-10-05", cib.id, "900", food, [(sara, "400"), (omar, "300")])
    assert edited.ref == txn.ref and c.people_money.balance(omar) == D(300) and _spent(c) == spent0 + 200
    c.transactions.void(txn.id, "test")
    assert c.people_money.balance(omar) == 0 and _spent(c) == spent0
    assert c.reporting.account_balance(cib.id) == cash0 + 400  # only Sara's repayment is left


def test_a_split_refuses_shares_that_leave_you_nothing_and_cannot_be_flattened_by_a_plain_edit(c, setup):
    accounts, _ = setup
    cib = accounts["cib"]
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    sara, omar = c.counterparties.ensure_person("Sara"), c.counterparties.ensure_person("Omar")
    with pytest.raises(ValidationError, match="less than the total"):
        c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "600"), (omar, "600")])
    with pytest.raises(ValidationError, match="less than the total"):
        c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "1300")])
    with pytest.raises(ValidationError, match="above zero"):
        c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "0")])
    with pytest.raises(ValidationError, match="once"):
        c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "100"), (sara, "100")])
    with pytest.raises(ValidationError, match="at least one person"):
        c.people_money.split("2026-10-05", cib.id, "1200", food, [])

    txn = c.people_money.split("2026-10-05", cib.id, "1200", food, [(sara, "400")])
    with pytest.raises(ValidationError, match="split with others"):
        c.transactions.update_money(txn.id, "2026-10-05", cib.id, "1200", food)
    with pytest.raises(ValidationError, match="split with others"):
        c.transactions.update_in_account(txn.id, cib.id, "2026-10-05", "-1000", food)
    c.transactions.update_in_account(txn.id, cib.id, "2026-10-06", "-1200", food, notes="Birthday")
    assert c.people_money.balance(sara) == D(400) and c.transactions.get(txn.id).notes == "Birthday"
