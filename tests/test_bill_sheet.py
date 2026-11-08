"""NF-3AZ4: a bill that falls due opens one sheet: already paid, or record it, with the reserve and budget effect shown
first and never a second expense when a payment already matches."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from test_reserve_bills import prepared


def _sheet(client, bill, due="2026-12-20"):
    return client.get(f"/plan/items/{bill}/pay?due={due}&back=/plan")


def _post(client, bill, **data):
    return client.post(f"/plan/items/{bill}/pay", data={"due": "2026-12-20", "back": "/plan", **data}, follow_redirects=False)


def test_the_sheet_shows_the_reserve_and_budget_effect_before_recording(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-20")
    bank, category, bill, reserve = prepared(c, setup)
    c.budgets.set_budget(category, "2026-12", "3000", schedule=c.schedules.view())
    page = _sheet(TestClient(create_app(c)), bill)
    assert "If you record it" in page.text and "Cover fund" in page.text
    assert "800 → 0" in page.text
    assert "Left in the budget before and after this payment" in page.text
    assert c.db.scalar("SELECT count(*) FROM transactions WHERE type='OUT'") == 0     # looking records nothing


def test_a_matching_payment_blocks_a_second_expense_until_the_user_says_so(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-20")
    bank, category, bill, reserve = prepared(c, setup)
    existing = c.transactions.record_outflow("2026-12-20", bank, "1000", category, counterparty="Insurer")
    client = TestClient(create_app(c))
    page = _sheet(client, bill)
    assert "Use this" in page.text and "This is a different payment" in page.text
    count = c.db.scalar("SELECT count(*) FROM transactions")
    refused = _post(client, bill, outcome="record", date_paid="2026-12-20", amount="1000", account_id=str(bank))
    assert "already%20recorded" in refused.headers["location"] and c.db.scalar("SELECT count(*) FROM transactions") == count
    linked = _post(client, bill, outcome="link", transaction_id=str(existing.id))
    assert linked.status_code == 303 and c.db.scalar("SELECT count(*) FROM transactions") == count


def test_without_a_match_recording_posts_once_and_uses_the_reserve(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-20")
    bank, category, bill, reserve = prepared(c, setup)
    client = TestClient(create_app(c))
    assert "This is a different payment" not in _sheet(client, bill).text
    done = _post(client, bill, outcome="record", date_paid="2026-12-20", amount="1000", account_id=str(bank))
    assert done.status_code == 303 and c.db.scalar("SELECT count(*) FROM transactions WHERE type='OUT'") == 1
    assert c.reserves.get(reserve)["effective_allocated"] == 0
