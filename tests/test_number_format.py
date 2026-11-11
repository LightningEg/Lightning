"""Screen comparisons share the signed percentage formatter, including near zero."""
from decimal import Decimal as D
from html.parser import HTMLParser
import re

import pytest
from fastapi.testclient import TestClient

from lightning.core.money import signed_pct
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


@pytest.mark.parametrize("value,expected", [
    ("-89.5", "−89.5"), ("6.2", "+6.2"), ("0", "0.0"),
    ("-0.04", "0.0"), ("0.04", "0.0"),
])
def test_signed_percentages_use_a_true_minus_and_no_signed_zero(value, expected):
    assert signed_pct(D(value)) == expected


class KpiText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_card = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "article" and "kpi-card" in dict(attrs).get("class", "").split():
            self.in_card = True

    def handle_endtag(self, tag):
        if tag == "article":
            self.in_card = False

    def handle_data(self, data):
        if self.in_card:
            self.parts.append(data)


def test_overview_kpi_comparisons_never_show_hyphen_before_a_number(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-12-31")
    load_mohab_2026(c)
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    response = TestClient(create_app(c)).get("/?period=month&month=2026-09")
    assert response.status_code == 200
    parser = KpiText()
    parser.feed(response.text)
    text = " ".join(parser.parts)
    assert re.search(r"−\d[\d,.]* points", text), text
    assert not re.search(r"(?<!\d)-\d", text), text


def test_pc_register_rows_show_piastres_only_when_there_are_any(c, setup, monkeypatch):
    """A06.1 (owner, 2026-11-08, IV-3BK6): rows drop ".00" on the PC as on the phone; piastres show when there are any."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    accounts, _ = setup
    utilities = c.categories.get_by_code("EXP.PERSONAL.UTILITIES").id
    c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "12000", utilities, counterparty="Landlord")
    c.transactions.record_outflow("2026-09-11", accounts["cib"].id, "3250.75", utilities, counterparty="Vodafone")
    page = TestClient(create_app(c)).get("/transactions").text
    assert "−12,000<" in page.replace("</span>", "<") and "−3,250.75" in page
    assert "−12,000.00" not in page
