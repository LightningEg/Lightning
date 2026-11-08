"""Gam'eya screens on PC and phone, in English and Arabic: create, set terms, record, and the figures that move."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

TODAY = date(2026, 12, 31)


def _client(c, phone=False, locale="en"):
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app, follow_redirects=False)
    if locale != "en":
        assert client.post("/settings/locale", data={"locale": locale}).status_code == 303
    return client


def _circle(c, setup, name="Office gam'eya", **overrides):
    accounts, _ = setup
    circle = c.account_flows.open_account(name, "GAMEYA", "2026-09-01", "0")
    terms = {"organiser": "Um Ali", "members": 10, "installment": "2000", "first_date": "2026-10-05",
             "my_turn": 3, "funding_account_id": accounts["cib"].id, "payout_account_id": accounts["cib"].id}
    terms.update(overrides)
    c.gameya.save_terms(circle.id, **terms)
    return circle


def test_create_circle_through_the_screens_on_pc_and_phone(c, setup):
    accounts, _ = setup
    cib = str(accounts["cib"].id)
    for phone in (False, True):
        client = _client(c, phone)
        name = f"Family gam'eya {'phone' if phone else 'pc'}"
        created = client.post("/accounts/new", data={"name": name, "account_type": "GAMEYA", "currency": "EGP",
                                                      "opening_balance": "", "opening_balance_date": "2026-09-01"})
        assert created.status_code == 303 and created.headers["location"].startswith("/gameya/")
        path = created.headers["location"].split("?")[0]
        circle_id = int(path.rsplit("/", 1)[1])
        page = client.get(path)
        assert page.status_code == 200 and "Set up your circle" in page.text
        terms = {"organiser": "Um Ali", "members": "10", "installment": "2000", "first_date": "2026-10-05",
                 "my_turn": "3", "interest": "none", "funding_account_id": cib, "payout_account_id": cib}
        bad = client.post(path + "/terms", data=terms | {"members": "1"})
        assert bad.status_code == 400 and "from 2 to 60" in bad.text
        assert client.post(path + "/terms", data=terms).status_code == 303
        saved = c.gameya.get(circle_id)
        assert saved.annual_rate == 0 and saved.payout == Decimal("20000.00")
        page = client.get(path)
        for text in ("Where you stand", "0 of 10", "2026-10-05", "Record instalment", "Record payout",
                     "No recorded balance yet.", 'value="2000.00"'):
            assert text in page.text, (phone, text)
        paid = client.post(path + "/instalment", data={"date": "2026-10-05", "amount": "2000.00", "account_id": cib})
        assert paid.status_code == 303 and c.gameya.progress(circle_id, TODAY).paid == 1
        assert "The circle owes you" in client.get(path).text
        refused = client.post(path + "/instalment", data={"date": "2026-11-05", "amount": "99999999",
                                                          "account_id": cib})
        assert refused.status_code == 400 and "of your cash on" in refused.text
        taken = client.post(path + "/payout", data={"date": "2026-12-05", "amount": "20000.00", "account_id": cib})
        assert taken.status_code == 303
        page = client.get(path).text
        assert "You owe the circle" in page and "18,000" in page
        register = client.get(f"/accounts/{circle_id}")  # the register still works, with a way to the circle
        assert register.status_code == 200 and f"/gameya/{circle_id}" in register.text
        if not phone:
            assert f"/gameya/{circle_id}" in client.get("/accounts").text


def test_overview_and_plan_show_the_circle_figures(c, setup):
    circle = _circle(c, setup, my_turn=1)
    c.gameya.record_instalment(circle.id, "2026-10-05")
    c.gameya.record_payout(circle.id, "2026-10-05")
    home = _client(c).get("/").text
    assert "Gam&#39;eya still to pay" in home or "Gam'eya still to pay" in home
    plan = _client(c).get("/plan").text
    assert "still to pay" in plan and "18,000" in plan
    assert "18,000" in _client(c, phone=True).get("/plan").text


def test_gameya_pages_have_no_english_system_text_in_arabic(c, setup):
    from test_arabic_no_english import _english
    circle = _circle(c, setup, my_turn=1)
    c.gameya.record_instalment(circle.id, "2026-10-05")
    names = {"Office gam'eya", "Um Ali", "CIB Current", "CIB", "Wallet", "CIB CD", "THNDR", "Fresh False", "Fresh True"}
    for phone in (False, True):
        client = _client(c, phone, "ar")
        for path in (f"/gameya/{circle.id}", f"/accounts/{circle.id}", "/accounts"):
            page = client.get(path)
            assert page.status_code == 200 and 'dir="rtl"' in page.text, path
            assert _english(page.text, names) == [], (path, phone, _english(page.text, names))
        fresh = c.account_flows.open_account(f"Fresh {phone}", "GAMEYA", "2026-09-01", "0")
        page = client.get(f"/gameya/{fresh.id}")
        assert _english(page.text, names | {f"Fresh {phone}"}) == [], phone


def test_new_figure_and_plan_words_are_arabic():
    from lightning.core.figures import FIGURES
    from lightning.ui.i18n import translate
    for text in (FIGURES["gameya_paid_in"].label, FIGURES["gameya_still_to_pay"].label,
                 "Gam'eya payout (estimate)", "Gam'eya instalments before next income",
                 "Gam'eya instalment due: Office", "Gam'eya payout due: Office",
                 "Instalment 4 of 10 was due 2026-10-05 · 2,000 EGP · not recorded yet."):
        arabic = translate(text, "ar")
        assert arabic != text and not any("a" <= ch.lower() <= "z" for ch in arabic.replace("Office", "").replace("EGP", "")), (text, arabic)


def test_accounts_sidebar_more_and_overview_agree_on_in_your_accounts(c, setup, monkeypatch):
    """BV-3AQ (audit 2026-11-05 F4, owner decision 2026-11-05): In your accounts is what the account rows add up to,
    the circle you still owe counted below zero, on Accounts, the sidebar, More and Overview alike. Accounts then
    reconciles it to What you own: less held for others, plus the circle still to pay (which sits in What you owe)."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-05")
    circle = _circle(c, setup, my_turn=1)
    c.gameya.record_instalment(circle.id, "2026-10-05")
    c.gameya.record_payout(circle.id, "2026-10-05")
    p = c.position.at(date(2026, 10, 5))
    rows = sum((value for account, value in c.reporting.net_worth("2026-10-05").by_account if account.active),
               Decimal(0))
    assert p.gameya_still_to_pay == Decimal("18000")
    assert p.in_your_accounts == rows == p.what_you_own + p.held_for_others - p.gameya_still_to_pay
    total = f"{p.in_your_accounts:,.0f}"
    pc = _client(c).get("/accounts").text
    assert pc.count(total) >= 2  # the sidebar and the Accounts lead read the same figure
    assert "+18,000" not in pc and "counted in what you owe" in pc and "18,000" in pc and f"{p.what_you_own:,.0f}" in pc  # How it adds up: the circle row, then What you own
    from lightning.ui.phone.screens import money
    assert money.build(c, date(2026, 10, 5)).net_worth == p.net_worth   # Money leads with the same net worth
    phone = _client(c, phone=True).get("/accounts").text
    assert total in phone and "18,000 you still owe a circle, so you own" in phone
    home = _client(c).get("/").text
    assert f"{p.net_worth:,.0f}" in home
    ar = _client(c, phone=True, locale="ar").get("/accounts").text
    assert "لسه عليك لجمعية" in ar
