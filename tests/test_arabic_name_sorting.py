"""IT-3BI2: Arabic spelling variants sort by their letters, without changing displayed names."""
from decimal import Decimal
from pathlib import Path
import re

import pytest


NAMES = ["إيمان", "احمد", "Zed", "ahmed"]
ORDERED = ["ahmed", "Zed", "احمد", "إيمان"]


def test_planned_names_fold_arabic_and_keep_kind_groups_and_equal_name_order(c):
    for kind in ("INCOME", "BILL"):
        for name in NAMES:
            c.planning.create(kind=kind, name=name, amount="100", frequency="MONTHLY", start_date="2026-09-01")
    first = c.planning.create(kind="BILL", name="أحمد", amount="100", frequency="MONTHLY", start_date="2026-09-01")
    rows = c.planning.items()
    assert [r.name for r in rows if r.kind.value == "INCOME"] == ORDERED
    bills = [r for r in rows if r.kind.value == "BILL"]
    assert [r.name for r in bills] == ["ahmed", "Zed", "احمد", "أحمد", "إيمان"]
    assert bills[3].id == first
    assert [r.kind.value for r in rows] == ["BILL"] * 5 + ["INCOME"] * 4


@pytest.mark.parametrize("vary", ["owner", "account"])
def test_cash_held_for_others_folds_owner_and_account_names(c, vary):
    category = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    for name in NAMES:
        account = c.account_flows.open_account(name, "BANK", "2026-09-01", "0")
        owner = name if vary == "owner" else "Family"
        receipt = c.transactions.record_in_account(account.id, "2026-09-10", "100", category.id)
        c.money_from_others.sync_transaction(receipt.id, receipt.date, owner, account.id, Decimal("100"))
    rows = c.reporting.money_from_others_by_owner("2026-09-30")
    assert [row["owner" if vary == "owner" else "account_name"] for row in rows] == ORDERED
    assert all(row["amount"] == Decimal("100") for row in rows)


@pytest.mark.parametrize("vary", ["owner", "asset"])
def test_investments_held_for_others_fold_owner_and_asset_names(c, vary):
    account = c.account_flows.open_account("Broker", "BROKERAGE", "2026-09-01", "10000")
    for index, name in enumerate(NAMES):
        asset = c.assets.create_investment(name, "STOCK", f"SORT{index}")
        buy = c.investments.buy_total("2026-09-10", account.id, asset.id, "1", "100")
        c.money_from_others.sync_investment(buy.id, buy.date, name if vary == "owner" else "Family",
                                           account.id, asset.id, Decimal("1"))
    rows = c.reporting.money_from_others_investments("2026-09-30")
    assert [row["owner" if vary == "owner" else "asset_name"] for row in rows] == ORDERED
    assert all(row["units"] == Decimal("1") for row in rows)


def test_browser_name_comparisons_use_the_page_language_and_ignore_accents():
    script = (Path(__file__).parents[1] / "lightning/ui/static/app.js").read_text(encoding="utf-8-sig")
    comparisons = re.findall(r"\.localeCompare\(([^;\n]+?)\)", script)
    assert comparisons
    assert all('document.documentElement.lang, {sensitivity: "base"}' in call for call in comparisons)
