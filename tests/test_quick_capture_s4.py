"""S4 Quick capture (IV-7AL, NF-7AM, IV-12W): the phone Add sheet starts on the amount, offers payments from the
accounts money is paid from, picks a payee's usual account, repeats an entry and saves another; the PC register asks
once about a forgotten minus and its search lists payments first."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from test_phone_capture import _phone, month  # noqa: F401  (the fixture and the phone client)
from lightning.ui.web import create_app


def test_from_lists_only_accounts_money_is_paid_from(month):
    c, accounts, _ = month
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{accounts['cib'].id}/transaction/new").text
    chip = re.search(r"<select id=\"popup-account\".*?</select>", sheet, re.S).group(0)
    assert "CIB Current" in chip and "Wallet" in chip
    spend = {a.name for a in c.accounts.list(active_only=True) if a.account_type.value in ("CASH", "BANK")}
    listed = set(re.findall(r"<option value=\"\d+\"[^>]*>([^<]+)</option>", chip))
    assert listed == spend and any(a.account_type.value == "DEPOSIT" for a in c.accounts.list())


def test_a_payee_always_paid_from_one_account_selects_it(month):
    c, accounts, cats = month
    wallet, cib = accounts["wallet"], accounts["cib"]
    for day in ("2026-09-14", "2026-09-15", "2026-09-16"):
        c.transactions.record_in_account(wallet.id, day, "-40", cats["EXP.PERSONAL.FOOD"].id, None, "Kiosk Cola", "")
    assert c.transactions.usual_accounts()["Kiosk Cola"] == wallet.id
    sheet = _phone(c).get(f"/accounts/{cib.id}/transaction/new").text
    assert re.search(rf'<option value="Kiosk Cola"[^>]*data-account="{wallet.id}"', sheet)


def test_repeat_opens_add_filled_and_selects_the_amount(month):
    c, accounts, cats = month
    phone = _phone(c)
    txn = c.transactions.record_in_account(accounts["cib"].id, "2026-09-20", "-75", cats["EXP.PERSONAL.FOOD"].id, None, "Seoudi", "")
    sheet = phone.get(f"/transactions/{txn.id}/sheet?return_to=/transactions").text
    link = re.search(r'href="(/accounts/\d+/transaction/new\?[^"]*repeat=1[^"]*)"', sheet)
    assert link and "Repeat" in sheet
    filled = phone.get(link.group(1).replace("&amp;", "&")).text
    assert 'value="75' in filled and 'value="Seoudi"' in filled and "data-repeat" in filled
    assert 'value="2026-09-20"' not in filled   # dated today, not the old day


def test_save_and_add_another_keeps_account_and_day(month):
    c, accounts, cats = month
    phone = _phone(c)
    sheet = phone.get(f"/accounts/{accounts['wallet'].id}/transaction/new").text
    assert "Save and add another" in sheet
    session = re.search(r'name="__session" value="([^"]*)"', sheet).group(1)
    sub = re.search(r'name="submission" value="([^"]*)"', sheet).group(1)
    r = phone.post(f"/accounts/{accounts['wallet'].id}/transaction/new", data={
        "__session": session, "submission": sub, "kind": "out", "amount": "20", "category_id": str(cats["EXP.PERSONAL.FOOD"].id),
        "date": "2026-09-18", "return_to": "/home", "again": "1"})
    assert r.url.path == f"/accounts/{accounts['wallet'].id}/transaction/new"
    assert "date=2026-09-18" in str(r.url) and 'value="2026-09-18"' in r.text and "Saved." in r.text
    assert c.transactions.usual_payees() is not None


def test_usual_payees_are_the_three_most_used_lately(month):
    c, accounts, cats = month
    from lightning.core.dates import today
    day = today().isoformat()
    for party, n in (("Tea Stand", 3), ("Bakery", 2), ("Taxi", 4), ("Rare", 1)):
        for _ in range(n):
            c.transactions.record_in_account(accounts["wallet"].id, day, "-10", cats["EXP.PERSONAL.FOOD"].id, None, party, "")
    assert [p["name"] for p in c.transactions.usual_payees()] == ["Taxi", "Tea Stand", "Bakery"]


def test_home_keeps_its_phone_page_after_a_save(month):
    c, _, _ = month
    page = _phone(c).get("/?msg=Saved.").text
    assert "Safe to spend" in page or "phone-" in page


def test_pc_asks_once_about_a_forgotten_minus(month):
    c, accounts, _ = month
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get(f"/accounts/{accounts['cib'].id}").text
    session = re.search(r'name="__session" value="([^"]*)"', page).group(1)
    data = {"__session": session, "date": "2026-09-20", "counterparty": "Carrefour", "category": "Food & groceries",
            "amount": "200", "notes": ""}
    before = len(c.transactions.search_ids("Carrefour"))
    asked = client.post(f"/accounts/{accounts['cib'].id}/register", data=data)
    assert asked.status_code == 400 and "Refund of 200, or a payment?" in asked.text
    assert len(c.transactions.search_ids("Carrefour")) == before
    kept = client.post(f"/accounts/{accounts['cib'].id}/register", data=data | {"sign_checked": "200"}, follow_redirects=False)
    assert kept.status_code in (200, 303) and len(c.transactions.search_ids("Carrefour")) == before + 1
    minus = client.post(f"/accounts/{accounts['cib'].id}/register", data=data | {"amount": "-200"}, follow_redirects=False)
    assert minus.status_code in (200, 303) and len(c.transactions.search_ids("Carrefour")) == before + 2


def test_pc_search_lists_payments_first(month):
    c, _, _ = month
    from lightning.ui.routes.search import matches
    results = matches(c, "Carrefour")
    kinds = [r["kind"] for r in results]
    assert kinds[0] == "Transaction" and kinds.count("Transaction") <= 5
    assert kinds.index("Counterparty") > kinds.index("Transaction")


def test_zakat_tab_is_hidden_until_zakat_is_on(month):
    c, _, _ = month
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get("/transactions").text
    assert 'href="/zakat"' not in page


def test_phone_running_balance_is_whole(month):
    c, accounts, _ = month
    page = _phone(c).get(f"/accounts/{accounts['cib'].id}").text
    assert not re.search(r"<small>[\d,]+\.\d\d</small>", page)
