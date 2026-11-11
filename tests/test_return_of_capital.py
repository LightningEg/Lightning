"""NF-5A4: a return of capital. A fund pays part of what you paid in back: cash arrives (internal, not income), no units
change and the holding's cost falls through a zero-unit cost line (owner decision 2026-11-02). Cost never falls below
zero; what is paid back beyond the cost left is a realized gain."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine, validate_posting
from lightning.core.refs import DocType
from lightning.database import migrator
from lightning.database.connection import Database
from lightning.investments import events
from lightning.investments.lots import cost_returned
from lightning.investments.events import EVENTS, EventValues, Sign, lines_for, validate
from lightning.investments.journey import holding_history
from lightning.investments.report import investment_period

D = Decimal
ASSET = SimpleNamespace(id=7, code="MIDF", unit="unit", quantity_decimals=0)
ACCOUNT = SimpleNamespace(id=3)


def values(**kw):
    return EventValues(**{**dict(asset=ASSET, account=ACCOUNT, cash_asset_id=1, category_ids={}), **kw})


# -- the line and its rule ---------------------------------------------------------------------------------------
def test_a_cost_only_line_is_valid_beside_its_cash():
    lines = [PostingLine.cost_only(3, 7, D("40")), PostingLine.cash(3, 1, D("40"), Effect.INTERNAL)]
    validate_posting(lines)
    assert (lines[0].quantity, lines[0].amount, lines[0].amount_base, lines[0].is_cash) == (D(0), D("-40"), D("-40"), False)


@pytest.mark.parametrize("line,why", [
    (PostingLine(3, 7, D(0), Effect.INTERNAL, D(0), amount=D("40"), amount_base=D("40"), is_cash=False), "cost cannot rise"),
    (PostingLine(3, 7, D(0), Effect.INTERNAL, D(0), amount=D(0), is_cash=False), "no amount at all"),
    (PostingLine(3, 7, D(0), Effect.OUTFLOW, D(0), category_id=1, amount=D("-40"), amount_base=D("-40"), is_cash=False),
     "only an internal line"),
    (PostingLine(3, 7, D(0), Effect.OPENING, D(0), amount=D("-40"), amount_base=D("-40"), is_cash=False), "not opening"),
    (PostingLine(3, 1, D(0), Effect.INTERNAL, D(1), amount=D("-40"), amount_base=D("-40"), is_cash=True),
     "a cash line always moves money"),
])
def test_any_other_zero_quantity_line_is_still_refused(line, why):
    with pytest.raises(ValidationError):
        validate_posting([line, PostingLine.cash(3, 1, D("40"), Effect.INTERNAL)])


def test_a_cost_only_line_must_still_net_to_zero_with_its_cash():
    with pytest.raises(ValidationError, match="net to zero"):
        validate_posting([PostingLine.cost_only(3, 7, D("40")), PostingLine.cash(3, 1, D("30"), Effect.INTERNAL)])


def test_cost_returned_never_goes_below_zero():
    assert cost_returned(D("100"), D("30")) == (D("30"), D("0"))
    assert cost_returned(D("100"), D("100")) == (D("100"), D("0"))
    assert cost_returned(D("100"), D("130")) == (D("100"), D("30"))
    assert cost_returned(D("0"), D("5")) == (D("0"), D("5"))
    assert cost_returned(D("-3"), D("5")) == (D("0"), D("5"))


# -- the row in the table -----------------------------------------------------------------------------------------
def test_the_row_and_its_lines():
    spec = EVENTS["return_of_capital"]
    assert (spec.doc_type, spec.units, spec.cash, spec.income_category, spec.lowers_cost) == (
        DocType.SEL, Sign.NONE, Sign.IN, None, True)
    cost, cash = lines_for("return_of_capital", values(amount="40"))
    assert (cost.quantity, cost.amount, cost.effect, cost.is_cash) == (D(0), D("-40"), Effect.INTERNAL, False)
    assert (cash.quantity, cash.effect, cash.category_id) == (D("40"), Effect.INTERNAL, None)
    validate_posting([cost, cash])


@pytest.mark.parametrize("amount", ["0", "-5", "", "abc", "1.005"])
def test_the_validator_refuses_a_bad_amount(amount):
    with pytest.raises(ValidationError) as error:
        validate("return_of_capital", values(amount=amount))
    assert error.value.field == "amount"


def test_form_fields_ask_only_for_the_amount_and_where_it_went():
    f = events.form_fields("return_of_capital")
    assert (f.units, f.fees, f.income, f.capital, f.cash_account, f.cash_from) == (False, False, False, True, True, False)
    assert not events.form_fields("dividend").capital and not events.form_fields("sell").capital


# -- the database: migration 0070 ---------------------------------------------------------------------------------
def _old_profile(monkeypatch, tmp_path) -> Database:
    old = tmp_path / "migrations_69"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 69:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db")
    migrator.migrate(db)
    assert migrator.inspect_schema(db).current_version == 69
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
    return db


def _seed(db: Database) -> None:
    """Rows of every shape the rebuild must carry: cash, units, a revaluation, a cleared flag, an owner."""
    db.conn.execute("PRAGMA foreign_keys=OFF")
    db.execute("INSERT INTO transactions(id,ref,date,type,status,description,counterparty,notes,source,created_at,updated_at) "
               "VALUES(1,'BUY-2026-09-01-001','2026-09-01','BUY','POSTED','','','','MANUAL','x','x')")
    rows = [(1, 1, 1, 1, 5_000_000, 1_000_000, 5_000_000, 1_000_000, 5_000_000, "INTERNAL", 0, None),
            (2, 1, 2, 2, 10_000_000, 500_000, 5_000_000, 1_000_000, 5_000_000, "INTERNAL", 1, None),
            (3, 1, 3, 2, 0, 1_000_000, 70_000, 1_000_000, 70_000, "REVALUATION", 0, None)]
    for rid, txn, line, asset, qty, price, amount, rate, base, effect, cleared, owner in rows:
        db.execute("INSERT INTO ledger_entries(id,transaction_id,line_no,date,account_id,asset_id,quantity_e6,unit_price_e6,"
                   "amount_e6,fx_rate_e6,amount_base_e6,effect,memo,cleared,owner_id) "
                   "VALUES(?,?,?,'2026-09-01',1,?,?,?,?,?,?,?,'m',?,?)",
                   (rid, txn, line, asset, qty, price, amount, rate, base, effect, cleared, owner))


def test_upgrade_keeps_every_row_and_allows_only_the_cost_only_line(monkeypatch, tmp_path):
    db = _old_profile(monkeypatch, tmp_path)
    _seed(db)
    before = [tuple(r) for r in db.all("SELECT * FROM ledger_entries ORDER BY id")]
    columns = [r[1] for r in db.all("PRAGMA table_info(ledger_entries)")]
    dangling = len(db.all("PRAGMA foreign_key_check"))  # the seed has no accounts or assets; the rebuild adds none
    # 0070 comes next; later migrations follow it (the list grows with every new one).
    pending = migrator.inspect_schema(db).pending
    assert pending[0] == "0070_zero_unit_cost_line" and len(pending) == migrator.BUNDLED_LATEST_VERSION - 69
    with pytest.raises(sqlite3.IntegrityError):  # before: no zero-unit cost line
        db.execute("INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,quantity_e6,unit_price_e6,"
                   "amount_e6,fx_rate_e6,amount_base_e6,effect) VALUES(1,9,'2026-09-02',1,2,0,0,-1000000,1000000,-1000000,'INTERNAL')")
    migrator.migrate(db)
    assert migrator.inspect_schema(db).current_version == migrator.BUNDLED_LATEST_VERSION
    assert [r[1] for r in db.all("PRAGMA table_info(ledger_entries)")] == columns
    assert [tuple(r) for r in db.all("SELECT * FROM ledger_entries ORDER BY id")] == before
    assert len(db.all("PRAGMA foreign_key_check")) == dangling and db.scalar("PRAGMA integrity_check") == "ok"
    names = {r[0] for r in db.all("SELECT name FROM sqlite_master WHERE sql LIKE '%ledger_entries%' OR tbl_name='ledger_entries'")}
    assert {"ix_ledger_account_date", "ix_ledger_asset_date", "ix_ledger_category_date",
            "ix_ledger_account_cleared", "ix_ledger_owner_balance", "v_ledger", "v_balances",
            "tr_ledger_edit_clears_reserve_links", "checked_ledger_insert", "checked_ledger_update", "checked_ledger_delete",
            "checked_transaction_update", "checked_transaction_delete"} <= names
    assert "ix_ledger_transaction" not in names  # 0068 dropped it as a duplicate; the rebuild must not bring it back
    insert = ("INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,quantity_e6,unit_price_e6,"
              "amount_e6,fx_rate_e6,amount_base_e6,effect,category_id) VALUES(1,9,'2026-09-02',1,2,0,0,?,1000000,?,?,NULL)")
    db.execute(insert, (-1_000_000, -1_000_000, "INTERNAL"))  # the one new shape
    for amount, effect in ((1_000_000, "INTERNAL"), (0, "INTERNAL"), (-1_000_000, "OPENING"), (-1_000_000, "OUTFLOW")):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert.replace("VALUES(1,9", "VALUES(1,10"), (amount, amount, effect))
    db.close()


def test_the_checked_month_still_protects_the_rebuilt_table(monkeypatch, tmp_path):
    db = _old_profile(monkeypatch, tmp_path)
    migrator.migrate(db)
    db.conn.execute("PRAGMA foreign_keys=OFF")
    db.execute("INSERT INTO reconciled_through(account_id,date,bank_balance_e6,checked_at) VALUES(1,'2026-10-01',0,'x')")
    with pytest.raises(sqlite3.IntegrityError, match="LN-E0001"):
        db.execute("INSERT INTO ledger_entries(account_id,date) VALUES(1,'2026-09-15')")
    db.close()


# -- the service and every screen --------------------------------------------------------------------------------
def _fund(c, setup, units="100", price="50"):
    accounts, _ = setup
    thndr = accounts["thndr"]
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, thndr.id, "30000")
    fund = c.assets.create_investment("MIDF Fund", "FUND.OTHER", "MIDF")
    c.investments.buy("2026-09-03", thndr.id, fund.id, units, price)  # 5,000 at 50
    c.assets.set_price(fund.id, "2026-09-03", price)
    return accounts, thndr, fund


def _position(c, thndr, fund, day="2026-10-31"):
    return next(p for p in c.investments.portfolio(day, thndr.id).positions if p.asset_id == fund.id)


def test_cash_arrives_units_stay_and_cost_falls(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    cash_before = c.reporting.account_balance(thndr.id, "2026-10-01")
    worth_before = c.reporting.net_worth("2026-10-01").total
    txn = c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "800", notes="Interim")
    assert txn.type == DocType.SEL and sorted(ln.quantity for ln in txn.lines) == [D(0), D("800")]
    assert {ln.effect for ln in txn.lines} == {Effect.INTERNAL}
    assert c.reporting.account_balance(thndr.id, "2026-10-01") == cash_before + D("800")
    p = _position(c, thndr, fund)
    assert (p.quantity, p.cost_basis, p.realized, p.dividends) == (D("100"), D("4200"), D("0"), D("0"))
    assert p.value == D("5000")  # the price did not move: the cash is new money on top of the same value
    assert c.reporting.net_worth("2026-10-01").total == worth_before + D("800")


def test_the_cash_is_not_income_and_money_added_does_not_move(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    flow_before = c.reporting.cash_flow(date(2026, 10, 1), date(2026, 10, 31))
    c.investments.return_of_capital("2026-10-05", thndr.id, fund.id, "800")
    flow = c.reporting.cash_flow(date(2026, 10, 1), date(2026, 10, 31))
    assert (flow.inflows, flow.outflows) == (flow_before.inflows, flow_before.outflows)
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-10-31")
    assert (report["new_money"], report["withdrawn"], report["dividends"]) == (D("0"), D("0"), D("0"))
    held = next(h for h in report["holdings"] if h["asset_id"] == fund.id)
    assert (held["units"], held["cost"], held["realized"], held["unrealized"]) == (D("100"), D("4200"), D("0"), D("800"))
    assert (report["realized"], report["unrealized_change"], report["result"]) == (D("0"), D("800"), D("800"))


def test_more_than_the_cost_left_is_a_realized_gain_and_cost_stops_at_zero(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "4000")
    c.investments.return_of_capital("2026-10-02", thndr.id, fund.id, "1500")  # 1,000 of cost left, 500 beyond it
    p = _position(c, thndr, fund)
    assert (p.quantity, p.cost_basis, p.realized, p.owned_cost_basis, p.owned_realized) == (
        D("100"), D("0"), D("500"), D("0"), D("500"))
    c.investments.return_of_capital("2026-10-03", thndr.id, fund.id, "200")  # nothing left: all of it is gain
    assert (_position(c, thndr, fund).cost_basis, _position(c, thndr, fund).realized) == (D("0"), D("700"))
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-10-31")
    held = next(h for h in report["holdings"] if h["asset_id"] == fund.id)
    assert (held["cost"], held["cost_native"], held["realized"], report["realized"]) == (D("0"), D("0"), D("700"), D("700"))
    # The period result is cash that arrived on top of an unchanged value, in total.
    assert report["result"] == D("5700")
    only_later = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-03", "2026-10-31")
    assert only_later["realized"] == D("200")  # the period's realized gain counts the days inside it only


def test_the_gain_split_leaves_net_worth_exactly_the_cash_received(c, setup):
    """The return moves no unit and no price: net worth rises by the cash, whatever part of it lowered cost or was a gain."""
    accounts, thndr, fund = _fund(c, setup)
    for amount in ("800", "4200", "300"):
        before = c.reporting.net_worth("2026-10-31").total
        c.investments.return_of_capital("2026-10-10", thndr.id, fund.id, amount)
        assert c.reporting.net_worth("2026-10-31").total == before + D(amount)
    p = _position(c, thndr, fund)
    assert (p.cost_basis, p.realized) == (D("0"), D("300"))
    assert p.value - p.cost_basis + p.realized == D("5300")  # unrealized + realized = all the cash that came back


def test_a_later_sale_uses_the_lower_average_cost(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "1000")  # cost 4,000 for 100 units: 40 each
    c.investments.sell("2026-10-02", thndr.id, fund.id, "50", "60")  # 3,000 for cost 2,000
    p = _position(c, thndr, fund)
    assert (p.quantity, p.cost_basis, p.realized) == (D("50"), D("2000"), D("1000"))
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-10-31")
    assert report["realized"] == D("1000")


def test_a_return_is_scoped_to_the_owner_who_holds_the_units(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    friend = c.counterparties.create("Sara")
    salary = setup[1]["EXP.WORK.SALARY"].id
    c.transactions.record_inflow("2026-09-03", thndr.id, "600", salary, owner_id=friend)  # Sara's own money
    c.investments.buy("2026-09-04", thndr.id, fund.id, "10", "50", owner_id=friend)  # 500 held for Sara
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "100", owner_id=friend)
    p = _position(c, thndr, fund)
    assert (p.owned_cost_basis, p.cost_basis) == (D("5000"), D("5400"))  # only Sara's pool lost cost


def test_the_cash_can_go_to_another_account_and_leaves_the_portfolio(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    bank_before = c.reporting.account_balance(accounts["cib"].id, "2026-10-01")
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "800", cash_account_id=accounts["cib"].id)
    assert c.reporting.account_balance(accounts["cib"].id, "2026-10-01") == bank_before + D("800")
    report = investment_period(c.db, c.accounts, c.assets, c.reporting, "2026-10-01", "2026-10-31")
    assert (report["new_money"], report["withdrawn"]) == (D("0"), D("800"))  # the money left the portfolio


@pytest.mark.parametrize("kw,field", [
    (dict(amount="0"), "amount"), (dict(amount="-3"), "amount"), (dict(amount="12.345"), "amount"),
    (dict(amount="10", date="2026-09-01"), "instrument"),  # before the units were bought
])
def test_the_service_refuses_bad_returns(c, setup, kw, field):
    accounts, thndr, fund = _fund(c, setup)
    args = {"date": "2026-10-01", **kw}
    with pytest.raises(ValidationError) as error:
        c.investments.return_of_capital(args.pop("date"), thndr.id, fund.id, args.pop("amount"))
    assert error.value.field == field


def test_it_needs_a_brokerage_and_a_holding(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    other = c.assets.create_investment("Other Fund", "FUND.OTHER", "OTHR")
    with pytest.raises(ValidationError) as error:
        c.investments.return_of_capital("2026-10-01", thndr.id, other.id, "10")  # none held
    assert error.value.field == "instrument"
    with pytest.raises(ValidationError) as error:
        c.investments.return_of_capital("2026-10-01", accounts["cib"].id, fund.id, "10")
    assert error.value.field == "account"
    c.investments.sell("2026-10-02", thndr.id, fund.id, "100", "50")
    with pytest.raises(ValidationError):  # sold out: nothing left to pay back from
        c.investments.return_of_capital("2026-10-03", thndr.id, fund.id, "10")


def test_edit_in_place_values_and_void(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    txn = c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "800")
    stored = c.investments.values_of(txn.id)
    assert (stored["kind"], stored["amount"], stored["account_id"], stored["asset_id"], stored["cash_account_id"]) == (
        "return_of_capital", D("800"), thndr.id, fund.id, thndr.id)
    updated = c.investments.update(txn.id, date="2026-10-02", account_id=thndr.id, asset_id=fund.id, amount="1000")
    assert updated.ref == txn.ref and updated.date == "2026-10-02"
    assert _position(c, thndr, fund).cost_basis == D("4000")
    with pytest.raises(ValidationError):
        c.investments.update(txn.id, account_id=thndr.id, asset_id=fund.id, amount="0")
    c.transactions.void(txn.id, "mistake")
    assert _position(c, thndr, fund).cost_basis == D("5000")
    assert c.investments.holding(thndr.id, fund.id, "2026-10-31") == D("100")


def test_a_return_does_not_become_the_asset_price(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    c.db.execute("DELETE FROM price_history WHERE asset_id=?", (fund.id,))
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "800")
    latest = c.reporting.q.latest_trade_price(fund.id, "2026-10-31")
    assert latest["price_e6"] == 50_000_000  # the buy at 50, never the zero-unit line's price of 0


def test_the_holding_journey_names_it_and_the_cost_follows(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "800")
    journey = holding_history(c.reporting, c.investments, thndr.id, fund.id, date(2026, 10, 31))
    row = next(t for t in journey["trades"] if t["kind"] == "Capital returned")
    assert (row["units"], row["amount"], row["price"], row["held"]) == (D("0"), D("800"), None, D("100"))
    assert journey["cost"][-1] == D("4200") and journey["average"] == D("42")
    assert journey["average_native"] == D("42")


def test_the_integrity_checks_still_pass(c, setup):
    accounts, thndr, fund = _fund(c, setup)
    c.investments.return_of_capital("2026-10-01", thndr.id, fund.id, "6000")
    failing = {check.name: check.status for check in c.integrity.checks("2026-10-31") if check.status != "PASS"}
    assert failing == {}
    ledger = c.db.scalar("SELECT COALESCE(SUM(le.amount_base_e6),0) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                         "WHERE t.type='SEL' AND le.effect='INTERNAL'")
    assert ledger == 0  # the internal lines of every sale and return net to zero


# -- the entry form and the edit form -------------------------------------------------------------------------------
def test_the_entry_form_posts_and_edits_a_return(c, setup):
    from fastapi.testclient import TestClient

    from lightning.ui.web import create_app
    accounts, thndr, fund = _fund(c, setup)
    client = TestClient(create_app(c))
    page = client.get(f"/investments/new?kind=return_of_capital&account={thndr.id}").text
    assert 'name="amount"' in page and 'name="cash_account_id"' in page and 'Return of capital' in page
    assert 'name="quantity"' not in page and 'name="fees"' not in page and 'name="total"' not in page
    posted = client.post("/investments/new?kind=return_of_capital", data={
        "date": "2026-10-01", "account_id": thndr.id, "asset_id": fund.id, "amount": "800"})
    assert "Saved SEL-2026-10-01-001" in posted.text
    txn = c.transactions.get_by_ref("SEL-2026-10-01-001")
    assert _position(c, thndr, fund).cost_basis == D("4200")
    form = client.get(f"/investments/{txn.id}/edit")
    assert form.status_code == 200 and 'value="800' in form.text and 'name="quantity"' not in form.text
    saved = client.post(f"/investments/{txn.id}/edit", data={
        "date": "2026-10-01", "account_id": thndr.id, "asset_id": fund.id, "amount": "1200"})
    assert "Saved SEL-2026-10-01-001" in saved.text and _position(c, thndr, fund).cost_basis == D("3800")
    refused = client.post("/investments/new?kind=return_of_capital", data={
        "date": "2026-10-01", "account_id": thndr.id, "asset_id": fund.id, "amount": "0"})
    assert refused.status_code == 400 and "Enter the amount paid back." in refused.text
