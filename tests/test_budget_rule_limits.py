import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app


def test_an_absurd_budget_is_refused_and_a_blank_field_says_it_cleared(c, setup):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    with pytest.raises(ValidationError):
        c.budgets.set_budget(food.id, "2026-11", "99999999999", schedule=c.schedules.view())
    c.budgets.set_budget(food.id, "2026-11", "100000000", schedule=c.schedules.view())  # the limit itself is allowed
    client = TestClient(create_app(c), base_url="http://127.0.0.1", follow_redirects=False)
    cleared = client.post(f"/budget/rule/{food.id}", data={"rule": "", "month": "2026-11"})
    assert "cleared" in cleared.headers["location"].lower()
    refused = client.post(f"/budget/rule/{food.id}", data={"rule": "99999999999", "month": "2026-11"})
    assert "not%20realistic" in refused.headers["location"]
