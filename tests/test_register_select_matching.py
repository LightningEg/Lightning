"""P7: a filtered PC register shows what the filter found and can select every match, not just this page."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


@pytest.fixture
def client(c):
    return TestClient(create_app(c))


def _matching(html):
    found = re.search(r"data-matching-ids='([^']*)'", html)
    return json.loads(found.group(1)) if found else None


def test_search_past_one_page_offers_select_all_matching(c, setup, client):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    made = [c.transactions.record_in_account(accounts["cib"].id, "2026-09-10", "-10", food.id, None, "Carrefour", "")
            for _ in range(55)]
    c.transactions.record_in_account(accounts["cib"].id, "2026-09-11", "-99", food.id, None, "Vodafone", "")
    html = client.get("/transactions?q=Carrefour").text
    assert sorted(_matching(html)) == sorted(t.id for t in made)
    assert "Select all 55 matching" in html
    assert 'class="register-result"' in html and "<b>55</b>" in html


def test_unfiltered_register_has_no_matching_list(c, setup, client):
    accounts, cats = setup
    c.transactions.record_in_account(accounts["cib"].id, "2026-09-10", "-10", cats["EXP.PERSONAL.FOOD"].id, None, "Carrefour", "")
    html = client.get("/transactions").text
    assert _matching(html) is None and 'class="register-result"' not in html


def test_all_transactions_offers_import_for_each_bank_and_cash_account(c, setup, client):
    accounts, _ = setup
    html = client.get("/transactions").text
    assert f'href="/accounts/{accounts["cib"].id}/import"' in html and "import-menu" in html
