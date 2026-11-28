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
PHONE = ["/home", "/money", "/budget", "/plan"]  # Safe to spend leads Cash planning on both (IV-12P)
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


def test_the_investments_lead_parts_add_up_to_portfolio_value(household):
    c, _ = household
    text = _main_text(_client(c, False), "/investments")
    value = _n(re.search(r"Portfolio value (?:[A-Z][a-z]+ \d{4} )?([\d,]+) EGP", text).group(1))
    cost, gain, valued = re.search(r"Cost ([\d,]+) · Unrealized gain ([+-]?[\d,]+)(?: · Valued by you ([\d,]+))?", text).groups()
    assert abs(_n(cost) + _n(gain) + _n(valued or "0") - value) <= 1  # BT-12AC: what has no cost or price is its own part


def test_the_payday_proposal_lines_add_up_to_the_cash_they_share(household):
    c, _ = household
    text = _main_text(_client(c, False), "/payday")
    lines = re.search(r"Bills protected ([\d,]+) EGP .*? ([\d,]+) EGP Emergency and goals ([\d,]+) EGP Left unassigned ([\d,]+) EGP", text)
    available = _n(re.search(r"Cash available to assign ([\d,]+)", text).group(1))
    assert abs(sum(_n(x) for x in lines.groups()) - available) <= 2


def test_overdrawn_account_reconciles_with_owned_asset_on_home(c):
    from lightning.transactions.domain import TxnSource

    bank = c.account_flows.open_account("Current account", "BANK", "2026-09-01", "100")
    c.account_flows.open_account("Flat", "OTHER_ASSET", "2026-09-01", "1000")
    c.transactions.record_outflow("2026-09-02", bank.id, "300", c.categories.get_by_code("EXP.PERSONAL.FOOD").id,
                                  source=TxnSource.IMPORT)
    html = TestClient(create_app(c)).get("/?month=2026-09").text
    figure = html.split('class="chart chart-donut"', 1)[1].split("</figure>", 1)[0]
    assert "chart-donut-ring" not in figure
    assert "−200" in figure and "1,000" in figure and "800 EGP" in figure


# IT-7BB (r40 F7, F9, F10, F11; r41 M1): one month, one story. Each "what is left" figure has one name and one value
# on Home, Budget, Plan, the Overview and the payday step, on both surfaces.
def test_one_month_one_story_each_figure_one_name_one_value(household):
    c, day = household
    f, e = c.forecaster.forecast(day), c.forecaster.everyday(day.isoformat()[:7], day)
    pc, phone = _client(c, False), _client(c, True)
    safe, free = fmt(f.safe_to_spend, 0), fmt(f.free_cash, 0)

    plan = _main_text(phone, "/plan")  # 1: "you keep" is Safe to spend, never Free cash under another name
    kept = re.findall(r"you keep ([\d,]+) safe to spend", plan, re.I)
    assert kept in ([], [safe]) and f"keep {free}" not in plan
    assert "Going out" not in plan and "Bills and loans · 30 days" in plan  # 2: named for what it holds

    planned, everyday_plan = set(), set()  # 3: Planned is the whole plan everywhere; the everyday part has its own name
    for client, path in ((pc, "/"), (pc, "/budget"), (phone, "/budget"), (phone, "/home")):
        text = _main_text(client, path)
        planned |= set(re.findall(r"(?:How it adds up Planned|of) ([\d,]+) (?:planned|Spent)", text))
        planned |= set(re.findall(r"How it adds up Planned ([\d,]+)", text))
        everyday_plan |= set(re.findall(r"Everyday plan ([\d,]+)", text))
    assert planned == {fmt(e.planned, 0)}, planned
    assert everyday_plan <= {fmt(e.everyday_plan, 0)}, everyday_plan

    cards = _main_text(pc, "/plan")  # 4: Lowest point ahead only when it is not Safe to spend again
    assert ("Lowest point ahead" in cards) == (not f.lowest_repeats_safe_to_spend or f.lowest is None)

    page = pc.get("/payday").text  # 5: the payday figures in one line each from Free cash and Safe to spend
    lines = {k: html.unescape(re.sub(r"<[^>]+>", "", v)) for k, v in re.findall(r'data-relation="(\w+)">(.*?)</p>', page, re.S)}
    if c.funding.preview(day)["available"] is not None:
        assert lines["available"].split(" = ")[1].startswith(f"Free cash {free}")
        assert lines["unassigned"].split(" = ")[1].startswith(f"Safe to spend today {safe}")
        for line in lines.values():
            total, rows = line.replace("EGP", "").split(" = ")
            terms = re.findall(r"(^|[+−]) ?[^+−\d]*?([\d,]+)", rows.strip())
            assert sum(_n(v) * (-1 if s == "−" else 1) for s, v in terms) == _n(total.split()[-1]), line


def test_reserves_count_the_same_for_free_cash_and_the_payday_step(household):
    """A reserve made on a pinned day counts from that day: Free cash and the payday step hold the same reserves."""
    c, day = household
    assert c.position.at(day).reserves == c.funding.preview(day)["reserved"]


def test_the_payday_proposal_protects_gameya_instalments_as_safe_to_spend_does(tmp_path, monkeypatch):
    from datetime import date
    from lightning.bootstrap import build
    from lightning.planning.funding import GAMEYA_BEFORE_PAYDAY
    from lightning.samples import load_mohab_2026
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-01")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "gameya.db")
    load_mohab_2026(c)
    day = date(2026, 11, 1)
    instalments = c.forecaster.forecast(day).taken_off(GAMEYA_BEFORE_PAYDAY)
    preview = c.funding.preview(day)
    assert instalments > 0 and preview["gameya"] == instalments
    page = _client(c, False).get("/payday").text
    assert GAMEYA_BEFORE_PAYDAY.replace("'", "&#39;") not in page and "Gam&#x27;eya instalments before" not in page
    c.db.close()


def test_safe_to_spend_says_expected_by_payday_only_when_it_differs(household):
    """r40 F18: with no income before payday, Expected by payday is Safe to spend again; the card names the day."""
    c, day = household
    f = c.forecaster.forecast(day)
    home = _main_text(_client(c, False), "/")
    shown = f"Expected by payday {fmt(f.expected_by_payday, 0)} on" in home
    assert shown == (not f.expected_repeats_safe_to_spend)
    assert "On top of your plan" not in _main_text(_client(c, False), "/plan")
