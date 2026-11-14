"""IV-12AH (#634, owner 2026-11-13): a category left out of the budget is called Outside the budget, Settings says its
subcategories go with it, the page says the spending still counts in Cash flow, and a limit for this month
only says so."""
from tests.screens import _ScreenClient, visible_text
from lightning.ui.web import create_app


def _client(c, locale="en"):
    client = _ScreenClient(create_app(c), "http://testserver")
    if locale != "en":
        client.post("/settings/locale", data={"locale": locale})
    return client


def test_outside_the_budget_names_its_scope_and_where_spending_stays(c, setup):
    accounts, _ = setup
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    eating_out = c.categories.get_by_code("EXP.PERSONAL.DINING")
    c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "900", eating_out.id)
    client = _client(c)
    text = visible_text(client.get("/budget?month=2026-12&open_group=all").text)
    assert "Leave outside the budget" in text and "One-off" not in text
    response = client.post("/budget/one-off", data={"category_id": eating_out.id, "month": "2026-12"})
    assert eating_out.id in c.budgets.one_off_ids()
    c.transactions.record_outflow("2026-12-03", accounts["cib"].id, "400", eating_out.id)
    text = visible_text(client.get("/budget?month=2026-12").text)
    assert "400 EGP spent this month is outside the budget: it still counts in Cash flow and Spending." in text
    assert "Categories outside the budget" in visible_text(client.get("/settings?section=budget").text)
    assert food.id not in c.budgets.one_off_ids()


def test_settings_says_subcategories_go_with_it(c, setup):
    text = visible_text(_client(c).get("/settings?section=budget").text)
    assert "its subcategories go with it. Its spending still counts in Cash flow and Spending." in text


def test_a_limit_for_this_month_only_says_so(c, setup):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.budgets.set_budget(food.id, "2026-12", "3000", only_this_month=True, schedule=c.schedules.view())
    text = visible_text(_client(c).get("/budget?month=2026-12&open_group=all").text)
    assert "This month only" in text
    assert "This month only" not in visible_text(_client(c).get("/budget?month=2027-01&open_group=all").text)


def test_arabic_names_it_too(c, setup):
    text = visible_text(_client(c, "ar").get("/categories").text)
    assert "بره الميزانية" in text and "مرة واحدة" not in text
