"""NF-12AI (#635): Fill opens on What changed. An unchanged month has nothing to do; a limit you set is not replaced by
an average unless you tick it; a past this-month-only limit is never offered as fixed; a new category with history
shows beside an unchanged one."""
from decimal import Decimal

from lightning.ui.web import create_app
from tests.screens import _ScreenClient, visible_text

MONTH = "2026-12"


def _ids(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id


def _page(c, query=""):
    return visible_text(_ScreenClient(create_app(c), "http://testserver").get(f"/budget/fill?month={MONTH}{query}").text)


def test_an_unchanged_month_has_nothing_to_do(c, setup):
    food, _ = _ids(c)
    c.budgets.set_budget(food, "2026-10", "3000", schedule=c.schedules.view())
    proposal = c.budgets.fill_proposal(MONTH, "changes", schedule=c.schedules.view())
    assert proposal.rows == () and proposal.unchanged == 0
    assert "Your plan continues" in _page(c)
    last = c.budgets.fill_proposal(MONTH, "last_month", schedule=c.schedules.view())
    assert all(not row.selectable for row in last.rows)  # nothing to apply on an unchanged row


def test_your_limit_is_kept_unless_you_tick_the_average(c, setup):
    accounts, _ = setup
    food, _ = _ids(c)
    c.budgets.set_budget(food, "2026-09", "400", schedule=c.schedules.view())
    for month in ("2026-09", "2026-10", "2026-11"):
        c.transactions.record_outflow(f"{month}-05", accounts["cib"].id, "550", food)
    [row] = c.budgets.fill_proposal(MONTH, "changes", schedule=c.schedules.view()).rows
    assert (row.category_id, row.amount, row.current_amount, row.selected) == (food, Decimal("550"), Decimal("400"), False)
    assert "Your limit: 400.00 fixed. Tick to use this instead for 2026-12 only." in row.conflict


def test_a_past_exception_is_not_offered_as_fixed(c, setup):
    food, _ = _ids(c)
    c.budgets.set_budget(food, "2026-10", "3000", schedule=c.schedules.view())
    c.budgets.set_budget(food, "2026-11", "9000", only_this_month=True, schedule=c.schedules.view())
    row = next(r for r in c.budgets.fill_proposal(MONTH, "last_month", schedule=c.schedules.view()).rows
               if r.category_id == food)
    assert row.note == "From 2026-11 · for that month only" and not row.selected
    assert all(r.category_id != food for r in c.budgets.fill_proposal(MONTH, "changes", schedule=c.schedules.view()).rows)


def test_a_new_category_shows_beside_an_unchanged_one(c, setup):
    accounts, _ = setup
    food, transport = _ids(c)
    c.budgets.set_budget(food, "2026-10", "1000", schedule=c.schedules.view())
    c.transactions.record_outflow("2026-11-02", accounts["cib"].id, "2000", transport)
    proposal = c.budgets.fill_proposal(MONTH, "changes", schedule=c.schedules.view())
    assert [(r.category_id, r.selected) for r in proposal.rows] == [(transport, True)]
    text = _page(c)
    assert "What changed" in text and "Transportation" in text
