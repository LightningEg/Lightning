"""IV-3H step 2, weekly friction: act from the holding (IN-8), give money back (HO-1), no history from too few months
(X-5), an overspend in proportion (BU-2), the gam'eya in the next 30 days (CP-3),
month lines in a register (RG-1), gold priced from another karat (PR-2), system categories kept (CA-3)."""
import re
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.core.dates import fmt_date, today
from lightning.ui.web import create_app
from test_gameya_screens import _circle


def _held_rows(c):
    return {row["owner"]: row for row in c.reporting.money_from_others_by_owner(today())}


def test_held_for_others_rows_give_back_and_spend_for_them(c, setup):
    accounts, cats = setup
    c.counterparties.create("Mom", kind="PERSON")
    c.money_from_others.record(fmt_date(today()), "Mom", accounts["cib"].id, Decimal("1000"))
    client = TestClient(create_app(c))
    page = client.get("/money-from-others").text
    links = re.findall(r'href="(/accounts/\d+/transaction/new\?[^"]+)"', page)
    assert len(links) == 3 and "Give back" in page and "Spend for them" in page and "Receive more" in page
    sheet = client.get(links[0].replace("&amp;", "&")).text
    assert re.search(r'<option value="\d+" selected>Mom', sheet)  # the person is chosen in Held for
    assert 'value="1000.00"' in sheet


def test_holding_page_acts_with_its_account_and_asset(c, setup):
    accounts, _ = setup
    asset = c.assets.create_investment("Test Fund", "STOCK", "TFD")
    c.assets.set_price(asset.id, fmt_date(today()), "10")
    c.investments.add_holding(accounts["thndr"].id, asset.id, "5", "50", fmt_date(today()))
    page = TestClient(create_app(c)).get(f"/investments/holding/{asset.id}?account={accounts['thndr'].id}").text
    for kind in ("buy", "sell", "dividend"):
        assert f"/investments/new?kind={kind}&amp;account={accounts['thndr'].id}&amp;asset={asset.id}" in page
    assert f"#asset-{asset.id}" in page and "Buy more" in page
    assert "holding-few-months" in page and "How bumpy" not in page  # X-5: one month, no history to draw


def test_a_small_overspend_is_a_rose_bar_not_a_needs_you_row(c, setup):
    """BU-2: 50 over a 10,000 plan reads rose on its bar; 600 over raises Needs you."""
    accounts, cats = setup
    month = fmt_date(today())[:7]
    food, fun = cats["EXP.PERSONAL.FOOD"], cats.get("EXP.PERSONAL.ENTERTAINMENT") or cats["EXP.PERSONAL.FOOD"]
    c.budgets.set_budget(food.id, month, "10000", schedule=c.schedules.view())
    c.transactions.record_outflow(fmt_date(today()), accounts["cib"].id, "10050", food.id)
    client = TestClient(create_app(c))
    name = food.name.replace("&", "&amp;")
    assert f"{name} is 50 over its plan" not in client.get(f"/budget?month={month}").text
    c.transactions.record_outflow(fmt_date(today()), accounts["cib"].id, "550", food.id)
    assert f"{name} is 600 over its plan" in client.get(f"/budget?month={month}").text


def test_the_gameya_is_in_the_next_30_days(c, setup):
    circle = _circle(c, setup, first_date=fmt_date(today()), my_turn=10)
    page = TestClient(create_app(c)).get("/plan").text
    assert f'/gameya/{circle.id}"' in page  # due today: the calendar opens on its day


def test_register_has_month_lines_with_the_closing_balance(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "100", food.id)
    c.transactions.record_outflow("2026-10-10", accounts["cib"].id, "200", food.id)
    page = TestClient(create_app(c)).get(f"/accounts/{accounts['cib'].id}").text
    months = re.findall(r'class="register-month"><td colspan="\d+"><b>([A-Z][a-z]+ \d{4})</b>', page)
    assert months[:2] == ["October 2026", "September 2026"] and "Closing balance" in page


def test_an_unpriced_karat_is_priced_from_another_by_purity(c):
    refs = {r["purity_e6"]: r["id"] for r in c.reporting.valuer.q.gold_references()}
    k21, k18 = refs.get(875000), refs.get(750000)
    assert k21 and k18  # the catalogue seeds 18K, 21K and 24K references
    c.assets.set_price(k21, "2026-09-01", "4200")
    derived = c.reporting.valuer.reference_price(k18, "2026-09-02")
    assert Decimal(derived["price_e6"]) / Decimal(1_000_000) == Decimal("3600")  # 4,200 × 18/21
    assert derived["source"] == "21K by purity"
    c.assets.set_price(k18, "2026-09-01", "3500")  # a typed 18K price wins
    assert c.reporting.valuer.reference_price(k18, "2026-09-02")["price_e6"] == 3_500_000_000


def test_system_categories_offer_no_archive_or_delete(c, setup):
    page = TestClient(create_app(c)).get("/categories").text
    system = [cat for cat in c.categories.tree() if cat.is_system and not cat.is_root]
    for cat in system:
        assert f'aria-label="Archive {cat.name}"' not in page and f'aria-label="Delete {cat.name}"' not in page


def test_one_bill_sheet_opens_from_recurring_and_the_next_30_days(c, setup):
    """3G6, the bill half: a bill's sheet says what is due, its next date and its last payments, with Mark paid."""
    accounts, cats = setup
    bill = c.planning.create(kind="BILL", name="Internet", amount="650", frequency="MONTHLY",
                             start_date=fmt_date(today()), account_id=str(accounts["cib"].id),
                             category_id=str(cats["EXP.PERSONAL.FOOD"].id))
    bill_id = bill if isinstance(bill, int) else bill.id
    client = TestClient(create_app(c))
    sheet = client.get(f"/plan/items/{bill_id}/sheet").text
    assert "bill-sheet" in sheet and "Internet" in sheet and "650" in sheet
    assert f"/plan/items/{bill_id}/pay?due={fmt_date(today())}" in sheet  # due today: Mark paid on its row
    assert f"/plan/items/{bill_id}/sheet" in client.get("/plan/recurring").text
    assert f"/plan/items/{bill_id}/pay?due={fmt_date(today())}" in client.get("/plan").text  # NF-7AR: the calendar's day list
