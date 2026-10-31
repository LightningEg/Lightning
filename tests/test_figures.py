"""One name and one calculation per figure: every tab reads the same position and income average."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from lightning.core.figures import FIGURES, RETIRED_NAMES
from lightning.ui.web import create_app

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "lightning" / "ui" / "templates"


def _household(c, setup):
    accounts, cats = setup
    c.transactions.record_transfer("2026-12-05", accounts["cib"].id, accounts["thndr"].id, "10000")
    thndr = accounts["thndr"]
    entry = {"price_basis": "total", "fees": "", "fees_included": "1"}
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    client.post(f"/accounts/{thndr.id}/investment-entry", data={**entry, "date": "2026-12-06",
                "instrument_key": "catalog:COMI", "units": "100", "total": "7000", "trade_action": "buy"})
    c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.transactions.record_inflow("2026-11-01", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.reserves.set_emergency_fund("6000")
    c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY", start_date="2026-12-20")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2027-01-05",
                      payment_count="4")
    return client


def test_derived_figures_are_formulas_of_base_figures(c, setup):
    _household(c, setup)
    p = c.position.at(date(2026, 12, 31))
    assert p.what_you_own == p.cash_you_own + p.holdings_value + p.other_you_own   # deposits are holdings
    assert p.what_you_own == c.reporting.net_worth("2026-12-31").total
    assert p.cash_you_own == c.reporting.owned_liquid_cash("2026-12-31") == p.bank_and_wallet_cash + p.brokerage_cash
    assert p.deposits == Decimal("5000") and p.brokerage_cash == Decimal("3000")
    # Audit 2026-10-15: brokerage cash is kept apart from spendable cash by default; If you sold today keeps it.
    assert p.kept_apart == p.brokerage_cash == c.reporting.owned_cash_kept_apart("2026-12-31")
    assert p.free_cash == p.cash_you_own - p.kept_apart - p.reserves - p.bills_due
    assert p.bills_due == Decimal("650") and p.loans_still_to_pay == Decimal("10000")
    assert p.what_you_owe == Decimal("10650")
    assert p.net_worth == p.what_you_own - p.what_you_owe
    assert p.portfolio_value == p.holdings_value   # owner decision 2026-10-04: brokerage cash is not portfolio
    assert p.holdings_value >= p.deposits and p.holdings_after_sale >= p.deposits_after_sale
    assert p.if_you_sold_today == p.free_cash + p.kept_apart + p.holdings_after_sale
    assert p.in_your_accounts == p.what_you_own + p.held_for_others


def test_every_tab_shows_the_same_free_cash_and_holdings_after_sale(c, setup):
    client = _household(c, setup)
    p = c.position.at(date(2026, 12, 31))
    free, after_sale = f"{p.free_cash:,.0f}", f"{p.holdings_after_sale:,.0f}"  # reporting pages round to the unit
    for page in ("/", "/birdview", "/plan/reserves"):
        assert free in client.get(page).text, page
    # Investments used to add holdings at full value (no sale factor); it now uses Birdview's factors.
    assert p.holdings_after_sale == p.holdings_value * Decimal("0.95")
    assert after_sale in client.get("/investments").text
    assert "How is this worked out?" not in client.get("/").text  # names explain themselves


def test_one_average_monthly_income_for_budget_reserves_and_forecast(c, setup):
    c.budgets.set_emergency_basis("income")
    client = _household(c, setup)
    income = c.budgets.income_average("2026-12")
    assert income.amount == Decimal("30000.00") and income.months_counted == 2
    assert c.budgets.budgeting_income("2026-12") == income.amount
    assert c.forecaster.forecast(date(2026, 12, 31)).average_income == income.amount
    page = client.get("/plan/reserves").text
    assert "Average monthly income" in page and "0.2 months" in page  # 6,000 ÷ 30,000


def test_formulas_only_use_names_from_the_table():
    labels = sorted((f.label for f in FIGURES.values()), key=len, reverse=True)
    for figure in FIGURES.values():
        rest = figure.formula
        for name in labels:
            rest = rest.replace(name, "")
        rest = re.sub(r"\b(last month|at the end|at the start|the day before the start|of each class|its sale factor|"
                      r"sale factor|other than loan payments|before next income|this month|Payments|Units)\b", "", rest)
        leftover = re.sub(r"[\s+−÷×Σ()]", "", rest)
        assert not leftover, f"{figure.key}: {figure.formula!r} uses a name that is not in the table ({leftover})"


def test_glossary_section_is_generated_from_the_registry_and_every_function_exists():
    import importlib
    from lightning.core.figures import END, START, glossary_markdown
    glossary = (ROOT / "ai" / "GLOSSARY.md").read_text(encoding="utf-8")
    section = glossary.split(START, 1)[1].split(END, 1)[0]
    assert section.strip() == glossary_markdown().strip(), "run: python -m lightning.core.figures"
    for figure in FIGURES.values():
        assert figure.layer in ("Ledger", "Plan", "Ledger + Plan"), figure.key
        parts = figure.function.split(".")
        for cut in range(len(parts) - 1, 0, -1):  # longest importable module prefix, then attributes
            try:
                target = importlib.import_module(".".join(parts[:cut]))
                break
            except ModuleNotFoundError:
                continue
        for attribute in parts[cut:]:
            fields = getattr(target, "__dataclass_fields__", {})
            target = fields[attribute] if attribute in fields else getattr(target, attribute)
        assert target is not None, figure.function


def test_glossary_lists_every_figure_and_screens_use_no_retired_name():
    glossary = (ROOT / "ai" / "GLOSSARY.md").read_text(encoding="utf-8")
    for figure in FIGURES.values():
        assert f"**{figure.label}**" in glossary, figure.label
    text = "\n".join(path.read_text(encoding="utf-8") for path in TEMPLATES.rglob("*.html"))
    for retired in RETIRED_NAMES:
        assert f">{retired}<" not in text, retired


def test_a_class_sale_factor_applies_to_its_kinds_until_one_sets_its_own(c):
    funds = c.assets.get_class_by_code("FUND") if hasattr(c.assets, "get_class_by_code") else next(
        x for x in c.assets.list_classes() if x.code == "FUND")
    equity = next(x for x in c.assets.list_classes() if x.code == "FUND.EQUITY")
    gold_fund = next(x for x in c.assets.list_classes() if x.code == "FUND.GOLD")
    for cls in (funds, equity, gold_fund):
        c.investments.set_liquidation_factor(cls.id, "")
    assert c.investments.liquidation_factors()[equity.id] == Decimal(95)  # nothing set: the default
    c.investments.set_liquidation_factor(funds.id, "90")
    factors = c.investments.liquidation_factors()
    assert factors[equity.id] == factors[gold_fund.id] == Decimal(90)  # inherited from Funds
    c.investments.set_liquidation_factor(gold_fund.id, "97")
    factors = c.investments.liquidation_factors()
    assert factors[gold_fund.id] == Decimal(97) and factors[equity.id] == Decimal(90)  # the child overrides
    assert c.investments.sale_factor_sources()[equity.id] == (Decimal(90), funds.id)
    c.investments.set_liquidation_factor(gold_fund.id, "")
    assert c.investments.liquidation_factors()[gold_fund.id] == Decimal(90)
