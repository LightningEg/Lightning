"""2E (Audit 1, section 1): the write paths refuse input the formulas cannot hold."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def _client(c):
    return TestClient(create_app(c), base_url="http://127.0.0.1")


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD")


# -- 2E1: a split respects the account's decimals ----------------------------------------------------------
def test_a_split_amount_with_three_decimals_is_refused(c, setup):
    accounts, _ = setup
    food = _food(c)
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    txn = c.transactions.record_outflow("2026-09-20", accounts["cib"].id, "1000", food.id)
    with pytest.raises(ValidationError, match="at most 2 decimal places"):
        c.transactions.update_expense_split(txn.id, [(food.id, "333.334"), (transport.id, "666.666")])
    assert [line.quantity for line in c.transactions.get(txn.id).lines] == [Decimal("-1000")]


# -- 2E2: no money in or out on a gold account -------------------------------------------------------------
@pytest.mark.parametrize("kind", ["out", "in"])
def test_money_in_or_out_on_a_physical_asset_account_is_refused(c, setup, kind):
    accounts, cats = setup
    gold = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-09-01", "0")
    with pytest.raises(ValidationError, match="physical"):
        if kind == "out":
            c.transactions.record_outflow("2026-09-20", gold.id, "250", _food(c).id)
        else:
            c.transactions.record_inflow("2026-09-20", gold.id, "250", cats["EXP.WORK.SALARY"].id)


def test_the_register_does_not_offer_a_gold_account_for_money(c, setup):
    gold = c.account_flows.open_account("Gold at home", "PHYSICAL_ASSET", "2026-09-01", "0")
    everything = _client(c).get("/transactions").text
    assert ">Gold at home<" not in everything.split('id="quick-add"')[1].split("</tr>")[0]


# -- 2E4: an unknown owner is a refusal, not a 500 ---------------------------------------------------------
def test_account_popup_with_an_unknown_owner_is_refused_not_a_crash(c, setup):
    accounts, _ = setup
    response = _client(c).post(f"/accounts/{accounts['cib'].id}/transaction/new", data={
        "kind": "out", "date": "2026-09-20", "amount": "10", "category_id": str(_food(c).id), "owner_id": "99999"})
    assert response.status_code < 500
    assert "Choose an active" in response.text


# -- 2E5: the planner refuses zero and negative amounts ----------------------------------------------------
@pytest.mark.parametrize("amount", ["0", "-50"])
def test_planner_amount_of_zero_or_less_is_refused_not_a_crash(c, setup, amount):
    response = _client(c).post("/investments/planner", data={"amount": amount})
    assert response.status_code == 422
    assert "greater than zero" in response.text


# -- 2E3: cash does not go below zero ----------------------------------------------------------------------
def test_an_expense_larger_than_the_cash_is_refused(c, setup):
    accounts, _ = setup
    with pytest.raises(ValidationError, match="would leave CIB Current"):
        c.transactions.record_outflow("2026-09-20", accounts["cib"].id, "999999999999", _food(c).id)
    assert c.reporting.account_balance(accounts["cib"].id) == Decimal("50000")


def test_a_transfer_then_an_expense_cannot_leave_the_account_negative(c, setup):
    accounts, _ = setup
    c.transactions.record_transfer("2026-09-20", accounts["cib"].id, accounts["wallet"].id, "30000")
    with pytest.raises(ValidationError, match="would leave CIB Current"):
        c.transactions.record_outflow("2026-09-21", accounts["cib"].id, "25000", _food(c).id)
    with pytest.raises(ValidationError, match="would leave CIB Current"):
        c.transactions.record_transfer("2026-09-21", accounts["cib"].id, accounts["wallet"].id, "25000")
    c.transactions.record_outflow("2026-09-21", accounts["cib"].id, "20000", _food(c).id)  # exactly empty is fine


def test_a_back_dated_expense_cannot_break_a_later_balance(c, setup):
    accounts, _ = setup
    c.transactions.record_outflow("2026-09-20", accounts["cib"].id, "49000", _food(c).id)
    with pytest.raises(ValidationError, match="would leave"):
        c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "2000", _food(c).id)


def test_editing_an_expense_up_past_the_cash_is_refused_but_a_note_is_not(c, setup):
    accounts, _ = setup
    txn = c.transactions.record_outflow("2026-09-20", accounts["cib"].id, "49000", _food(c).id)
    with pytest.raises(ValidationError, match="would leave"):
        c.transactions.update_money(txn.id, "2026-09-20", accounts["cib"].id, "51000", _food(c).id)
    c.transactions.update_money(txn.id, "2026-09-20", accounts["cib"].id, "49000", _food(c).id, notes="kept")


def test_the_integrity_page_flags_a_cash_account_below_zero(c, setup):
    accounts, _ = setup
    names = {check.name: check for check in c.integrity.checks("2026-09-30")}
    assert names["No cash account is below zero"].status == "PASS"
    c.db.execute("UPDATE ledger_entries SET quantity_e6=-60000000000 WHERE account_id=? AND transaction_id IN "
                 "(SELECT id FROM transactions WHERE ref LIKE 'OPN%')", (accounts["cib"].id,))
    names = {check.name: check for check in c.integrity.checks("2026-09-30")}
    assert names["No cash account is below zero"].status == "ISSUE"


# -- 2E6: crafted input is refused, not a 500 ----------------------------------------------------------------
def test_a_crafted_category_direction_is_refused(c, setup):
    food = _food(c)
    with pytest.raises(ValidationError):
        c.categories.set_direction(food.id, "SIDEWAYS")
    row = _client(c).post(f"/categories/{food.id}/row", data={"direction": "SIDEWAYS"}, follow_redirects=False)
    assert row.status_code < 500
    assert c.categories.get(food.id).direction.value != "SIDEWAYS"


@pytest.mark.parametrize("value", [2**63, 2**64, 0, -1])
def test_a_transaction_id_outside_the_database_range_is_not_found(c, setup, value):
    from lightning.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        c.transactions.get(value)
    assert _client(c).get(f"/transactions/{value}").status_code == 404
