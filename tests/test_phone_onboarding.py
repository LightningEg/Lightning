"""IV-11N: the phone's first launch. Welcome's intro, the four-card tour, setup's steps 3 to 6 after the profile and its
recovery key, and Home's first day that follows (owner decisions, 2026-11-20). Dummy data only."""
from __future__ import annotations

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.planning.domain import PlanKind
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.samples.tour import cards, comparison
from lightning.ui.i18n import translate
from test_profile_app import PASSWORD, SECRET, create, recovery_shown, token

D = Decimal


@pytest.fixture
def phone(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-20")
    cfg = Credentials("http://127.0.0.1:9867")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as client:
        client.get("/__launch", params={"code": cfg.launch_code})
        yield client, app


def ask(client, app, read):
    """Read the open profile on its own thread (the encrypted database stays on the thread that opened it)."""
    return client.portal.call(lambda: read(app.session.container))


def create_in(client, locale):
    """Create a profile in English, then turn to ``locale`` on Welcome's cookie just before the key is confirmed."""
    page = client.get("/profiles/new")
    page = client.post("/profiles/new", data={"csrf": token(page.text), "name": "Home", "currency": "EGP",
                                              "password": PASSWORD, "confirm": PASSWORD, **SECRET})
    key = recovery_shown(page.text)
    client.cookies.set("lightning_ui_locale", locale)
    return client.post("/profiles/confirm", data={"csrf": token(page.text), "recovery": key})


def session_token(text):
    return token(text, "__session")


def post(client, path, page, **data):
    return client.post(path, data={"__session": session_token(page.text), **data})


# ---------------------------------------------------------------- Welcome and the tour (11N1)

def test_welcome_plays_the_intro_once_and_offers_the_tour(phone):
    client, _ = phone
    page = client.get("/profiles")
    assert 'class="v2-intro"' in page.text and "sessionStorage" in page.text  # once per launch
    assert "prefers-reduced-motion" in page.text                              # never for reduced motion
    assert 'href="/profiles/tour"' in page.text and 'href="/profiles/new"' in page.text
    assert "passphrase" not in page.text.lower()


def test_the_tour_is_four_cards_in_the_owners_order_and_ends_on_setup(phone):
    client, _ = phone
    keys = [card.key for card in cards()]
    assert keys == ["quick", "went", "safe", "worth"]   # SMS logs itself, where it went, Safe to spend, Net worth
    for n, card in enumerate(cards(), 1):
        page = client.get(f"/profiles/tour?card={n}")
        assert page.status_code == 200 and card.question in page.text
        assert ("/profiles/tour?card=%d" % (n + 1) in page.text) == (n < 4)
    assert 'href="/profiles/new"' in client.get("/profiles/tour?card=4").text
    assert client.get("/profiles/tour?card=9").text == client.get("/profiles/tour").text  # out of range: the first


def test_the_tours_figures_add_up():
    quick, went, safe, worth = cards()
    assert quick.lead == -sum(r.amount for r in quick.groups[0].rows) == D("1495")
    assert went.lead == sum(r.amount for r in went.bars) and len(went.bars) == 5  # four, then Other (A16)
    assert went.bars[-1].label == "Other" and comparison(went) == D("1100")
    rows = [r for g in safe.groups for r in g.rows]
    assert safe.lead == sum(r.amount for r in rows) == D("1000")
    assert worth.lead == sum(r.amount for g in worth.groups for r in g.rows) == D("43000")


def test_the_tour_reads_in_arabic(phone):
    client, _ = phone
    client.cookies.set("lightning_ui_locale", "ar")
    for n, card in enumerate(cards(), 1):
        page = client.get(f"/profiles/tour?card={n}").text
        for text in (card.question, card.answer, card.foot, card.lead_label):
            assert translate(text, "ar") != text, text
            assert text not in page, text


# ---------------------------------------------------------------- setup's steps 3 to 6 (11N2)

def test_a_new_phone_profile_goes_on_to_step_three(phone):
    client, app = phone
    page = create(client, setup=True)
    assert page.url.path == "/start/account"
    assert "3 of 6" in page.text and "Your first account" in page.text
    assert ask(client, app, lambda c: c.settings.get("phone_start")) == "open"


def test_the_whole_setup_bank_salary_cash_then_home(phone):
    client, app = phone
    page = create(client, setup=True)
    page = post(client, "/start/account", page, account_type="BANK", institution="CIB", name="",
                opening_balance="18,500")
    assert page.url.path == "/start/salary" and "4 of 6" in page.text
    bank = ask(client, app, lambda c: next(a for a in c.accounts.list() if a.account_type.value == "BANK"))
    assert bank.institution == "CIB" and bank.name.startswith("CIB")
    page = post(client, "/start/salary", page, amount="30,000", payday="25", account_id=str(bank.id))
    assert page.url.path == "/start/cash" and "One week with your wallet" in page.text
    income = ask(client, app, lambda c: c.planning.items((PlanKind.INCOME,)))
    assert len(income) == 1 and income[0].account_id == bank.id
    page = post(client, "/start/cash", page, opening_balance="2,000")
    assert page.url.path == "/start/phone" and "6 of 6" in page.text
    wallet = ask(client, app, lambda c: next(a for a in c.accounts.list() if a.cash_at_hand))
    assert wallet.name == "Cash wallet"
    page = post(client, "/start/finish", page)
    assert page.url.path in ("/", "/home") and ask(client, app, lambda c: c.settings.get("phone_start")) == "done"
    assert ask(client, app, lambda c: c.settings.get("first_day_bills")) == "open"
    assert client.get("/start").url.path in ("/", "/home")   # setup does not come back once done


def test_every_step_can_be_skipped_and_a_cash_salary_waits_for_the_wallet(phone):
    client, app = phone
    page = create(client, setup=True)
    page = post(client, "/start/skip", page, step="account")
    assert page.url.path == "/start/salary" and "Cash, in hand" in page.text
    page = post(client, "/start/salary", page, amount="12000", payday="1", account_id="cash")
    assert page.url.path == "/start/cash" and not ask(client, app, lambda c: c.planning.items((PlanKind.INCOME,)))
    assert "I never use cash" not in page.text   # the salary needs the wallet
    page = post(client, "/start/cash", page, opening_balance="")
    wallet = ask(client, app, lambda c: next(a for a in c.accounts.list() if a.cash_at_hand))
    income = ask(client, app, lambda c: c.planning.items((PlanKind.INCOME,)))
    assert len(income) == 1 and income[0].account_id == wallet.id
    page = post(client, "/start/skip", page, step="phone")
    assert page.url.path in ("/", "/home") and ask(client, app, lambda c: c.settings.get("phone_start")) == "done"


def test_a_closed_app_comes_back_to_the_step_it_left(phone):
    client, app = phone
    page = create(client, setup=True)
    post(client, "/start/account", page, account_type="CASH", institution="Vodafone Cash", name="Wallet")
    assert client.get("/").url.path == "/start/salary"


def test_a_bad_amount_keeps_the_step_and_says_why(phone):
    client, _ = phone
    page = create(client, setup=True)
    page = post(client, "/start/skip", page, step="account")
    page = post(client, "/start/salary", page, amount="lots", payday="40", account_id="cash")
    assert page.status_code == 400 and "4 of 6" in page.text


def test_a_sample_instead_ends_setup(phone):
    client, app = phone
    create(client, setup=True)
    page = client.get("/start/samples")
    assert ask(client, app, lambda c: c.settings.get("phone_start")) == "done"
    assert 'id="samples"' in page.text


def test_step_six_explains_sms_before_asking(phone):
    client, _ = phone
    page = create(client, setup=True)
    for step in ("account", "salary", "cash"):
        page = post(client, "/start/skip", page, step=step)
    assert page.url.path == "/start/phone"
    assert "never from people" in page.text and "Finish setup" in page.text


@pytest.mark.parametrize("path", ["/start/account", "/start/salary", "/start/cash", "/start/phone"])
def test_every_step_reads_in_arabic(phone, path):
    client, app = phone
    create_in(client, "ar")   # chosen on Welcome, before the profile exists
    assert ask(client, app, lambda c: c.settings.get("locale")) == "ar"
    text = client.get(path).text
    body = re.sub(r"<[^>]+>", " ", text.split("<body>", 1)[1])
    english = [w for w in re.findall(r"[A-Za-z]{4,}", body) if w not in ("Lightning", "Vodafone", "InstaPay", "Cash")]
    assert not english, english


# ---------------------------------------------------------------- Home's first day after setup (11N3)

def _set_up(client):
    page = create(client, setup=True)
    page = post(client, "/start/account", page, account_type="BANK", institution="NBE", name="NBE", opening_balance="9,000")
    bank_id = re.search(r'name="account_id" value="(\d+)"', page.text).group(1)
    page = post(client, "/start/salary", page, amount="20,000", payday="1", account_id=bank_id)
    page = post(client, "/start/cash", page, opening_balance="1,500")
    return post(client, "/start/finish", page)


def test_after_setup_home_asks_for_bills_and_a_first_payment(phone):
    client, _ = phone
    home = _set_up(client)
    assert "Your regular bills" in home.text and "Your first payment" in home.text
    assert "Your salary account" not in home.text and "Your payday" not in home.text  # setup did both
    assert "0/2" in home.text and "I have no regular bills" in home.text


def test_no_regular_bills_passes_the_bills_step(phone):
    client, app = phone
    home = _set_up(client)
    home = post(client, "/start/no-bills", home)
    assert ask(client, app, lambda c: c.settings.get("first_day_bills")) == "none"
    assert "1/2" in home.text and "I have no regular bills" not in home.text


def test_a_skipped_payday_stays_on_the_first_day(phone):
    client, _ = phone
    page = create(client, setup=True)
    for step in ("account", "salary"):
        page = post(client, "/start/skip", page, step=step)
    page = post(client, "/start/cash", page, opening_balance="800")
    page = post(client, "/start/finish", page)
    assert "Your payday" in page.text and "Your regular bills" in page.text and "0/3" in page.text
    assert "Your salary account" not in page.text   # the cash wallet is an account


def test_skipping_everything_ends_on_the_empty_profiles_page(phone):
    client, _ = phone
    page = create(client, setup=True)
    for step in ("account", "salary", "cash", "phone"):
        page = post(client, "/start/skip", page, step=step)
    assert "Where do you keep your money?" in page.text and 'id="samples"' in page.text


def test_a_profile_from_before_setup_keeps_its_three_steps(tmp_path, monkeypatch):
    from datetime import date
    from lightning.ui.phone.screens import home
    from test_phone_home import build
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    c = build(tmp_path / "old.db")
    screen = home.build(c, date(2026, 10, 4))
    assert [key for key, _ in screen.steps] == ["account", "payday", "payment"] and screen.state == "first_run"
    c.db.close()
