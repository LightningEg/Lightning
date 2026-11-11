"""IT-12AE1: the PC and the phone are compared on one household. One database, the PC app and the phone app over it,
the demo household and Mohab's year on pinned days. A headline figure carries `data-fig="<registry key>"`; every key
shown on both surfaces shows one value, and the ones listed in OWNERS equal their owner function."""
from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from lightning.core.money import fmt
from lightning.ui.web import create_app

PC = ["/", "/plan", "/budget", "/accounts", "/investments"]
PHONE = ["/home", "/money", "/budget"]
FIG = re.compile(r'data-fig="([a-z_]+)"[^>]*>(.*?)</', re.S)

OWNERS = {  # registry key -> the owner function, on the pinned day
    "net_worth": lambda c, day: c.position.at(day).net_worth,
    "safe_to_spend": lambda c, day: c.forecaster.forecast(day).safe_to_spend,
    "free_cash": lambda c, day: c.forecaster.forecast(day).free_cash,
}


def _client(c, phone: bool) -> TestClient:
    app = create_app(c)
    if phone:
        from lightning.ui.phone.router import mount_phone
        mount_phone(app)
        inner = app

        async def phone_app(scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})["phone"] = True
            await inner(scope, receive, send)
        app = phone_app
    return TestClient(app, follow_redirects=True)


def _shown(c, phone: bool) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}
    client = _client(c, phone)
    for path in (PHONE if phone else PC):
        for key, value in FIG.findall(client.get(path).text):
            text = re.sub(r"<[^>]+>|EGP|\s+", "", html.unescape(value)).replace("−", "-")
            seen.setdefault(key, set()).add(text)
    return seen


@pytest.fixture(params=[("demo", "2026-11-09"), ("mohab", "2026-10-20")], ids=lambda p: p[0])
def household(request, tmp_path, monkeypatch):
    from datetime import date
    from lightning.bootstrap import build
    kind, day = request.param
    monkeypatch.setenv("LIGHTNING_TODAY", day)
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "agree.db")
    if kind == "demo":
        from lightning.demo import build_demo
        build_demo(c)
    else:
        from lightning.samples import load_mohab_2026
        load_mohab_2026(c)
    yield c, date.fromisoformat(day)
    c.db.close()


def test_a_figure_shows_one_value_on_every_page_of_both_surfaces(household):
    c, _ = household
    pc, phone = _shown(c, False), _shown(c, True)
    assert {"net_worth", "safe_to_spend"} <= pc.keys() & phone.keys()
    for key in pc.keys() | phone.keys():
        values = pc.get(key, set()) | phone.get(key, set())
        assert len(values) == 1, f"{key} shows {sorted(values)} (PC {sorted(pc.get(key, ()))}, phone {sorted(phone.get(key, ()))})"


def test_the_shown_figures_equal_their_owner_function(household):
    c, day = household
    shown = _shown(c, False)
    for key, owner in OWNERS.items():
        assert shown.get(key) == {fmt(owner(c, day), 0)}, key


# IT-12AE2: parts add up to their whole.
def _main_text(client, path: str) -> str:
    page = client.get(path).text
    main = re.search(r"<main\b.*?</main>", page, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(main.group(0) if main else page))).replace("−", "-")


def _n(text: str) -> int:
    return int(text.replace(",", "").replace("+", ""))


def test_what_you_own_by_kind_adds_up_to_what_you_own(household):
    from lightning.ui import visuals
    c, day = household
    position = c.position.at(day)
    donut = visuals.holdings_donut(position, include_cash=True)
    assert donut["total"] == position.what_you_own
    assert sum(s["value"] for s in donut["segments"]) == position.what_you_own


def test_safe_to_spend_rows_add_up_to_it(household):
    from lightning.core.money import quantize
    from lightning.ui import visuals
    c, day = household
    forecast = c.forecaster.forecast(day)
    rows = visuals.cash_plan(c, forecast, day)["safe_display_parts"]
    assert sum(value for _, value in rows) == quantize(forecast.safe_to_spend, 0)


def test_the_investments_lead_parts_add_up_to_portfolio_value(household, request):
    c, _ = household
    if request.node.callspec.id == "mohab":
        request.applymarker(pytest.mark.xfail(strict=True, reason="BT-12AC: the Lead leaves out the flat's cost"))
    text = _main_text(_client(c, False), "/investments")
    value = _n(re.search(r"Portfolio value (?:[A-Z][a-z]+ \d{4} )?([\d,]+) EGP", text).group(1))
    cost, gain = re.search(r"Cost ([\d,]+) · Unrealized gain ([+-]?[\d,]+)", text).groups()
    assert abs(_n(cost) + _n(gain) - value) <= 1


def test_the_payday_proposal_lines_add_up_to_the_cash_they_share(household, request):
    c, _ = household
    if request.node.callspec.id == "mohab":
        request.applymarker(pytest.mark.xfail(strict=True, reason="BT-12AD: protected bills sit inside the spending line too"))
    text = _main_text(_client(c, False), "/payday")
    lines = re.search(r"Bills protected ([\d,]+) EGP .*? ([\d,]+) EGP Emergency and goals ([\d,]+) EGP Left unassigned ([\d,]+) EGP", text)
    available = _n(re.search(r"Cash available to assign ([\d,]+)", text).group(1))
    assert abs(sum(_n(x) for x in lines.groups()) - available) <= 2
