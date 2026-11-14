"""What does your bank say? One typed balance; a small difference becomes one adjustment."""
from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError

D = Decimal


def test_small_means_one_percent_or_at_least_100(c, setup):
    accounts, _ = setup
    wallet, cib = accounts["wallet"].id, accounts["cib"].id
    assert c.reconciliation.check(wallet, "2026-09-30", D("1150")).limit == D("100")      # 1% of 1,150 is 11.50
    assert c.reconciliation.check(cib, "2026-09-30", D("49000")).limit == D("490.00")
    assert c.reconciliation.check(cib, "2026-09-30", D("50000")).matches
    assert c.reconciliation.check(cib, "2026-09-30", D("49510")).small
    assert not c.reconciliation.check(cib, "2026-09-30", D("49000")).small


def test_a_shortfall_is_spending_and_an_excess_is_income(c, setup):
    accounts, _ = setup
    wallet = accounts["wallet"].id
    short = c.reconciliation.adjust(wallet, "2026-09-30", D("1150"))
    assert short.ref.startswith("OUT-") and c.reconciliation.balance(wallet, "2026-09-30") == D("1150")
    assert c.categories.get(short.lines[0].category_id).code == "EXP.UNACCOUNTED"   # IV-12V: a wallet's gap is unaccounted
    extra = c.reconciliation.adjust(wallet, "2026-10-01", D("1180"))
    assert extra.ref.startswith("IN-") and c.reconciliation.balance(wallet, "2026-10-01") == D("1180")
    assert c.categories.get(extra.lines[0].category_id).code == "INC.UNACCOUNTED"
    assert c.reporting.cash_flow("2026-09-01", "2026-09-30").outflows == D("50")


def test_a_big_difference_or_a_match_is_never_adjusted(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    with pytest.raises(ValidationError, match="too big"):
        c.reconciliation.adjust(cib, "2026-09-30", D("45000"))
    with pytest.raises(ValidationError, match="already matches"):
        c.reconciliation.adjust(cib, "2026-09-30", D("50000"))
    assert c.reconciliation.balance(cib, "2026-09-30") == D("50000")


def test_the_page_offers_the_adjustment_only_when_small(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    wallet, cib = accounts["wallet"].id, accounts["cib"].id
    small = client.get(f"/accounts/{wallet}/reconcile?date=30/9/2026&balance=1,150").text
    assert "A small difference" in small and "Post adjustment of" in small
    big = client.get(f"/accounts/{cib}/reconcile?date=2026-09-30&balance=40,000").text
    assert "Too big to adjust" in big and "Post adjustment" not in big
    refused = client.post(f"/accounts/{cib}/reconcile", data={"date": "2026-09-30", "balance": "40000"})
    assert refused.status_code == 400 and "too big to adjust" in refused.text
    posted = client.post(f"/accounts/{wallet}/reconcile", data={"date": "2026-09-30", "balance": "1150"},
                         follow_redirects=False)
    assert posted.status_code == 303 and c.reconciliation.balance(wallet, "2026-09-30") == D("1150")


def test_a_cash_wallet_adjusts_any_size_and_a_bank_still_refuses(c, setup):
    """IV-12V (owner, 2026-11-10): a wallet has no statement, so a far-off count is settled, filed as unaccounted."""
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    wallet, cib = accounts["wallet"].id, accounts["cib"].id
    before = c.reconciliation.balance(wallet, "2026-09-30")
    check = c.reconciliation.check(wallet, "2026-09-30", before - D("900"))
    assert not check.small and check.adjustable and check.filed_under == "Unaccounted spending"
    txn = c.reconciliation.adjust(wallet, "2026-09-30", before - D("900"))
    assert c.categories.get(txn.lines[0].category_id).code == "EXP.UNACCOUNTED"
    assert c.reconciliation.balance(wallet, "2026-09-30") == before - D("900")
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{wallet}/reconcile?date=2026-09-30&balance={before + D('5000')}").text
    assert "Post adjustment of" in page and "Unaccounted money found" in page and "Latest rows" in page
    with pytest.raises(ValidationError, match="too big"):
        c.reconciliation.adjust(cib, "2026-09-30", D("45000"))
