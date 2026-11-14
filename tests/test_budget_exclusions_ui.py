"""IV-12AH: saved exclusions expose their scope and undo without hiding actual money."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.ui.i18n import translate as tr
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.screens import Screen


def client_for(c, phone, locale):
    app = create_app(c)
    if phone:
        mount_phone(app)

        @app.middleware("http")
        async def phone_frame(request, call_next):
            request.state.phone = True
            return await call_next(request)

    client = TestClient(app)
    client.post("/settings/locale", data={"locale": locale})
    return client


def exclusion_form(page, category_id, action):
    return next(form for form in Screen(page).forms
                if form.action == "/budget/one-off" and form.fields.get("category_id") == str(category_id)
                and form.fields.get("action", "exclude") == action)


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_scope_and_put_back_round_trip_preserve_cash_flow_and_spending(c, setup, phone, locale):
    accounts, _ = setup
    parent = c.categories.create(c.categories.get_by_code("EXP.PERSONAL").id, "Trips")
    children = [c.categories.create(parent.id, name) for name in ("Tickets", "Hotels")]
    other = c.categories.get_by_code("EXP.WORK.SOFTWARE")
    for category in (parent, *children):
        c.transactions.record_outflow("2026-11-05", accounts["cib"].id, "100", category.id)
    client = client_for(c, phone, locale)
    before_cash = c.reporting.cash_flow("2026-11-01", "2026-11-30")
    before_spending = c.budgets.owned_spending(date(2026, 11, 1), date(2026, 11, 30))
    page = client.get(f"/budget/category/{parent.id}/edit?month=2026-11")
    assert tr("and its {n} subcategories", locale, n=2) in Screen(page).text
    assert tr("Leave outside the budget", locale) in Screen(page).text
    form = exclusion_form(page, parent.id, "exclude")
    assert client.post(form.action, data=form.fields).status_code == 200
    # Keep an unrelated saved preference, including across the parent restore.
    client.post("/budget/one-off", data={"category_id": other.id, "month": "2026-11"})
    assert {parent.id, *(child.id for child in children)} <= c.budgets.one_off_ids()
    assert c.reporting.cash_flow("2026-11-01", "2026-11-30") == before_cash
    assert c.budgets.owned_spending(date(2026, 11, 1), date(2026, 11, 30)) == before_spending
    # The choice lasts beyond the month in which it was made.
    page = client.get("/budget?month=2026-12")
    text = Screen(page).text
    assert tr("and its {n} subcategories", locale, n=2) in text
    assert tr("These categories stay outside the budget until you put them back. Their spending still counts in Cash flow and Spending.", locale) in text
    form = exclusion_form(page, parent.id, "restore")
    assert tr("Put back", locale) in form.text
    client.post(form.action, data=form.fields)
    assert c.budgets.one_off_ids(with_children=False) == {other.id}
    assert not {parent.id, *(child.id for child in children)} & c.budgets.one_off_ids()
    assert c.reporting.cash_flow("2026-11-01", "2026-11-30") == before_cash
    assert c.budgets.owned_spending(date(2026, 11, 1), date(2026, 11, 30)) == before_spending


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_month_only_limit_is_labelled_without_changing_next_month(c, setup, phone, locale):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.budgets.set_budget(food.id, "2026-10", "6000", schedule=c.schedules.view())
    c.budgets.set_budget(food.id, "2026-11", "9000", only_this_month=True, schedule=c.schedules.view())
    client = client_for(c, phone, locale)
    urls = ["/budget?month=2026-11", f"/budget/category/{food.id}/edit?month=2026-11"]
    if phone:
        urls.append("/budget/plan?month=2026-11")
    for url in urls:
        page = client.get(url)
        assert page.status_code == 200
        assert tr("Limit for this month only", locale) in Screen(page).text
    next_month = c.budgets.month_view("2026-12", schedule=c.schedules.view())
    line = next(line for section in next_month.sections for line in section.lines if line.category_id == food.id)
    assert line.budget == 6000 and not line.one_off


def test_restore_only_removes_the_selected_explicit_choice_and_invalid_action_does_nothing(c, setup):
    parent = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    child = c.categories.create(parent.id, "Lunch")
    client = client_for(c, False, "en")
    for category in (parent, child):
        client.post("/budget/one-off", data={"category_id": category.id, "month": "2026-11"})
    page = client.get("/budget?month=2026-11")
    assert "and its 1 subcategory" in Screen(page).text
    client.post("/budget/one-off", data={"category_id": parent.id, "month": "2026-11", "action": "invalid"})
    assert c.budgets.one_off_ids(with_children=False) == {parent.id, child.id}
    form = exclusion_form(page, parent.id, "restore")
    client.post(form.action, data=form.fields)
    assert c.budgets.one_off_ids() == {child.id}
