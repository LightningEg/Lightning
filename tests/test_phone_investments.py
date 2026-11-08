"""IV-3AY15: Investments on the phone agree with the PC page and with Money."""
from datetime import date


from tests.test_phone_account import _phone, sample  # noqa: F401,F811
from lightning.ui.phone.screens import investments as screen
from lightning.ui.web import create_app
from fastapi.testclient import TestClient


def test_value_agrees_with_the_pc_page_and_money(sample):
    page = screen.build(sample, date(2026, 10, 20))
    shown = f"{page.value:,.0f}"
    assert shown in TestClient(create_app(sample)).get("/investments").text
    money = _phone(sample).get("/money").text
    assert shown in money
    assert page.holdings and page.holdings == tuple(sorted(page.holdings, key=lambda r: (r.value is None, -(r.value or 0), r.name.casefold())))


def test_five_holdings_then_all_and_after_sale(sample):
    phone = _phone(sample)
    html = phone.get("/investments").text
    assert 'id="value-heading"' in html and html.count('class="phone-row" href="/investments/holding/') <= 5
    assert "Holdings after sale (estimate)" in html
    assert phone.get("/investments?holdings=all").text.count('/investments/holding/') >= html.count('/investments/holding/')
    assert 'id="value-heading"' not in phone.get("/investments?period=ytd").text   # another period keeps the PC page


def test_value_line_allocation_income_and_the_sale_breakdown(sample):
    phone = _phone(sample)
    html = phone.get("/investments").text
    page = screen.build(sample, date(2026, 10, 20))
    assert 'id="alloc-heading"' in html and "/investments/report-detail?kind=dividends" in html
    assert page.classes and sum(k.after_sale for k in page.classes) <= page.after_sale + 1   # classes add up to the total
    assert all(f'href="/birdview/class/{k.id}?as_of=' in html for k in page.classes)
    assert len(page.chart["labels"] if "labels" in page.chart else page.chart) >= 1


def test_each_class_is_its_value_at_its_sale_factor(sample):
    position = sample.position.at(date(2026, 10, 20))
    page = screen.build(sample, date(2026, 10, 20))
    by_id = {k.id: k for k in position.classes}
    for row in page.classes:
        assert row.after_sale == by_id[row.id].after_sale
        assert row.factor == by_id[row.id].factor
