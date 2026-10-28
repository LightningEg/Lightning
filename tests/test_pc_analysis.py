"""PC analysis and big actions (owner, 2026-10-28): Compare periods, Item analysis, Reports, one Import page with
batch undo, and Find and replace. Today is pinned to 2026-12-31 (conftest)."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from lightning.ui.routes.analysis import analyse, compare, preset_periods
from lightning.ui.routes.workbench import guess_account
from lightning.ui.web import create_app


def _spend(c):
    bank = c.account_flows.open_account("CIB", "BANK", "2026-01-01", "50000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.transactions.record_outflow("2026-11-10", bank.id, "300", food.id, counterparty="Carrefour")
    c.transactions.record_outflow("2026-12-10", bank.id, "500", food.id, counterparty="Carrefour")
    c.transactions.record_outflow("2026-12-12", bank.id, "100", food.id, counterparty="Spinneys")
    return bank, food


def test_month_preset_compares_the_same_days_of_last_month():
    a, b = preset_periods("month", date(2026, 12, 31))
    assert a == (date(2026, 12, 1), date(2026, 12, 31))
    assert b == (date(2026, 11, 1), date(2026, 11, 30))
    a, b = preset_periods("year", date(2026, 3, 15))
    assert a == (date(2026, 1, 1), date(2026, 3, 15)) and b == (date(2025, 1, 1), date(2025, 3, 15))


def test_compare_gives_each_payee_its_difference(c):
    _spend(c)
    rows = {r["name"]: r for r in compare(c, (date(2026, 12, 1), date(2026, 12, 31)), (date(2026, 11, 1), date(2026, 11, 30)), "payee")}
    assert rows["Carrefour"]["a"] == 500 and rows["Carrefour"]["b"] == 300 and rows["Carrefour"]["diff"] == 200
    assert rows["Spinneys"]["b"] == 0 and rows["Spinneys"]["pct"] is None


def test_item_analysis_totals_twelve_months_of_a_payee(c):
    _spend(c)
    data = analyse(c, "payee", "carrefour", date(2026, 12, 31))
    assert data["total"] == 800 and data["this_month"] == 500 and data["last_month"] == 300 and data["count"] == 2
    assert len(data["trend"]) == 12


def test_analysis_pages_open(c):
    _, food = _spend(c)
    client = TestClient(create_app(c))
    assert "Carrefour" in client.get("/spending/compare?by=payee").text
    assert client.get(f"/analysis/category/{food.id}").status_code == 200
    page = client.get("/analysis/payee?name=Carrefour")
    assert page.status_code == 200 and "Edit all these transactions" in page.text
    assert client.get("/reports").status_code == 200
    assert client.get("/spending/compare?format=csv").headers["content-type"].startswith("text/csv")


def test_a_statement_file_finds_its_account_by_last_four_digits(c):
    cib = c.account_flows.open_account("CIB", "BANK", "2026-01-01", "0")
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-01-01", "0")
    c.db.execute("UPDATE accounts SET last4='4821' WHERE id=?", (nbe.id,))
    accounts = c.accounts.list(active_only=True)
    assert guess_account("statement_4821_oct.csv", accounts) == nbe.id
    assert guess_account("cib-october.csv", accounts) == cib.id
    assert guess_account("unknown.csv", accounts) is None


def test_find_and_replace_renames_a_payee_on_every_match(c):
    _spend(c)
    client = TestClient(create_app(c))
    client.get("/import")
    response = client.post("/transactions/find-replace", data={"field": "counterparty", "find": "carrefour",
                                                               "replace": "Carrefour Maadi"}, follow_redirects=False)
    assert response.status_code in (302, 303)
    names = [r["counterparty"] for r in c.db.all("SELECT counterparty FROM transactions WHERE type='OUT'")]
    assert names.count("Carrefour Maadi") == 2 and "Spinneys" in names


def test_find_and_replace_stays_in_the_register_it_was_sent_from_and_matches_whole_words(c):
    bank, food = _spend(c)
    other = c.account_flows.open_account("NBE", "BANK", "2026-01-01", "5000")
    c.transactions.record_outflow("2026-12-11", bank.id, "50", food.id, counterparty="Khalil")
    c.transactions.record_outflow("2026-12-11", other.id, "70", food.id, counterparty="Carrefour")
    client = TestClient(create_app(c))
    client.get("/import")
    client.post("/transactions/find-replace", data={"field": "counterparty", "find": "carrefour", "replace": "Carrefour Maadi",
                                                     "account_id": str(bank.id), "date_from": "2026-12-01"})
    client.post("/transactions/find-replace", data={"field": "counterparty", "find": "ali", "replace": "Ali Baba"})
    names = sorted(r["counterparty"] for r in c.db.all("SELECT counterparty FROM transactions WHERE type='OUT'"))
    assert names == ["Carrefour", "Carrefour", "Carrefour Maadi", "Khalil", "Spinneys"]


def test_compare_export_keeps_negative_differences_as_numbers():
    from lightning.ui.routes.analysis import _csv
    body = _csv("x.csv", ("Name", "Change"), [("=cmd", "-200.00")]).body.decode("utf-8-sig")
    assert body.splitlines()[1] == "'=cmd,-200.00"
