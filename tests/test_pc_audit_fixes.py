"""PC usability audit, 2026-11-21 (report r38): fixes the guideline already asked for."""

from __future__ import annotations

import re
from datetime import date

from fastapi.testclient import TestClient

from lightning.demo import build_demo
from lightning.ui.web import create_app


def _calendar_month(html: str) -> str:
    return re.search(r'<h2 id="upcoming-month">([^<]+)</h2>', html).group(1).strip()


def test_cash_planning_opens_on_this_month_while_a_bill_is_still_to_pay(c, monkeypatch):
    """A05: every tab opens on the current month. With payday next month, a bill still due this month keeps the
    calendar here, so it is not behind Previous month."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-21")
    build_demo(c, date(2026, 11, 21))   # the audit's household: November's salary is in, the electricity bill is due on the 24th
    with TestClient(create_app(c)) as browser:
        assert _calendar_month(browser.get("/plan").text) == "November 2026"


def test_budget_header_has_one_page_action(c, monkeypatch):
    """A05: one page action after the period control; Next month (NF-12AL4) is in More actions."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-21")
    build_demo(c, date(2026, 11, 21))
    with TestClient(create_app(c)) as browser:
        page = browser.get("/budget").text
    top = page.split('page-controls', 1)[1].split('class="section-gear', 1)[0]
    assert re.findall(r'class="btn small"[^>]*>([^<]+)<', top) == ["Fill this month"]
    menu = top.split('class="action-menu', 1)[1]
    assert 'href="/budget?month=2026-12">Next month</a>' in menu


def test_a_buy_is_not_toned_as_spending_in_the_register(c, monkeypatch):
    """A03 / A16 "a colour off its meaning": buying gold or a fund moves money into holdings; it is not spending."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-21")
    build_demo(c, date(2026, 11, 21))
    with TestClient(create_app(c)) as browser:
        page = browser.get("/transactions").text
    rows = [row for row in page.split("<tr")[1:] if "zurde" in row]   # the demo buys a gold ring at L’Azurde
    assert rows, "the demo household has a buy in these months"
    for row in rows:
        assert not re.search(r'class="num amount (neg|pos)"', row), row[:300]


def test_settings_and_safety_titles_match_the_sidebar_and_the_version_shows_once(c, monkeypatch):
    """A05 (r38): a section's first tab carries the section's name; Settings names the version once."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-21")
    build_demo(c, date(2026, 11, 21))
    with TestClient(create_app(c)) as browser:
        settings = browser.get("/settings").text
        safety = browser.get("/plan/reserves").text
    assert re.search(r"<h1[^>]*>\s*Settings\s*</h1>", settings) and re.search(r"<h1[^>]*>\s*Safety\s*</h1>", safety)
    assert "App version" not in settings and 'id="lightning-version"' in settings
