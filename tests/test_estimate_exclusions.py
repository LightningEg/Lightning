"""NF-12AK2 (#643, owner decisions 2026-11-13): leave one transaction out of estimates. The estimate basis skips an
excluded expense and the refunds and claim receipts linked to it; Cash flow and Spent keep it; the switch is optional,
on the PC and phone edit and under More on add, and undoable; an older profile upgrades."""
from __future__ import annotations

import shutil

import pytest

from lightning.database import migrator
from lightning.database.connection import Database
from lightning.database.seed import seed


@pytest.mark.parametrize("encrypted", [False, True])
def test_an_older_profile_upgrades_and_keeps_its_rows(monkeypatch, tmp_path, encrypted):
    if encrypted:
        pytest.importorskip("sqlcipher3")
    old = tmp_path / "migrations_85"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 85:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db", key=bytes(range(32)) if encrypted else None)
    try:
        migrator.migrate(db)
        seed(db)
        db.execute("INSERT INTO transactions(ref,type,date,status,description,created_at,updated_at) "
                   "VALUES('OUT-0001','OUT','2026-09-02','POSTED','Laptop','2026-09-02','2026-09-02')")
        before = [dict(r) for r in db.all("SELECT * FROM transactions")]
        monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)
        assert migrator.migrate(db) == ["0086_budget_estimate_exclusions (APPLIED)"]
        assert [dict(r) for r in db.all("SELECT * FROM transactions")] == before
        assert db.scalar("SELECT count(*) FROM budget_estimate_exclusions") == 0
        txn = before[0]["id"]
        db.execute("INSERT INTO budget_estimate_exclusions(transaction_id,created_at,updated_at) VALUES(?,?,?)",
                   (txn, "2026-11-14", "2026-11-14"))
        with pytest.raises(Exception):  # one row per transaction
            db.execute("INSERT INTO budget_estimate_exclusions(transaction_id,created_at,updated_at) VALUES(?,?,?)",
                       (txn, "2026-11-14", "2026-11-14"))
        assert migrator.migrate(db) == []  # a second run does nothing
        assert db.scalar("SELECT max(version) FROM schema_migrations") == 86
    finally:
        db.close()


# --------------------------------------------------------------------------- the estimate basis
from decimal import Decimal  # noqa: E402

from lightning.core.dates import parse_month  # noqa: E402
from lightning.core.errors import ValidationError  # noqa: E402


def _ids(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.WORK.TRANSPORT").id


def _average(c, category_id, month):
    return c.budgets.category_averages(month, schedule=c.schedules.view())[category_id]["average3"]


def _basis(c, category_id, month):
    return c.budgets.estimate_spending(*parse_month(month)).get(category_id, Decimal(0))


def _spent(c, category_id, month):
    return c.budgets.owned_spending(*parse_month(month)).get(category_id, Decimal(0))


def _cash_out(c, month):
    return c.reporting.cash_flow(*parse_month(month))


def _laptop_year(c, accounts):
    food, _ = _ids(c)
    for month in ("2026-08", "2026-09", "2026-10", "2026-11"):
        c.transactions.record_outflow(f"{month}-05", accounts["cib"].id, "1000", food)
    return c.transactions.record_outflow("2026-10-12", accounts["cib"].id, "9000", food, description="Laptop")


def test_the_laptop_left_out_averages_1000_and_stays_in_cash_flow_and_spent(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    laptop = _laptop_year(c, accounts)
    assert _average(c, food, "2026-12") == Decimal("4000.00")  # September to November with the laptop
    cash_before, spent_before = _cash_out(c, "2026-10"), _spent(c, food, "2026-10")
    assert c.budgets.set_left_out(laptop.id, True) is True
    assert c.budgets.is_left_out(laptop.id)
    assert _average(c, food, "2026-12") == Decimal("1000.00")
    assert _basis(c, food, "2026-10") == Decimal("1000")
    assert (_cash_out(c, "2026-10"), _spent(c, food, "2026-10")) == (cash_before, spent_before)
    assert spent_before == Decimal("10000")
    assert c.budgets.set_left_out(laptop.id, True) is False  # already left out
    assert c.budgets.set_left_out(laptop.id, False) is True
    assert _average(c, food, "2026-12") == Decimal("4000.00")


def test_a_purchase_alone_in_its_category_leaves_no_month_behind(c, setup):
    accounts, _ = setup
    food, work = _ids(c)
    c.transactions.record_outflow("2026-08-05", accounts["cib"].id, "1000", food)  # history before the window
    bike = c.transactions.record_outflow("2026-10-12", accounts["cib"].id, "9000", work)
    c.budgets.set_left_out(bike.id, True)
    assert work not in c.budgets.estimate_spending(*parse_month("2026-10"))  # not a month of zero spending


def test_its_linked_refunds_and_claim_receipts_leave_with_it(c, setup):
    accounts, _ = setup
    food, work = _ids(c)
    c.transactions.record_outflow("2026-08-05", accounts["cib"].id, "300", food)
    purchase = c.transactions.record_outflow("2026-09-02", accounts["cib"].id, "6000", food)
    c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "500", food)
    refund = c.transactions.record_refund("2026-11-12", accounts["cib"].id, "2000", food)
    c.refunds.link(refund.id, purchase.id)
    trip = c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "1200", work)
    c.transactions.record_outflow("2026-11-04", accounts["cib"].id, "100", work)
    claim = c.reimbursements.create_claim(trip.id, "1200")
    receipt = c.transactions.record_inflow("2026-11-20", accounts["cib"].id, "1200", work)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "1200")
    unlinked = c.transactions.record_refund("2026-11-25", accounts["cib"].id, "200", food)
    assert unlinked.id
    c.budgets.set_left_out(purchase.id, True)
    c.budgets.set_left_out(trip.id, True)
    assert food not in c.budgets.estimate_spending(*parse_month("2026-09"))
    assert _basis(c, food, "2026-11") == Decimal("300")  # its own 500 less the unlinked 200; the linked 2,000 left
    assert work not in c.budgets.estimate_spending(*parse_month("2026-10"))
    assert _basis(c, work, "2026-11") == Decimal("100")  # the receipt left with its expense
    assert _spent(c, food, "2026-11") == Decimal("-1700")  # Spent keeps every refund on its real date
    c.budgets.set_left_out(purchase.id, False)
    assert _basis(c, food, "2026-09") == Decimal("4000")  # counted again: the linked refund back in its month


def test_a_reserve_funded_purchase_is_not_taken_out_twice(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.transactions.record_outflow("2026-10-05", accounts["cib"].id, "1000", food)
    laptop = c.transactions.record_outflow("2026-10-12", accounts["cib"].id, "9000", food)
    start, end = parse_month("2026-10")
    funded = c.budgets.plan_funded_spending(start, end)[food]
    c.budgets.set_left_out(laptop.id, True)
    # Without funding the month keeps its 1,000; with some, never less than what funding left nor below zero.
    assert _basis(c, food, "2026-10") == min(funded, Decimal("1000"))


def test_only_an_expense_can_be_left_out(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    income = c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "5000",
                                          c.categories.get_by_code("EXP.PERSONAL.OTHER_INCOME").id)
    refund = c.transactions.record_refund("2026-10-12", accounts["cib"].id, "100", food)
    for txn in (income, refund):
        with pytest.raises(ValidationError):
            c.budgets.set_left_out(txn.id, True)
    assert not c.budgets.left_out_ids()


def test_leaving_out_undoes(c, setup):
    accounts, _ = setup
    laptop = _laptop_year(c, accounts)
    c.budgets.set_left_out(laptop.id, True)
    c.undo.replay()
    assert not c.budgets.is_left_out(laptop.id)


# --------------------------------------------------------------------------- the journal: a replica's switch
from test_journal_finance import devices  # noqa: E402,F401
from test_journal_area_more import act, on_home  # noqa: E402
from test_journal_area_plans import account, category  # noqa: E402


def test_the_switch_travels_from_a_replica_to_the_home(devices):  # noqa: F811
    hd, pc = devices
    laptop = on_home(hd, lambda s: s.transactions.record_outflow(
        "2026-09-02", account(hd, "Bank").id, Decimal("90"), category(hd).id))
    pc.sync_with(hd.home)
    mine = pc.c.db.scalar("SELECT id FROM transactions WHERE ref=?", (laptop.ref,))
    act(hd, pc, lambda s: s.budgets.set_left_out(mine, True))
    assert pc.c.budgets.is_left_out(mine) and hd.c.budgets.is_left_out(laptop.id)
    act(hd, pc, lambda s: s.budgets.set_left_out(mine, False))
    assert not pc.c.budgets.left_out_ids() and not hd.c.budgets.left_out_ids()


# --------------------------------------------------------------------------- screens (PC and phone, EN and AR)
from fastapi.testclient import TestClient  # noqa: E402

from lightning.ui.web import create_app  # noqa: E402
from tests.screens import visible_text  # noqa: E402


def _client(c, phone=False, locale="en"):
    app = create_app(c)

    @app.get("/test-history")
    async def history():  # the undo history lives on the server's own connection
        return c.undo.available()
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app, follow_redirects=False)
    if locale != "en":
        assert client.post("/settings/locale", data={"locale": locale}).status_code == 303
    return client


def _text(c, url, phone=False, locale="en"):
    return visible_text(_client(c, phone, locale).get(url).text)


def _switch(page):
    return page.split('id="popup-left-out"')[1].split(">")[0]


def _edit_form(c, txn, account, food, **changes):
    return dict(kind="out", date="2026-10-12", amount="9000", category_id=str(food), account_id=str(account.id),
                notes="", counterparty="", owner_id="", to_account_id="", revision=c.transactions.revision(txn.id),
                return_to=f"/accounts/{account.id}", early_checked="2026-10-12", left_out_shown="1") | changes


@pytest.mark.parametrize("phone", [False, True])
def test_the_switch_on_edit_round_trips_with_undo(c, setup, phone):
    accounts, _ = setup
    food, _ = _ids(c)
    laptop = _laptop_year(c, accounts)
    with _client(c, phone) as client:  # one server thread: undo history is per connection
        page = client.get(f"/transactions/{laptop.id}/edit-popup").text
        assert "Leave out of estimates" in visible_text(page) and "checked" not in _switch(page)
        saved = client.post(f"/transactions/{laptop.id}/edit-popup",
                            data=_edit_form(c, laptop, accounts["cib"], food, left_out="1"))
        assert saved.status_code == 303 and c.budgets.is_left_out(laptop.id)
        assert _average(c, food, "2026-12") == Decimal("1000.00")
        assert "checked" in _switch(client.get(f"/transactions/{laptop.id}/edit-popup").text)
        group = client.get("/test-history").json()["undo"]["id"]
        assert client.post("/history/undo", data={"group_id": group, "back": "/"}).status_code == 303
        assert not c.budgets.is_left_out(laptop.id) and _average(c, food, "2026-12") == Decimal("4000.00")
        group = client.get("/test-history").json()["redo"]["id"]
        assert client.post("/history/redo", data={"group_id": group, "back": "/"}).status_code == 303
        assert c.budgets.is_left_out(laptop.id)
        # Switched off, it counts again; a form without the switch never changes the choice.
        client.post(f"/transactions/{laptop.id}/edit-popup", data=_edit_form(c, laptop, accounts["cib"], food))
        assert not c.budgets.is_left_out(laptop.id)
        c.budgets.set_left_out(laptop.id, True)
        form = _edit_form(c, laptop, accounts["cib"], food, notes="New bag")
        del form["left_out_shown"]
        client.post(f"/transactions/{laptop.id}/edit-popup", data=form)
        assert c.budgets.is_left_out(laptop.id)


def test_the_phone_adds_it_left_out_under_more(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    client = _client(c, phone=True)
    page = client.get(f"/accounts/{accounts['cib'].id}/transaction/new").text
    more = page.split('class="phone-more"')[1].split("</details>")[0]
    assert "Leave out of estimates" in visible_text(more)
    saved = client.post(f"/accounts/{accounts['cib'].id}/transaction/new", data=dict(
        kind="out", date="2026-10-12", amount="9000", category_id=str(food), counterparty="", owner_id="",
        to_account_id="", notes="", early_checked="2026-10-12", submission="a" * 32, left_out_shown="1", left_out="1"))
    assert saved.status_code == 303
    laptop = c.db.scalar("SELECT max(id) FROM transactions")
    assert c.budgets.is_left_out(laptop)
    assert _spent(c, food, "2026-10") == Decimal("9000")  # Spent still counts it


def test_the_pc_add_dialog_stays_as_it_was(c, setup):
    accounts, _ = setup
    assert "Leave out of estimates" not in _text(c, f"/accounts/{accounts['cib'].id}/transaction/new")


@pytest.mark.parametrize("phone", [False, True])
def test_the_switch_reads_arabic(c, setup, phone):
    accounts, _ = setup
    laptop = _laptop_year(c, accounts)
    page = _text(c, f"/transactions/{laptop.id}/edit-popup", phone, "ar")
    assert "استبعده من التقديرات" in page and "Leave out of estimates" not in page
