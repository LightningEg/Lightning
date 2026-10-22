"""Composite app workflows are one command and retain references across device-local ids."""
from datetime import date
from types import SimpleNamespace

from test_journal_finance import devices  # noqa: F401
from test_journal_screens import screens  # noqa: F401
from lightning.sync.journal.proxy import JournalServices
from lightning.workflows.activity import ActivityReview
from lightning.planning.loan_actions import preview_early_payment
from lightning.sync.journal.history import attach_home_history
from lightning.sync.journal.areas.workflows import JournalWorkflowService


def test_budget_settings_fingerprint_uses_category_codes_not_local_ids():
    def service(first_id, second_id, reverse=False):
        rows = [
            {"category_id": first_id, "month": "2026-10", "one_off": 0, "amount_e6": 100,
             "average_months": None, "income_percent_e6": None},
            {"category_id": second_id, "month": "2026-10", "one_off": 0, "amount_e6": 200,
             "average_months": None, "income_percent_e6": None},
        ]
        carry = [{"category_id": first_id, "month": "2026-10", "enabled": 1},
                 {"category_id": second_id, "month": "2026-10", "enabled": 0}]
        if reverse:
            rows.reverse()
            carry.reverse()

        class Database:
            def all(self, sql):
                return rows if "FROM budgets" in sql else carry

        class Settings:
            def get(self, key):
                return None

        categories = SimpleNamespace(tree=lambda: [SimpleNamespace(id=first_id, code="EXP.A"),
                                                    SimpleNamespace(id=second_id, code="EXP.B")])
        return JournalWorkflowService(SimpleNamespace(db=Database(), settings=Settings(), categories=categories))

    assert service(7, 8).budget_settings_fingerprint() == service(107, 108, reverse=True).budget_settings_fingerprint()


def _sync(home, replica):
    replica.sync_with(home.home)
    replica.sync_with(home.home)


def test_activity_review_applies_as_one_journal_command(screens):
    (home, replica), (home_client, replica_client) = screens
    bank_h = next(a for a in home.c.accounts.list() if a.name == "Bank")
    food_h = home.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    txn_id = JournalServices(home).transactions.record_outflow(date.today().isoformat(), bank_h.id, "40", food_h,
                                                                counterparty="Cafe", notes="lunch")
    txn_id = txn_id.id
    _sync(home, replica)
    txn_uuid = home.adapter.uid("transactions", txn_id)
    local_txn = replica.adapter.local("transactions", txn_uuid)
    txn = replica.c.transactions.get(local_txn)
    current = txn.lines[0].category_id
    next_category = next(item for item in replica.c.categories.tree(active_only=True)
                         if item.movement.value == "OUTFLOW" and item.depth == 2 and item.id != current
                         and not item.is_system)
    fingerprint = ActivityReview(replica.c).fingerprint(local_txn)
    response = replica_client.post(f"/activity/{local_txn}/apply", data={
        "fingerprint": fingerprint, "category_choice": str(next_category.id), "payment": "",
        "reserve_id": "", "reserve_amount": ""}, headers={"referer": f"http://testserver/activity/{local_txn}"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    _sync(home, replica)
    assert home.c.transactions.get(txn_id).lines[0].category_id == next(
        item.id for item in home.c.categories.tree() if item.code == next_category.code)
    assert home.store.fingerprint() == replica.store.fingerprint()


def test_salary_setup_reaches_one_recurring_plan_command(screens):
    (home, replica), (_, replica_client) = screens
    bank = next(a for a in replica.c.accounts.list() if a.name == "Bank")
    response = replica_client.post("/setup/salary", data={"account_id": str(bank.id), "amount": "50000",
                                                           "payday": "25"},
                                  headers={"referer": "http://testserver/setup/salary"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    _sync(home, replica)
    home_salary = next(item for item in home.c.planning.items() if item.name == "Salary")
    replica_salary = next(item for item in replica.c.planning.items() if item.name == "Salary")
    assert home_salary.amount == replica_salary.amount
    assert home.store.fingerprint() == replica.store.fingerprint()


def test_installment_purchase_and_early_payment_are_single_service_commands(screens):
    (home, replica), (_, replica_client) = screens
    bank = next(a for a in replica.c.accounts.list() if a.name == "Bank")
    today = date.today().isoformat()
    response = replica_client.post("/plan/purchases/new", data={
        "intent": "save", "name": "Laptop", "price": "1200", "fee": "0", "months": "3",
        "first_date": today, "account_id": str(bank.id)}, headers={"referer": "http://testserver/plan/purchases/new"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    _sync(home, replica)
    purchase = next(item for item in replica.c.planning.items(active_only=False) if item.name == "Laptop")
    preview = preview_early_payment(replica.c.planning, purchase.id, "100", "0", today)
    response = replica_client.post(f"/plan/items/{purchase.id}/early-payment", data={
        "intent": "record", "principal": "100", "fee": "0", "date_paid": today,
        "account_id": str(bank.id), "expected_remaining": str(preview["remaining_before"])},
        headers={"referer": f"http://testserver/plan/items/{purchase.id}/early-payment"})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    _sync(home, replica)
    assert home.c.db.scalar("SELECT COUNT(*) FROM loan_extra_payments") == 1
    assert replica.c.db.scalar("SELECT COUNT(*) FROM loan_extra_payments") == 1
    assert home.store.fingerprint() == replica.store.fingerprint()


def test_home_command_undo_records_only_confirmed_financial_effects(devices):
    home, replica = devices
    history = attach_home_history(home.c, home.adapter)
    assert history is home.c.undo and home.c.db.undo is None
    home.command("accounts.open", name="Travel", account_type="CASH", opening_date="2026-10-01",
                 opening_balance="0", institution="", currency=None, last4=None, notes="",
                 opening_balance_date=None, owner_id=None)
    assert any(item.name == "Travel" for item in home.c.accounts.list())
    group = history.available()["undo"]
    assert group and group["label"] == "Open account"
    assert home.c.db.scalar("SELECT COUNT(*) FROM undo_records WHERE table_name LIKE 'journal_%'") == 0
    assert home.c.db.scalar("SELECT COUNT(*) FROM undo_records WHERE group_id=?", (group["id"],)) > 0

    home.command("undo.replay", redo=False, expected_id=group["id"],
                 expected_fingerprint=home.store.fingerprint())
    assert not any(item.name == "Travel" for item in home.c.accounts.list())
    assert history.available()["redo"]["id"] == group["id"]
    assert home.store.fingerprint() == home.adapter.fingerprint()

    replica.sync_with(home.home)
    assert not any(item.name == "Travel" for item in replica.c.accounts.list())
    assert home.store.fingerprint() == replica.store.fingerprint()
