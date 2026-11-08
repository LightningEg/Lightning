"""IV-3AY14: an account on the phone: balance, the bank question, the month's rows."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import account as screen
from lightning.ui.web import create_app


@pytest.fixture()
def sample(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-20")
    c = build(tmp_path / "a.db")
    load_mohab_2026(c)
    yield c
    c.db.close()


def _phone(c):
    app = create_app(c)
    mount_phone(app)

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(phone)


def _bank(c):
    return next(a for a in c.accounts.list() if a.account_type.value == "BANK")


def test_the_screen_reads_the_bank_balance_and_the_months_rows(sample):
    bank = _bank(sample)
    page = screen.build(sample, bank.id, date(2026, 10, 20))
    assert page.name == bank.label and page.check_today and page.checked_through == ""
    assert page.balance == sample.reconciliation.balance(bank.id, "2026-10-20")
    assert page.rows and page.month == "2026-10" and page.next_month == ""
    assert screen.build(sample, bank.id, date(2026, 10, 20), "2026-09").next_month == "2026-10"


def test_yes_checks_the_account_and_the_question_goes_away(sample):
    bank = _bank(sample)
    phone = _phone(sample)
    html = phone.get(f"/accounts/{bank.id}").text
    assert 'class="phone-hero' in html and f'action="/accounts/{bank.id}/check"' in html
    assert f'href="/accounts/{bank.id}/reconcile"' in html          # Fix it
    token = re.search(r'name="__session" value="([^"]*)"', html).group(1)
    assert phone.post(f"/accounts/{bank.id}/check", data={"__session": token}, follow_redirects=False).status_code == 303
    assert sample.reconciliation.checked_through(bank.id) == "2026-10-20"
    after = phone.get(f"/accounts/{bank.id}").text
    assert "check-heading" not in after and "2026-10-20" in after


def test_other_kinds_and_filtered_urls_keep_the_older_route(sample):
    phone = _phone(sample)
    bank = _bank(sample)
    assert 'id="balance-heading"' not in phone.get(f"/accounts/{bank.id}?q=salary").text
    other = next(a for a in sample.accounts.list() if a.account_type.value not in ("BANK", "CASH"))
    assert 'id="balance-heading"' not in phone.get(f"/accounts/{other.id}").text
