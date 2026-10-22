"""The screens that use the newer commands: saving a rule, a transaction from the account form, a saved view."""
from test_journal_area_plans import account, category, same
from test_journal_finance import devices  # noqa: F401
from test_journal_screens import screens  # noqa: F401


def rule_form(category_id, **changes):
    return {"match": "all", "counterparty_op": "contains", "counterparty": "Cafe", "notes": "", "amount_op": "", "amount": "",
            "amount_to": "", "account_id": "", "direction": "", "category_id": str(category_id), "tag": ""} | changes


def test_saving_a_rule_on_the_screens(screens):
    (hd, pc), (home, replica) = screens
    food = category(pc).id
    response = replica.post("/rules", data=rule_form(food), headers={"referer": "http://testserver/rules"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert not pc.c.db.scalar("SELECT COUNT(*) FROM rules")  # Waiting for the home.
    pc.sync_with(hd.home)
    assert pc.c.db.scalar("SELECT COUNT(*) FROM rules") == 1
    same(hd, pc)
    # The home saves at once and lands on the new rule's page.
    response = home.post("/rules", data=rule_form(food, counterparty="Souq"))
    assert response.status_code == 303 and response.headers["location"].startswith("/rules/2/past")
    pc.sync_with(hd.home)
    assert pc.c.db.scalar("SELECT COUNT(*) FROM rules") == 2
    assert "Souq" in replica.get("/rules").text
    # Editing and deleting go through the same commands.
    first = pc.c.db.scalar("SELECT MIN(id) FROM rules")
    assert replica.post(f"/rules/{first}/edit", data=rule_form(food, counterparty="Cafe Nile")).status_code == 303
    pc.sync_with(hd.home)
    assert "Cafe Nile" in replica.get("/rules").text and pc.c.db.scalar("SELECT COUNT(*) FROM rules") == 2
    assert replica.post(f"/rules/{first}/delete").status_code == 303
    pc.sync_with(hd.home)
    assert pc.c.db.scalar("SELECT COUNT(*) FROM rules") == 1
    same(hd, pc)
    # An account condition travels by account code, not the replica's local id.
    bank = account(pc, "Bank")
    response = replica.post("/rules", data=rule_form(food, account_id=str(bank.id)))
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    rule = next(rule for rule in pc.c.rules.list() if any(condition.field == "account" for condition in rule.conditions))
    assert next(condition.value for condition in rule.conditions if condition.field == "account") == bank.code


def test_a_transaction_from_the_account_form_and_a_saved_view_on_the_screens(screens):
    (hd, pc), (home, replica) = screens
    bank, food = account(pc, "Bank").id, category(pc).id
    form = {"kind": "out", "date": "2026-09-05", "amount": "42", "category_id": str(food), "counterparty": "Spinneys",
            "owner_id": "", "to_account_id": "", "notes": ""}
    response = replica.post(f"/accounts/{bank}/transaction/new", data=form, headers={"referer": f"http://testserver/accounts/{bank}"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    assert next(r for r in pc.balances() if r["name"] == "Bank")["balance"] == 958
    response = home.post(f"/accounts/{account(hd, 'Bank').id}/transaction/new", data=form | {"kind": "in", "amount": "8"})
    assert response.status_code == 303 and "Saved" in response.headers["location"]
    pc.sync_with(hd.home)
    assert next(r for r in pc.balances() if r["name"] == "Bank")["balance"] == 966
    response = replica.post("/transactions/views", data={"name": "Food", "preset": "all_time", "category_id": str(food)})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    pc.sync_with(hd.home)
    assert [v["name"] for v in pc.c.saved_views.list(None)] == ["Food"]
    same(hd, pc)
