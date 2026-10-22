"""The phone's Accounts tab (phone overhaul 2026-10-22): "Where is my money right now?" leads with In your accounts and
one sentence, then the accounts in the sidebar's groups with each group's total, and ends with one link to the
Transactions tab instead of a list of them."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials

from test_profile_app import create, token


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone_accounts")
    cfg = Credentials("http://127.0.0.1:9863")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


def _number(text: str) -> int:
    return int(text.replace(",", "").replace("−", "-"))


def test_it_leads_with_in_your_accounts_then_the_actions_then_the_groups(phone):
    html = phone.get("/accounts").text
    assert html.index("In your accounts") < html.index('class="phone-page-actions"') < html.index('phone-accounts-group')
    hero = re.search(r'class="phone-lead">([\d,]+) <small>EGP</small>', html)
    assert hero and re.search(r'class="phone-hero-line">Includes [\d,]+ held for others, so you own [\d,]+\.<', html)
    assert 'href="/accounts/new">Add account<' in html and 'href="/sms">From SMS<' in html  # the actions stay
    assert 'class="phone-header"><h1>Accounts</h1>' in html  # the heading for a screen reader
    # each group's total sits on the right of its name, and the groups add up to the hero's figure
    totals = [_number(t) for t in re.findall(r'class="phone-accounts-total">([\d,−-]+)<', html)]
    assert len(totals) >= 3 and sum(totals) == _number(hero.group(1))


def test_each_account_is_one_row_with_its_type_and_opens_as_before(phone):
    html = phone.get("/accounts").text
    assert re.search(r'<a class="phone-row" href="/accounts/\d+"><span>CIB Payroll<small>Bank account</small></span><b>[\d,]+</b></a>', html)
    assert re.search(r'<a class="phone-row" href="/accounts/\d+"><span>Gold at home<small>Physical asset</small></span>', html)
    assert "<td" not in html and ".00<" not in html  # whole EGP, no table


def test_transactions_is_a_link_not_a_list(phone):
    html = phone.get("/accounts").text
    assert 'class="phone-quiet" href="/transactions">See all transactions<' in html
    assert "phone-txn" not in html and "phone-latest" not in html


def test_a_bank_gets_its_name_a_circle_its_own_group_and_a_closed_account_its_fold(phone):
    session = re.search(r'name="lightning-session" content="([^"]+)"', phone.get("/accounts").text).group(1)
    phone.post("/accounts/new", data={"__session": session, "name": "Salary", "institution": "Banque Misr",
                                      "account_type": "BANK", "opening_balance_date": "2026-09-01",
                                      "opening_balance": "1,000"})
    phone.post("/accounts/new", data={"__session": session, "name": "Office circle", "account_type": "GAMEYA",
                                      "currency": "EGP", "opening_balance": "", "opening_balance_date": "2026-09-01"})
    html = phone.get("/accounts").text
    assert re.search(r"<span>Salary<small>Bank account · Banque Misr</small></span><b>1,000</b>", html)
    group = re.search(r'<h2 id="group-\d+">Gam&#39;eya</h2>.*?<span>Office circle', html, re.S)
    assert group, "the circle sits under the Gam'eya group"
    phone.post("/accounts/new", data={"__session": session, "name": "Old card", "account_type": "BANK",
                                      "opening_balance_date": "2026-09-01", "opening_balance": ""})
    old = re.search(r'href="/accounts/(\d+)"><span>Old card<', phone.get("/accounts").text).group(1)
    phone.post(f"/accounts/{old}/deactivate", data={"__session": session})
    html = phone.get("/accounts").text
    fold = html.index("Inactive accounts")
    assert "Old card" in html[fold:] and "Old card" not in html[:fold]
