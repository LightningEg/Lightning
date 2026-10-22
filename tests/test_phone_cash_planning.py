"""Cash planning on the phone (phone overhaul 2026-10-22): "What leaves before payday, and am I covered?"

The Due before payday hero is the Safe to spend working's own row, its sentences say how many payments, whether free
cash covers them and whether any are late, and Coming up lists late payments first, then what is due before payday,
ending with payday itself. Free cash and Reserves are two tiles. Safe to spend and its working stay on the page."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.core.figures import label
from lightning.ui.web import create_app

DAY = date(2026, 10, 6)


def _phone(c):
    """The phone app: every request renders in the phone frame, as profile_app(phone=True) does."""
    app = create_app(c)

    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)

    return TestClient(wrapped, base_url="http://127.0.0.1")


def _plan(c, **items):
    for name, kind, amount, start, extra in items.values():
        c.planning.create(kind=kind, name=name, amount=amount, frequency="MONTHLY", start_date=start, **extra)


def _hero(html: str) -> str:
    return re.search(r'(?s)<section class="phone-hero has-seam".*?</section>', html).group(0)


def _coming(html: str) -> str:
    return re.search(r'(?s)<section class="phone-section phone-plan-coming".*?</section>', html).group(0)


def _text(html: str) -> str:
    return re.sub(r"\s+([.,])", r"\1", " ".join(re.sub(r"<[^>]+>", " ", html).split()))


@pytest.fixture
def week(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    accounts, _ = setup
    _plan(c, salary=("ACME Egypt", "INCOME", "45000", "2026-10-25", {}),
          rent=("Landlord", "BILL", "12000", "2026-10-10", {}),
          stream=("Streaming", "SUBSCRIPTION", "120", "2026-10-12", {}),
          internet=("Internet", "BILL", "650", "2026-09-20", {"account_id": str(accounts["cib"].id)}),
          later=("Gym", "BILL", "300", "2026-10-28", {}))
    return _phone(c)


def test_the_hero_is_the_workings_due_before_payday_with_its_sentences(c, week):
    html = week.get("/plan").text
    parts = dict(c.forecaster.forecast(DAY).safe_to_spend_parts)
    due = -parts[label("payments_before_next_income")]
    hero = _hero(html)
    assert "Due before payday" in hero and f"{due:,.0f} <small>EGP</small>" in hero
    assert "12,770" in hero  # Landlord 12,000 + Streaming 120 + Internet's October 650
    text = _text(hero)
    assert "3 payments until 2026-10-25." in text and "All covered by free cash." in text
    assert "1 payment is already late." in text
    # The hero sits above the worded tabs, which sit right under its sentence.
    assert html.index('class="phone-hero has-seam"') < html.index('class="section-bar"') < html.index('class="phone-section phone-plan-coming"')
    assert html.count('class="phone-hero ') == 1  # the sentence is shown once


def test_coming_up_lists_late_first_then_what_is_due_and_ends_with_payday(c, week):
    html = _coming(week.get("/plan").text)
    names = re.findall(r'class="phone-row phone-plan-row[^"]*"[^>]*href="[^"]+"><span>([^<]+)<small>', html)
    # Late Internet, then by date; payday ends the list; Gym (after payday) is the folded row below it.
    assert names == ["Internet", "Landlord", "Streaming", "Internet", "ACME Egypt", "Gym"], names
    assert "Late · 16 days" in html[html.index("Internet"):html.index("Landlord")]
    assert html.count("plan-status-late") == 1 and "Payday" in html and "+45,000" in html
    assert "−12,000" in html and "−120" in html and "in 4 days" in html and "2026-10-10" in html
    assert "Gym" not in html.split("<details")[0]  # after payday: folded under the list
    assert "<details" in html and "Gym" in html.split("<details")[1]


def test_every_row_keeps_its_pay_sheet_link_with_the_name_first(c, week):
    html = week.get("/plan").text
    for name in ("Landlord", "Streaming", "Internet", "ACME Egypt", "Gym"):
        assert re.search(r'href="/plan/items/\d+/pay\?[^"]+"[^>]*><span>' + name, html), name


def test_two_tiles_and_the_safe_to_spend_home_stay(c, week):
    html = week.get("/plan").text
    tiles = re.search(r'(?s)<section class="phone-kpis".*?</section>', html).group(0)
    assert tiles.count('class="phone-kpi ') == 2 and "Free cash" in tiles and "Reserves" in tiles and "After bills:" in tiles
    assert html.index(tiles) > html.index('class="phone-section phone-plan-coming"')
    for marker in ('id="plan-build"', 'id="plan-forecast"', 'id="plan-next"', "Each month ahead", "What is promised"):
        assert marker in html, marker
    assert html.index('id="plan-build"') > html.index(tiles)


def test_short_free_cash_says_by_how_much(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    _plan(c, salary=("ACME Egypt", "INCOME", "45000", "2026-10-25", {}),
          laptop=("Laptop", "BILL", "90000", "2026-10-12", {}))
    html = _phone(c).get("/plan").text
    free = c.forecaster.forecast(DAY).free_cash
    assert f"Free cash is {90000 - free:,.0f} short of what is due." in _text(_hero(html))
    assert "−" in re.search(r"After bills: ([^<]+)<", html).group(0)  # the true minus, like every other figure


def test_no_income_date_reads_the_next_three_months_and_nothing_planned_asks_for_bills(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    empty = _phone(c).get("/plan").text
    assert "Nothing is due in the next 3 months." in _text(_hero(empty))
    assert "Add your bills, subscriptions, income and loans on Recurring" in _coming(empty)
    _plan(c, rent=("Landlord", "BILL", "12000", "2026-10-10", {}))
    html = _phone(c).get("/plan").text
    assert "payments in the next 3 months." in _text(_hero(html)) or "1 payment in the next 3 months." in _text(_hero(html))
    assert 'class="phone-row phone-plan-row' in _coming(html) and "Payday" not in _coming(html)
