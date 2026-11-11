"""BT-2E item 6 (owner 2026-11-02): a transaction dated before its account opened is allowed, but Save asks once."""
import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from tests.screens import said


@pytest.fixture
def opened(c, setup):
    bank = c.account_flows.open_account("New bank", "BANK", "2026-09-01", "1000")
    return TestClient(create_app(c), base_url="http://127.0.0.1"), bank, setup[1]["EXP.PERSONAL.FOOD"]


def _count(c, bank):
    return c.db.scalar("SELECT COUNT(DISTINCT t.id) FROM transactions t JOIN ledger_entries e ON e.transaction_id=t.id "
                       "WHERE t.status='POSTED' AND t.type='OUT' AND e.account_id=?", (bank.id,))


def test_the_register_row_asks_once_then_keeps_the_date(c, opened):
    client, bank, food = opened
    row = dict(date="2026-07-10", amount="-10", category="Food & Groceries", counterparty="", notes="")
    first = client.post(f"/accounts/{bank.id}/register", data=row)
    assert first.status_code == 400 and said("before this account opened on 2026-09-01") in first.text and _count(c, bank) == 0
    again = client.post(f"/accounts/{bank.id}/register", data=row | {"early_checked": "2026-07-10"}, follow_redirects=False)
    assert again.status_code == 303 and _count(c, bank) == 1
    ordinary = client.post(f"/accounts/{bank.id}/register", data=row | {"date": "2026-09-05"}, follow_redirects=False)
    assert ordinary.status_code == 303 and _count(c, bank) == 2        # no ask for a date after the opening


def test_the_add_popup_asks_once_and_its_form_carries_the_answer_back(c, opened):
    client, bank, food = opened
    form = dict(kind="out", date="2026-07-10", amount="10", category_id=str(food.id), category_choice=str(food.id),
                counterparty="", owner_id="", to_account_id="", notes="")
    first = client.post(f"/accounts/{bank.id}/transaction/new", data=form)
    assert first.status_code == 400 and "before this account opened" in first.text
    assert 'name="early_checked" value="2026-07-10"' in first.text         # pressing Save again sends it back
    again = client.post(f"/accounts/{bank.id}/transaction/new", data=form | {"early_checked": "2026-07-10"},
                        follow_redirects=False)
    assert again.status_code == 303 and _count(c, bank) == 1


def test_quick_add_keeps_its_old_behaviour(c, opened):
    client, bank, food = opened
    reply = client.post("/accounts/quick-add", data=dict(account_id=str(bank.id), kind="out", date="2026-07-10",
                                                         amount="10", category_id=str(food.id)))
    assert reply.status_code == 200 and reply.json()["ok"] and _count(c, bank) == 1


def test_the_ask_is_in_arabic_when_the_app_is_in_arabic():
    from lightning.ui.i18n import translate
    text = translate("2026-07-10 is before this account opened on 2026-09-01. Check the date, then press Save again to keep it.", "ar")
    assert "before this account" not in text and "2026-09-01" in text and "حفظ" in text
