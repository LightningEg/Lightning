"""The Investments tab on a phone (phone overhaul 2026-10-22, "How is my money growing?"): Portfolio value and one
sentence lead, the month stepper sits under them, one chart card with the Month / YTD / All links, then Holdings as
flat rows (the biggest five, "See all" for every one grouped). The figures are the PC's; the sentence, the line and
the list come from the route. No browser here: tools/phone_check.py measures the widths."""
import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.core.dates import today
from lightning.ui.routes.investments import _phone_hero_line, _phone_value_line, _signed_percent
from lightning.ui.periods import Period

from test_profile_app import create, token


@pytest.fixture(scope="module")
def phone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("phone_invest")
    cfg = Credentials("http://127.0.0.1:9863")
    app = profile_app(cfg, folder / "docs", devices=Devices(folder / "app", port=0), phone=True)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        create(browser)
        page = browser.get("/")
        browser.post("/demo", data={"__session": token(page.text, "__session")})
        yield browser


def _months_ago(n: int) -> tuple[str, str]:
    """(yyyy-mm, its last day) of the month n months before this one."""
    now = today()
    index = now.year * 12 + now.month - 1 - n
    year, month = divmod(index, 12)
    return f"{year}-{month + 1:02d}", f"{year}-{month + 1:02d}-{calendar.monthrange(year, month + 1)[1]:02d}"


def test_the_hero_leads_and_the_stepper_sits_under_it(phone):
    html = phone.get("/investments").text
    hero, stepper = html.index('class="phone-hero has-seam"'), html.index('class="phone-period"')
    chart, holdings = html.index("phone-invest-card"), html.index('id="holdings-heading"')
    assert hero < stepper < chart < holdings  # the PDF's order
    assert "Portfolio value" in html and re.search(r'class="phone-lead">[\d,]+ <small>EGP</small>', html)
    assert re.search(r'class="phone-hero-line">(Up|Down) [\d,]+ this month \([+−][\d.]+%\)\.<', html)
    assert 'class="phone-kpis"' not in html and "<table" not in html  # no tiles, no table
    assert html.count('class="phone-page-actions"') == 1 and "phone-period" not in html.split('class="phone-page-actions"')[1].split("</div>")[0]


def test_one_chart_card_with_three_dates_and_the_period_links(phone):
    html = phone.get("/investments").text
    card = html.split("phone-invest-card")[1].split("</article>")[0]
    assert card.count("chart-marks") == 1 and 'style="height:160px"' in card  # one line, 160 tall
    assert len(re.findall(r'<span style="left:[\d.]+%">\d{4}-\d{2}-\d{2}</span>', card)) == 7  # seven dates drawn, CSS names three
    links = re.findall(r'<a href="(/investments\?[^"]+)"( class="is-chosen")?', card)
    assert [(href.split("period=")[1].split("&")[0], bool(chosen)) for href, chosen in links] == [
        ("month", True), ("ytd", False), ("all", False)]  # the same period system: ?period=month|ytd|all
    assert 'class="phone-invest-seg"' in card and ">Month<" in card and ">YTD<" in card and ">All<" in card


@pytest.mark.parametrize("period, when", [("ytd", "this year"), ("all", "since your first record")])
def test_the_other_ranges_read_in_words(phone, period, when):
    html = phone.get("/investments", params={"period": period}).text
    assert re.search(r'class="phone-hero-line">(Up|Down) [\d,]+ ' + when + r' \(', html)
    assert 'class="is-chosen" aria-current="true">' + {"ytd": "YTD", "all": "All"}[period] in html


def test_a_past_month_names_the_month_and_the_day_it_is_valued(phone):
    month, last_day = _months_ago(1)
    html = phone.get("/investments", params={"period": "month", "month": month}).text
    assert re.search(r'class="phone-hero-line">(Up|Down) [\d,]+ in ' + month + r' \(', html) and f"As of {last_day}" in html


def test_holdings_are_flat_rows_with_see_all_past_five(phone, monkeypatch):
    html = phone.get("/investments").text
    section = html.split('id="holdings-heading"')[1].split("</section>")[0]
    rows = re.findall(r'<a class="phone-txn phone-invest-row" href="([^"]+)">', section)
    assert 1 <= len(rows) <= 5 and all(href.startswith("/investments/holding/") for href in rows)
    assert 'phone-txn-av is-invest' in section and re.search(r"<small>[^<]+ · [+\u2212]?[\d.]+%?[^<]*</small>", section)  # "Gold · +28.3%"
    assert "See all" not in section  # five or fewer: nothing more to see
    monkeypatch.setattr("lightning.ui.routes.investments.PHONE_HOLDINGS_SHOWN", len(rows) - 1)  # more than the page shows
    short = phone.get("/investments").text.split('id="holdings-heading"')[1].split("</section>")[0]
    assert len(re.findall(r'class="phone-txn phone-invest-row"', short)) == len(rows) - 1
    assert re.search(r'href="/investments\?[^"]*holdings=all#holdings-heading">See all<', short)
    assert "phone-invest-views" not in short  # the group chips come with See all
    full = phone.get("/investments", params={"holdings": "all"}).text.split('id="holdings-heading"')[1].split("</section>")[0]
    assert len(re.findall(r'class="phone-txn phone-invest-row"', full)) >= len(rows) and "Show fewer" in full
    assert 'class="phone-invest-views"' in full and ">By account<" in full and "phone-group-head" in full


def test_every_part_of_the_old_page_is_still_here(phone):
    html = phone.get("/investments").text
    for marker in ('id="alloc-heading"', 'id="income-heading"', 'id="horizon-heading"', "Brokerage cash", "Holdings after sale",
                   "Locked certificate", "See them"):
        assert marker in html
    assert ">Holdings</span>" in html and ">Planner<" in html and ">Prices<" in html  # the tab's other pages come from the frame


def test_a_month_before_any_holding_keeps_its_stepper(phone):
    html = phone.get("/investments", params={"period": "month", "month": _months_ago(20)[0]}).text
    assert "No holdings yet" in html and 'class="phone-period"' in html and 'href="/accounts"' in html


def test_the_sentence_is_built_in_python():
    month = Period("month", "Monthly", date(2026, 10, 1), date(2026, 10, 22))
    past = Period("month", "Monthly", date(2026, 9, 1), date(2026, 9, 30))
    up = _phone_hero_line(Decimal("7956"), Decimal("1.94"), month, True, "en")
    assert up == {"text": "Up {amt} {when} ({pct}).", "values": {"amt": "7,956", "when": "this month", "pct": "+1.9%"}}
    down = _phone_hero_line(Decimal("-1200"), Decimal("-0.44"), past, False, "en")
    assert down["text"] == "Down {amt} {when} ({pct})." and down["values"] == {"amt": "1,200", "when": "in 2026-09", "pct": "−0.4%"}
    no_rate = _phone_hero_line(Decimal("500"), None, Period("ytd", "YTD", date(2026, 1, 1), date(2026, 10, 22)), True, "en")
    assert no_rate == {"text": "Up {amt} {when}.", "values": {"amt": "500", "when": "this year"}}
    assert "since your first record" in _phone_hero_line(Decimal("5"), None, Period("all", "All time", date(2026, 1, 5), date(2026, 10, 22)),
                                                          True, "en")["values"]["when"]
    missing = _phone_hero_line(None, None, month, True, "en")  # why, in the page's own words
    assert missing["text"].startswith("A price is missing") and _phone_hero_line(Decimal(0), None, month, True, "en")["text"].startswith("Your holdings")
    assert _signed_percent(Decimal("0.02")) == "0.0%" and _signed_percent(Decimal("-3.26")) == "−3.3%"


@pytest.mark.parametrize("days, drawn", [(0, 0), (1, 0), (2, 3), (4, 5), (6, 7), (29, 7), (400, 7)])
def test_the_line_draws_three_five_or_seven_dates_and_nothing_on_a_day(c, days, drawn):
    start = date(2026, 9, 1)
    period = Period("custom", "Custom", start, start + timedelta(days=days))
    value, line = _phone_value_line(c, period, Decimal(1))
    assert value == 0 and line["count"] == drawn  # an empty profile: zero, then the line or "not enough history"
    assert len(line["labels"]) == drawn and line["too_short"] == (drawn == 0)
    if drawn:
        assert line["labels"][0]["text"] == "2026-09-01" and line["labels"][-1]["text"] == (start + timedelta(days=days)).isoformat()
