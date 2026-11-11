"""IV-12P: one name, one figure across Budget, Cash planning and Home, on the PC and the phone.

Each label below is read on every page that shows it, on both apps over one database for one day; a label with two
values fails. (r32 N2-N5: Left in plan was 6,598 and 5,468; Home's Safe to spend sat on a budget caption; Scenarios'
lowest point was not the plan's; Cash planning led with a different figure on each device.) Dummy data only."""
from __future__ import annotations

import html as html_lib
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.demo import build_demo
from lightning.samples import load_mohab_2026
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app

LABELS = ("Left in plan", "Left for everyday", "Safe to spend", "Lowest point ahead", "Due before payday",
          "Not yet given a job", "Plan leaves to save")
PC = ("/", "/budget", "/plan", "/plan/scenarios")
PHONE = ("/home", "/budget/flexible", "/budget", "/plan", "/plan/scenarios")
NUMBER = re.compile(r"^[+−-]?\d[\d,]*$")


def _tokens(page: str) -> list[str]:
    page = re.sub(r"(?s)<(script|style|template|thead)\b.*?</\1>", " ", page)   # a column heading is not a figure
    main = re.search(r"(?s)<main\b.*?</main>", page)
    text = re.sub(r"<[^>]+>", " | ", main.group(0) if main else page)
    text = html_lib.unescape(text).replace("⁦", "").replace("⁩", "")
    return [t.strip() for t in text.split("|") if t.strip()]


def _figures(tokens: list[str]) -> list[tuple[str, str]]:
    """(label, the figure after it) for every token that is exactly a label. Only a chip with a number in it ("22 days
    left", "until 2026-12-01") may sit between; a word (a category's name under a column heading) means the label is
    a heading or follows its figure, and is skipped."""
    found = []
    for i, token in enumerate(tokens):
        if token in LABELS:
            for after in tokens[i + 1:i + 4]:
                after = after.replace("EGP", "").strip()
                if not NUMBER.match(after) and not re.search(r"\d", after):
                    break
                if NUMBER.match(after):
                    # a working row shows a deduction as negative: the figure is its size
                    found.append((token, after.lstrip("+−-")))
                    break
    return found


def _client(c, phone: bool) -> TestClient:
    app = create_app(c)
    if not phone:
        return TestClient(app)
    mount_phone(app)

    async def phone_app(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    return TestClient(phone_app)


def _values(c) -> dict[str, dict[str, set[str]]]:
    seen: dict[str, dict[str, set[str]]] = {}
    for phone, pages in ((False, PC), (True, PHONE)):
        client = _client(c, phone)
        for path in pages:
            response = client.get(path)
            assert response.status_code == 200, path
            for name, value in _figures(_tokens(response.text)):
                seen.setdefault(name, {}).setdefault(value, set()).add(("phone:" if phone else "pc:") + path)
    return seen


@pytest.mark.parametrize("household,day", [("demo", "2026-11-09"), ("sample", "2026-10-21")])
def test_each_label_has_one_value_on_both_apps(c, monkeypatch, household, day):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", day)
    build_demo(c) if household == "demo" else load_mohab_2026(c)
    seen = _values(c)
    twice = {name: {value: sorted(pages) for value, pages in values.items()}
             for name, values in seen.items() if len(values) > 1}
    assert not twice, twice
    assert {"Safe to spend", "Left in plan"} <= set(seen)


def test_home_leads_with_left_for_everyday_and_cash_planning_with_safe_to_spend(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-09")
    build_demo(c)
    day = date(2026, 11, 9)
    everyday = c.forecaster.everyday("2026-11", day)
    phone = _client(c, True)
    home = _tokens(phone.get("/home").text)
    hero = home[home.index("Left for everyday") + 1:]
    if hero[0].startswith("Safe to spend"):   # the note on the label's right opens Cash planning
        hero = hero[1:]
    assert hero[0] == f"{everyday.everyday_left:,.0f}"
    assert any(t.startswith(f"About {everyday.per_day:,.0f} a day") for t in home)   # the line is the hero's own idea
    plan = _tokens(phone.get("/plan").text)
    pc_plan = _tokens(_client(c, False).get("/plan").text)
    first = lambda tokens: next(t for t in tokens if t in LABELS)                     # noqa: E731
    assert first(plan) == first(pc_plan) == "Safe to spend"


def test_a_scenario_purchase_moves_the_plans_lowest_point_by_its_amount(c, monkeypatch):
    from lightning.planning.scenarios import compare_scenario
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-09")
    build_demo(c)
    day = date(2026, 11, 9)
    account = next(a for a in c.accounts.list(active_only=True) if a.account_type.value == "BANK")
    base = compare_scenario(c.forecaster, day, date(2027, 2, 7))
    moved = compare_scenario(c.forecaster, day, date(2027, 2, 7), purchase="1000", purchase_date="2026-11-10",
                             account_id=str(account.id))
    assert base.plan_low.closing == c.forecaster.forecast(day).lowest.closing == base.scenario_plan_low[1]
    assert moved.scenario_plan_low[1] == base.plan_low.closing - 1000
