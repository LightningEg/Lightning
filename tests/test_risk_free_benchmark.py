"""NF-9E: the same money on the same dates at a typed risk-free rate."""
from datetime import date
from decimal import Decimal

import pytest

from lightning.investments import benchmark as b

D = Decimal


def _history(*rows):
    return b.parse_history(b.dump_history([(date.fromisoformat(d), D(p) / 100) for d, p in rows]))


def test_a_rate_holds_until_a_later_one_is_typed():
    history = _history(("2026-01-01", "20"), ("2026-07-01", "25"))
    assert b.rate_on(history, date(2025, 12, 31)) is None
    assert b.rate_on(history, date(2026, 6, 30)) == (date(2026, 1, 1), D("0.2"))
    assert b.rate_on(history, date(2027, 3, 1)) == (date(2026, 7, 1), D("0.25"))  # last month's value carries forward


def test_one_year_at_a_fixed_rate_earns_that_rate():
    result = b.benchmark([("2026-01-01", D("-1000"))], D("1300"), "2027-01-01", _history(("2026-01-01", "20")))
    assert result.value == pytest.approx(D("1200"), abs=D("0.000001"))
    assert result.gap == pytest.approx(D("100"), abs=D("0.000001"))
    assert result.rate == pytest.approx(D("0.2"), abs=D("0.000001"))


def test_a_rate_change_in_the_middle_is_followed_and_a_withdrawal_comes_off():
    history = _history(("2026-01-01", "10"), ("2027-01-01", "20"))
    flows = [("2026-01-01", D("-1000")), ("2027-01-01", D("100"))]
    result = b.benchmark(flows, D("1000"), "2028-01-01", history)
    assert result.value == pytest.approx((D("1000") * D("1.1") - D("100")) * D("1.2"), abs=D("0.000001"))
    assert result.latest_rate == D("0.2") and result.latest_since == date(2027, 1, 1)


def test_nothing_is_guessed_before_the_first_typed_rate_or_without_a_value():
    history = _history(("2026-06-01", "20"))
    assert b.benchmark([("2026-01-01", D("-100"))], D("120"), "2027-01-01", history) is None
    assert b.benchmark([("2026-07-01", D("-100"))], None, "2027-01-01", history) is None
    assert b.benchmark([("2026-07-01", D("-100"))], D("120"), "2027-01-01", []) is None
    assert b.benchmark([], D("120"), "2027-01-01", history) is None


def test_set_and_remove_a_rate_and_reject_nonsense():
    raw = b.set_rate(None, "2026-01-01", "27,5")
    raw = b.set_rate(raw, "2026-01-01", "28")  # same day replaces
    raw = b.set_rate(raw, "2025-06-01", "20")
    assert [(d.isoformat(), r) for d, r in b.parse_history(raw)] == [("2025-06-01", D("0.2")), ("2026-01-01", D("0.28"))]
    assert [d.isoformat() for d, _ in b.parse_history(b.remove_rate(raw, "2025-06-01"))] == ["2026-01-01"]
    for bad in ("abc", "-1", "5000", "nan"):
        with pytest.raises(ValueError):
            b.set_rate(raw, "2026-02-01", bad)
    assert b.parse_history("not json") == [] and b.parse_history(None) == []


def _client(c):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    return TestClient(create_app(c))


@pytest.fixture
def held(c, setup):
    accounts, _ = setup
    comi = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-01-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    c.investments.buy_total("2026-01-05", accounts["thndr"].id, comi.id, "10", "1000")
    c.assets.set_price(comi.id, "2026-09-30", "130")
    return c, comi


def test_holding_page_asks_for_a_rate_then_compares_and_follows_a_newer_one(held):
    c, comi = held
    client = _client(c)
    url = f"/investments/holding/{comi.id}?date=2026-09-30"
    page = client.get(url).text
    assert "Type the yearly rate of a T-bill" in page and "Ahead of the risk-free rate" not in page
    posted = client.post("/investments/risk-free-rate", data={"day": "2026-01-01", "percent": "20", "return_to": url},
                         follow_redirects=False)
    assert posted.status_code == 303 and posted.headers["location"].endswith("#risk-free") or "#risk-free" in posted.headers["location"]
    page = client.get(url).text
    assert "risk-free rate" in page and "Using 20.00% a year, typed for 1 Jan" in page
    assert "Ahead of the risk-free rate" in page or "Behind the risk-free rate" in page
    client.post("/investments/risk-free-rate", data={"day": "2026-06-01", "percent": "25", "return_to": url})
    assert "Using 25.00% a year, typed for 1 Jun" in client.get(url).text
    client.post("/investments/risk-free-rate", data={"action": "remove", "day": "2026-06-01", "return_to": url})
    assert "Using 20.00% a year, typed for 1 Jan" in client.get(url).text


def test_a_rate_starting_after_the_first_cash_flow_says_so_and_bad_input_is_refused(held):
    c, comi = held
    client = _client(c)
    url = f"/investments/holding/{comi.id}?date=2026-09-30"
    client.post("/investments/risk-free-rate", data={"day": "2026-06-01", "percent": "20", "return_to": url})
    assert "Your first typed rate is for 1 Jun" in client.get(url).text
    refused = client.post("/investments/risk-free-rate", data={"day": "2026-07-01", "percent": "abc", "return_to": url},
                          follow_redirects=False)
    assert "msg=" in refused.headers["location"]
    assert [d.isoformat() for d, _ in b.parse_history(c.settings.get(b.SETTING_KEY))] == ["2026-06-01"]
    outside = client.post("/investments/risk-free-rate", data={"day": "2026-07-01", "percent": "20", "return_to": "//evil.test"},
                          follow_redirects=False)
    assert outside.headers["location"].startswith("/investments")
