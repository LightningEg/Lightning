"""Real route writes, retry markers and related links roll back together on matching failure."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.sync.journal.proxy import JournalServices
from lightning.ui.web import create_app
from test_journal_finance import devices
from test_journal_screens import Screen


def _snapshot(c):
    names = [r["name"] for r in c.db.all("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {name: sorted((tuple(r) for r in c.db.all('SELECT * FROM "' + name.replace('"', '""') + '"')), key=repr)
            for name in names}


def _fail_matching(c, monkeypatch):
    original = c.planning.match_payments
    calls = []
    def fail(day):
        calls.append(original(day))
        raise ValidationError("Injected settlement failure")
    monkeypatch.setattr(c.planning, "match_payments", fail)
    return original, calls


@pytest.mark.parametrize("bulk", [False, True])
def test_category_saves_and_bill_links_roll_back_and_a_redirect_does_not_retry_matching(c, setup, monkeypatch, bulk):
    accounts, cats = setup
    bank, food, software = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id, cats["EXP.WORK.SOFTWARE"].id
    first = c.transactions.record_outflow("2026-09-22", bank, "400", food)
    second = c.transactions.record_outflow("2026-09-22", bank, "250", food)
    c.planning.create(kind="BILL", name="Subscription", amount="400", frequency="ONCE", start_date="2026-09-22",
                      account_id=bank, category_id=software)
    before = _snapshot(c)
    original, calls = _fail_matching(c, monkeypatch)
    app = create_app(c)
    @app.middleware("http")
    async def phone(request, call_next):
        request.state.phone = True
        return await call_next(request)
    client = TestClient(app)
    path = "/transactions/bulk-category" if bulk else f"/transactions/{first.id}/category"
    payload = {"category_id": str(software), "txn_ids": [str(first.id), str(second.id)], "back": "/transactions"}
    response = client.post(path, data=payload, follow_redirects=False)
    assert response.status_code == (303 if bulk else 400)
    assert calls == [1]  # including redirects: no second attempt outside the route's transaction
    assert _snapshot(c) == before
    monkeypatch.setattr(c.planning, "match_payments", original)
    assert client.post(path, data=payload, follow_redirects=False).status_code == 303
    assert c.planning.linked_transaction_ids() == {first.id}
    assert c.transactions.get(first.id).lines[0].category_id == software
    assert c.reporting.account_balance(bank) == Decimal("49350")


def test_plan_creation_and_its_paid_history_roll_back_before_retry(c, setup, monkeypatch):
    accounts, cats = setup
    bank, food = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    c.transactions.record_outflow("2026-09-22", bank, "400", food)
    before = _snapshot(c)
    original, calls = _fail_matching(c, monkeypatch)
    payload = dict(kind="BILL", name="Monthly box", amount="400", frequency="MONTHLY", interval_count="1",
                   start_date="2026-09-22", account_id=bank, category_id=food, counterparty="", past_due="paid")
    client = TestClient(create_app(c))
    response = client.post("/plan/items", data=payload, follow_redirects=False)
    assert response.status_code == 400 and calls == [1]
    assert _snapshot(c) == before
    monkeypatch.setattr(c.planning, "match_payments", original)
    assert client.post("/plan/items", data=payload, follow_redirects=False).status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM planned_items") == 1
    assert c.db.scalar("SELECT COUNT(*) FROM planned_payments WHERE status='PAID'") == 1


def test_conversion_receipt_and_fx_save_roll_back_and_resending_the_token_posts_once(c, setup, monkeypatch):
    bank = setup[0]["cib"].id
    c.currencies.register("USD")
    usd = c.account_flows.open_account("Dollars", "BANK", "2026-09-01", "0", currency="USD")
    c.fx.save("USD", "2026-09-22", "50")
    before = _snapshot(c)
    original, calls = _fail_matching(c, monkeypatch)
    payload = dict(date="2026-09-22", from_account_id=bank, to_account_id=usd.id, sent="5000", received="100",
                   fee="0", notes="Dummy conversion", submission="c" * 32)
    client = TestClient(create_app(c))
    response = client.post(f"/accounts/{bank}/convert", data=payload, follow_redirects=False)
    assert response.status_code == 400 and calls == [0]
    assert _snapshot(c) == before
    monkeypatch.setattr(c.planning, "match_payments", original)
    for _ in range(2):
        assert client.post(f"/accounts/{bank}/convert", data=payload, follow_redirects=False).status_code == 303
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='CNV'") == 1
    assert c.reporting.account_balance(bank) == Decimal("45000")
    assert c.reporting.account_balance(usd.id) == Decimal("100")


def test_currency_rollback_restores_the_live_service_graph_as_well_as_the_database(c, monkeypatch):
    c.currencies.register("USD")
    before = _snapshot(c)
    original, calls = _fail_matching(c, monkeypatch)
    client = TestClient(create_app(c))
    assert client.post("/settings/currency", data={"base_currency": "USD"}, follow_redirects=False).status_code == 303
    assert calls == [0] and _snapshot(c) == before
    assert c.base_currency == "EGP"
    assert all(service.base_currency == "EGP" for service in (c.assets, c.accounts, c.transactions, c.reporting))
    assert c.fx.profile_currency == "EGP"
    monkeypatch.setattr(c.planning, "match_payments", original)
    assert client.post("/settings/currency", data={"base_currency": "USD"}, follow_redirects=False).status_code == 303
    assert c.base_currency == c.transactions.base_currency == "USD"


def test_a_late_related_read_failure_rolls_back_the_entry_and_retry_marker(c, setup, monkeypatch):
    accounts, cats = setup
    before = _snapshot(c)
    original = c.reserves.auto_link_transaction
    def fail(transaction_id):
        original(transaction_id)
        raise ValidationError("Injected reserve suggestion failure")
    monkeypatch.setattr(c.reserves, "auto_link_transaction", fail)
    payload = dict(account_id=accounts["cib"].id, kind="out", date="2026-09-22", amount="400",
                   category_id=cats["EXP.PERSONAL.FOOD"].id, submission="d" * 32)
    client = TestClient(create_app(c))
    assert client.post("/accounts/quick-add", data=payload).status_code == 422
    assert _snapshot(c) == before
    monkeypatch.setattr(c.reserves, "auto_link_transaction", original)
    result = client.post("/accounts/quick-add", data=payload)
    assert result.status_code == 200 and not result.json()["repeat"]
    assert c.reporting.account_balance(accounts["cib"].id) == Decimal("49600")


def test_home_and_replica_routes_preserve_command_settlement_and_pending_writes(devices, monkeypatch):
    home, replica = devices
    bank = next(a.id for a in home.c.accounts.list() if a.name == "Bank")
    food = home.c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    health = home.c.categories.get_by_code("EXP.PERSONAL.HEALTH").id
    txn = JournalServices(home).transactions.record_in_account(bank, "2026-09-01", "-30", category_id=food)
    replica.sync_with(home.home)
    original = home.c.planning.match_payments
    calls = []
    def traced(day):
        calls.append(day)
        return original(day)
    monkeypatch.setattr(home.c.planning, "match_payments", traced)
    assert Screen(home).post("/transactions/bulk-category", data={"txn_ids": [txn.id], "category_id": health}).status_code == 303
    assert len(calls) == 1  # command-owned matching only
    replica.sync_with(home.home)
    local = replica.adapter.local("transactions", home.adapter.uid("transactions", txn.id))
    response = Screen(replica).post("/transactions/bulk-category", data={"txn_ids": [local], "category_id": food})
    assert response.status_code == 303 and "Saved+on+this+device" in response.headers["location"]
    assert replica.c.transactions.get(local).lines[0].category_id == health
    replica.sync_with(home.home)
    assert replica.c.transactions.get(local).lines[0].category_id == food
    assert home.store.fingerprint() == replica.store.fingerprint()


def test_new_cost_method_route_rolls_back_with_failed_matching(c, setup, monkeypatch):
    accounts, _ = setup
    broker = accounts["thndr"]
    before = _snapshot(c)
    original, calls = _fail_matching(c, monkeypatch)
    client = TestClient(create_app(c))
    response = client.post(f"/accounts/{broker.id}/cost-method", data={"method": "fifo"}, follow_redirects=False)
    assert response.status_code == 303
    assert "Injected" in response.headers["location"]
    assert calls and _snapshot(c) == before
    monkeypatch.setattr(c.planning, "match_payments", original)
    assert client.post(f"/accounts/{broker.id}/cost-method", data={"method": "fifo"},
                       follow_redirects=False).status_code == 303
    assert c.accounts.get(broker.id).cost_method == "fifo"
