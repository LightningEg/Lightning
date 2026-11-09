"""3AY10: Money. Net worth today, the balances themselves (four, then N more), Coming up with never a late bill."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.planning.bill_state import BillState
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.phone.screens import money as screen
from lightning.ui.web import create_app


@pytest.fixture
def mohab(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-04")
    load_mohab_2026(c)
    return c


def test_net_worth_is_the_positions_and_balances_are_four_then_more(mohab):
    day = date(2026, 10, 4)
    s = screen.build(mohab, day)
    now = mohab.position.at(day)
    assert s.net_worth == now.net_worth and s.what_you_owe == now.what_you_owe
    assert len(s.accounts) <= screen.ACCOUNTS_SHOWN
    assert [a.balance for a in s.accounts] == sorted((a.balance for a in s.accounts), reverse=True)


def test_coming_up_never_holds_a_late_bill_and_late_ones_are_one_pointer(mohab):
    s = screen.build(mohab, date(2026, 10, 25))      # bills have gone late by then
    assert len(s.coming_up) <= screen.COMING_UP
    assert all(b.state not in (BillState.LATE, BillState.LATE_STALE) for b in s.coming_up)


def test_the_page_renders_with_a_link_to_every_shown_balance_and_the_gear(mohab):
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/money").text
    s = screen.build(mohab, date(2026, 10, 4))
    assert all(f'href="/accounts/{a.id}"' in page for a in s.accounts)
    assert 'href="/settings"' in page and "Coming up" in page


def test_the_accounts_page_lists_every_balance_and_money_links_to_it(mohab):
    day = date(2026, 10, 4)
    page = screen.accounts_page(mohab, day)
    assert len(page.rows) >= len(screen.build(mohab, day).accounts)
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    html = client.get("/money/accounts").text
    assert all(f'href="/accounts/{a.id}"' in html for a in page.rows)
    if screen.build(mohab, day).accounts_more:
        assert 'href="/money/accounts"' in client.get("/money").text


def test_the_bills_page_groups_the_one_bill_state_and_agrees_with_coming_up(mohab):
    day = date(2026, 10, 25)
    bills, money = screen.bills_page(mohab, day), screen.build(mohab, day)
    upcoming = {(b.payment.item.id, b.due_date) for b in (*bills.week, *bills.before_payday, *bills.after_payday)}
    assert {(b.payment.item.id, b.due_date) for b in money.coming_up} <= upcoming          # Coming up is a slice of Bills
    assert not {(b.payment.item.id, b.due_date) for b in bills.late} & upcoming             # a bill sits in one group only
    app = create_app(mohab)
    mount_phone(app)
    page = TestClient(app).get("/money/bills")
    assert page.status_code == 200 and ".00" not in page.text.split("<main", 1)[1]   # whole EGP, A16


def test_money_rows_carry_figures_and_settings_leave_for_the_gear(mohab):
    """IV-11H: at most 12 rows under the hero, each with its figure or opening one place; the settings rows are on ⚙
    (Settings), the analysis is one Reports and reviews row, and the Money tab no longer wears More's "···"."""
    import re
    app = create_app(mohab)
    mount_phone(app)
    client = TestClient(app)
    page = client.get("/money").text
    body = page.split("</section>", 1)[1].split('<nav class="phone-tabbar"', 1)[0]   # below the hero
    rows = re.findall(r'<a class="phone-row"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
    assert 0 < len(rows) <= 12
    for href, inner in rows:
        assert href.startswith("/") and ("chevron" in inner or "fig" in inner), href
    for gone in ("/categories", "/counterparties", "/rules", "/profiles/devices", "/checks", "/money/report"):
        assert f'href="{gone}"' not in body, gone
    assert 'class="phone-icon" href="/settings"' in page                      # the gear
    assert "M4.5 12h1M11.5 12h1M18.5 12h1" not in page                        # More's dots are gone from the tab bar
    s = screen.build(mohab, date(2026, 10, 4))
    assert s.goals_count and f"{s.goals_funded} of {s.goals_count} funded" in body
    reviews = client.get("/money/reviews").text
    assert all(f'href="{h}"' in reviews for h in ("/money/report", "/plan", "/birdview/expenses", "/review"))


def test_net_worth_trend_ends_at_the_hero_and_what_you_own_adds_up(mohab):
    """IV-11D4: the trend's last point is today's net worth (the hero), and the bar's parts add to What you own, in
    A04's order (Cash, Deposits, Gold, Stocks, Other)."""
    day = date(2026, 10, 4)
    s = screen.build(mohab, day)
    line = s.trend["series"][0]
    assert not s.trend["too_short"] and line["values"][-1] == s.net_worth and line["last"]["value"] == s.net_worth
    assert len(s.trend["labels"]) <= screen.TREND_MONTHS
    assert sum(p["value"] for p in s.own_split) == s.what_you_own
    order = [key for key, _ in screen.FAMILIES]
    assert [p["key"] for p in s.own_split] == sorted((p["key"] for p in s.own_split), key=order.index)
    assert abs(sum(p["share"] for p in s.own_split) - 100) < 0.01
    app = create_app(mohab)
    mount_phone(app)
    html = TestClient(app).get("/money").text
    assert 'class="phone-chart-trend"' in html and html.count('class="phone-chart-trend-dot') == len(line["dots"])
    assert html.count("<span>", html.index('class="phone-chart-trend-x"'), html.index("</div>", html.index('class="phone-chart-trend-x"'))) <= 3
    assert all(f'tone-{p["key"]}' in html for p in s.own_split)
