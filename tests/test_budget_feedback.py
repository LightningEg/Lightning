from lightning.ui.routes.register import _budget_feedback


def test_saving_past_a_budget_says_over_not_a_negative_left(c, setup):
    accounts, _ = setup
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.budgets.set_budget(food.id, "2026-11", "1000", schedule=c.schedules.view())
    inside = c.transactions.record_outflow("2026-11-12", accounts["cib"].id, "400", food.id)
    assert "600.00 EGP left this month" in _budget_feedback(c, inside)
    past = c.transactions.record_outflow("2026-11-13", accounts["cib"].id, "800", food.id)
    text = _budget_feedback(c, past)
    assert "200.00 EGP over this month" in text and "-" not in text and "left" not in text
