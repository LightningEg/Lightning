from decimal import Decimal

from lightning.investments.xirr import xirr


def test_xirr_annualizes_one_year_return():
    result = xirr([("2025-01-01", Decimal("-1000")), ("2026-01-01", Decimal("1100"))])
    assert result is not None
    assert abs(result - Decimal("0.10")) < Decimal("0.001")


def test_xirr_returns_none_when_flows_do_not_define_a_rate():
    assert xirr([("2025-01-01", Decimal("-100"))]) is None
    assert xirr([("2025-01-01", Decimal("-100")), ("2025-01-01", Decimal("110"))]) is None


def test_short_irregular_cashflows_match_an_independent_annualized_rate():
    from datetime import date
    rate = Decimal("0.12")
    flows = [("2026-01-01", Decimal("-1000")), ("2026-02-20", Decimal("-500"))]
    end = date(2026, 4, 1)
    terminal = sum(-amount * (1 + rate) ** (Decimal((end - date.fromisoformat(day)).days) / 365)
                   for day, amount in flows)
    result = xirr(flows + [(end.isoformat(), terminal)])
    assert abs(result - rate) < Decimal("0.0000001")


def test_a_later_report_date_cannot_make_same_day_cashflows_define_a_return():
    assert xirr([("2026-01-01", Decimal("-100")), ("2026-01-01", Decimal("100"))],
                "2026-02-01") is None


def test_offsetting_same_day_flows_across_multiple_days_do_not_define_a_return():
    assert xirr([("2026-01-01", Decimal("-100")), ("2026-01-01", Decimal("100")),
                 ("2026-02-01", Decimal("-200")), ("2026-02-01", Decimal("200"))]) is None
