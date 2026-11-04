"""Annualized-return uncertainty, checked against independent known-root cash flows."""
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest

from lightning.investments.xirr import RELATIVE_RESIDUAL, XirrStatus, solve_xirr, xirr


def yearly(*amounts):
    return [((date(2025, 1, 1) + timedelta(days=365 * i)).isoformat(), Decimal(a)) for i, a in enumerate(amounts)]


def npv(flows, rate):
    with localcontext() as ctx:
        ctx.prec = 60
        origin = date.fromisoformat(min(day for day, _ in flows))
        discounted = [amount / (1 + rate) ** (Decimal((date.fromisoformat(day) - origin).days) / 365)
                      for day, amount in flows]
        return sum(discounted), sum(abs(a) for a in discounted)


@pytest.mark.parametrize("amounts,roots", [
    (("-100", "230", "-132.16"), ("0.12", "0.18")),
    (("-100", "220.01", "-121.011"), ("0.1", "0.1001")),
    (("-100", "360", "-431", "171.6"), ("0.1", "0.2", "0.3")),
])
def test_multiple_roots_are_ambiguous_without_selecting_a_rate(amounts, roots):
    flows = yearly(*amounts)
    for rate in roots:
        assert abs(npv(flows, Decimal(rate))[0]) < Decimal("1e-50")
    result = solve_xirr(flows)
    assert result.status == XirrStatus.AMBIGUOUS and result.reason == "multiple_roots"
    assert result.rate is None and result.residual is None and xirr(flows) is None


def test_no_root_is_unavailable_rather_than_ambiguous():
    # In discount-factor space: -100 + 50q - 100q² has a negative maximum.
    result = solve_xirr(yearly("-100", "50", "-100"))
    assert result.status == XirrStatus.UNAVAILABLE and result.reason == "no_root"
    assert result.rate is None


@pytest.mark.parametrize("scale", [Decimal("0.000001"), Decimal(1), Decimal("1e12")])
def test_a_unique_nonconventional_root_is_verified_not_blanket_rejected(scale):
    # q³ - 0.8q² + q - 0.8 = (q - 0.8)(q² + 1): the only positive root is q=0.8.
    flows = [(day, amount * scale) for day, amount in yearly("-0.8", "1", "-0.8", "1")]
    result = solve_xirr(flows)
    assert result.status == XirrStatus.CONVERGED
    assert abs(result.rate - Decimal("0.25")) < Decimal("1e-9")
    residual, gross = npv(flows, result.rate)
    assert abs(residual) <= gross * RELATIVE_RESIDUAL
    assert result.residual == residual


def test_unsorted_and_split_same_day_entries_keep_the_same_ambiguity():
    flows = yearly("-100", "230", "-132.16")
    split = [(flows[0][0], Decimal("-40")), (flows[0][0], Decimal("-60")), *flows[1:],
             ("2028-01-01", Decimal("900")), ("2028-01-01", Decimal("-900"))]
    assert solve_xirr(list(reversed(split)), "2030-01-01") == solve_xirr(flows)


def test_a_stationary_root_has_an_explicit_numerical_reason():
    result = solve_xirr(yearly("-100", "220", "-121"))
    assert result.status == XirrStatus.UNAVAILABLE and result.reason == "unstable_root"
    assert result.rate is None


def test_leap_year_spacing_and_report_date_use_actual_cashflow_dates():
    flows = [("2024-01-01", Decimal("-1000")), ("2025-01-01", Decimal("1100"))]
    result = solve_xirr(flows)
    with localcontext() as ctx:
        ctx.prec = 60
        expected = Decimal("1.1") ** (Decimal(365) / 366) - 1
    assert result.rate == expected and result.status == XirrStatus.CONVERGED
    assert solve_xirr(flows, "2030-01-01") == result


def test_extreme_annualization_is_unavailable_without_infinite_or_invalid_rates():
    result = solve_xirr([("2026-01-01", Decimal("-100")), ("2026-01-02", Decimal("110"))])
    assert result.status == XirrStatus.UNAVAILABLE and result.reason == "rate_out_of_range"
    assert result.rate is None


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_input_is_unavailable(bad):
    result = solve_xirr(yearly("-100", bad, "100"))
    assert result.status == XirrStatus.UNAVAILABLE and result.reason == "invalid_cashflow"


def test_large_conventional_histories_still_find_the_known_rate():
    rate, end = Decimal("0.12"), date(2026, 12, 31)
    flows = [((end - timedelta(days=400 - i)).isoformat(), Decimal("-10")) for i in range(300)]
    terminal = sum(-amount * (1 + rate) ** (Decimal((end - date.fromisoformat(day)).days) / 365)
                   for day, amount in flows)
    flows.append((end.isoformat(), terminal))
    result = solve_xirr(flows)
    assert result.status == XirrStatus.CONVERGED and abs(result.rate - rate) < Decimal("1e-8")


def test_complex_histories_fail_closed_at_the_work_limit():
    flows = [((date(2025, 1, 1) + timedelta(days=i)).isoformat(), Decimal("100") * (-1 if i % 2 else 1))
             for i in range(300)]
    result = solve_xirr(flows)
    assert result.status == XirrStatus.UNAVAILABLE and result.reason == "calculation_limit"
