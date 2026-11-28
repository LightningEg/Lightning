"""NF-12G7: one ordinary Money out sheet on PC and phone, with or without shares."""
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.screens import Screen, visible_text
from tests.test_journal_finance import devices  # noqa: F401
from tests.test_journal_screens import screens  # noqa: F401


def _sheet_fields(client, path):
    page = client.get(path)
    assert "Split with others" in page.text
    return next(form.fields for form in Screen(page).forms if form.action == path)


@pytest.mark.parametrize("phone", [False, True], ids=["PC", "phone"])
def test_dinner_validation_save_replay_and_repayment(c, setup, phone):
    accounts, _ = setup
    account = accounts["cib"]
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    app = create_app(c)
    if phone:
        mount_phone(app)
    client = TestClient(app, follow_redirects=False)
    path = f"/accounts/{account.id}/transaction/new"
    sara, omar = [c.counterparties.ensure_person(name) for name in ("Sara", "Omar")]
    original = _sheet_fields(client, path) | {
        "kind": "out", "amount": "1200", "date": "2026-10-05", "category_id": str(food),
        "notes": "Dinner", "share_person": ["Sara", "Omar"], "share_amount": ["400", "900"],
    }
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")
    cash_before = c.reporting.account_balance(account.id)
    c.budgets.save_month("2026-10", amounts={food: "2000"}, schedule=c.schedules.view())

    def spent():
        lines = c.budgets.month_view("2026-10", schedule=c.schedules.view()).sections
        return next(line.actual for section in lines for line in section.lines if line.category_id == food)

    spending_before = spent()
    refused = client.post(path, data=original)
    assert refused.status_code == 400
    for value in ("Sara", "Omar", "400", "900", "1200", "Dinner", original["submission"]):
        assert f'value="{value}"' in refused.text
    assert "data-people-split open" in refused.text
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before
    dinner = original | {"share_amount": ["400", "400"]}
    saved = client.post(path, data=dinner)
    assert saved.status_code == 303
    assert "Saved. Your share: 400.00 EGP. Owed to you: 800.00 EGP." in parse_qs(urlsplit(saved.headers["location"]).query)["msg"][0]
    assert client.post(path, data=dinner).status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before + 1
    assert c.reporting.account_balance(account.id) == cash_before - 1200
    assert spent() == spending_before + 400
    assert c.people_money.balance(sara) == c.people_money.balance(omar) == 400

    repay = client.post(f"/counterparties/{sara}/repay",
                        data={"day": "2026-10-06", "amount": "400", "account_id": str(account.id)})
    assert repay.status_code == 303
    assert c.people_money.balance(sara) == 0 and c.people_money.balance(omar) == 400
    assert c.reporting.account_balance(account.id) == cash_before - 800
    assert spent() == spending_before + 400

    ordinary = _sheet_fields(client, path) | {
        "kind": "out", "amount": "50", "category_id": str(food), "date": "2026-10-07",
    }
    assert client.post(path, data=ordinary).status_code == 303
    assert c.reporting.account_balance(account.id) == cash_before - 850
    assert spent() == spending_before + 450
    assert c.people_money.balance(omar) == 400


def test_the_replica_uses_the_split_journal_command_once(screens):
    from tests.test_journal_area_plans import account, same

    (hd, pc), (home, replica) = screens
    for name in ("Sara", "Omar"):
        assert home.post("/counterparties", data={"name": name, "counterparty_action": "create",
                                                 "kind": "PERSON"}).status_code == 303
    pc.sync_with(hd.home)
    bank = account(pc, "Bank")
    food = pc.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    path = f"/accounts/{bank.id}/transaction/new"
    form = _sheet_fields(replica, path) | {
        "kind": "out", "amount": "900", "date": "2026-09-05", "category_id": str(food),
        "share_person": ["Sara", "Omar"], "share_amount": ["400", "400"],
    }
    for _ in range(2):
        response = replica.post(path, data=form, headers={"referer": f"http://testserver{path}"})
        assert response.status_code == 303, visible_text(response.text).split("Record one account activity.", 1)[-1][:500]
    assert [command["name"] for command in pc.pending_commands()] == ["people_money.split"]
    pc.sync_with(hd.home)
    same(hd, pc)
    for name in ("Sara", "Omar"):
        assert pc.c.people_money.balance(pc.c.counterparties.resolve(name)["id"]) == 400
