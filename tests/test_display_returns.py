"""The owner's return display policy uses real gain before 365 days, then XIRR."""
from decimal import Decimal as D

from lightning.investments.returns import display_return


def test_short_return_counts_partial_sale_and_income_against_all_purchases():
    flows = [("2026-09-01", D("-1000")), ("2026-09-10", D("600")),
             ("2026-09-15", D("50")), ("2026-09-30", D("550"))]
    shown = display_return(flows, "2026-09-30", D("9"))
    assert (shown.percent, shown.annualized, shown.days_held) == (D("20"), False, 29)


def test_annual_return_starts_at_365_days_and_missing_values_stay_missing():
    flows = [("2025-10-01", D("-1000")), ("2026-10-01", D("1100"))]
    assert not display_return(flows, "2026-09-30", D("0.1")).annualized
    shown = display_return(flows, "2026-10-01", D("0.1"))
    assert (shown.percent, shown.annualized, shown.days_held) == (D("10"), True, 365)
    assert display_return(flows, "2026-10-01", D("0.1"), valued=False).percent is None
    assert display_return([], "2026-10-01", None).percent is None


def test_annual_uncertainty_is_explicit_and_plain_return_does_not_depend_on_it():
    from lightning.investments.xirr import XirrResult, XirrStatus
    flows = [("2024-01-02", D("-100")), ("2025-01-01", D("230")), ("2026-01-01", D("-132.16"))]
    ambiguous = XirrResult(XirrStatus.AMBIGUOUS, reason="multiple_roots")
    unavailable = XirrResult(XirrStatus.UNAVAILABLE, reason="no_root")
    shown = display_return(flows, "2026-01-01", ambiguous)
    assert (shown.percent, shown.status, shown.reason) == (None, "ambiguous", "multiple_roots")
    assert "More than one" in shown.explanation
    missing = display_return(flows, "2026-01-01", unavailable)
    assert (missing.percent, missing.status, missing.reason) == (None, "unavailable", "no_root")
    assert missing.explanation != shown.explanation
    short = display_return(flows[:1] + [("2024-02-01", D("110"))], "2024-02-01", ambiguous)
    assert (short.percent, short.annualized, short.status) == (D("10"), False, "available")
    unpriced = display_return(flows, "2026-01-01", ambiguous, valued=False)
    assert (unpriced.status, unpriced.reason) == ("unavailable", "missing_valuation")
