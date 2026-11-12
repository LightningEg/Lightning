"""IV-12Q (r32 U2-U5): the unfinished pages of Budget and Cash planning get the page pattern.

12Q2: Compare scenarios and Forecast inputs light the Plan tab; scenarios draws the plan and the change as two lines
with the lowest month marked; inputs is one row per account or currency with one action.
12Q3: Change limit says what was spent with a bar; Fill opened without a source (Fill this month, Give it a job) opens
on a source that has rows; an empty source or carryover says what to do next."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.sections import locate
from lightning.ui.web import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-21")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("q") / "t.db")
        load_mohab_2026(c)
        with TestClient(create_app(c)) as client:
            yield c, client
        c.db.close()


def test_scenarios_and_inputs_light_the_plan_tab():
    for path in ("/plan/scenarios", "/plan/inputs"):
        section, tab = locate(path)
        assert section.key == "plan" and tab.key == "plan", path


def test_scenarios_draws_two_lines_and_marks_the_lowest_month(client):
    c, http = client
    page = http.get("/plan/scenarios?what=purchase&purchase=60000&purchase_date=2026-11-10&account_id=1").text
    assert 'class="card lead-card lead-hero"' in page and "Lowest point ahead" in page
    assert page.count('class="chart-line tone-') == 2          # your plan and with this change
    assert page.count("is-over") >= 1 and "lowest point" in page
    assert "60,000" in page                                     # the change, in the Lead's comparison


def test_inputs_is_one_row_per_subject_with_one_action(client):
    c, http = client
    page = http.get("/plan/inputs").text
    rows = page.count('class="compact-row inputs-row"')
    assert rows and rows == page.count('class="btn small" href=')
    assert "Review inputs" not in page and '<h1>Forecast inputs</h1>' in page


def test_change_limit_shows_spent_with_a_bar(client):
    c, http = client
    food = c.categories.find_by_text("Food & Groceries").id
    page = http.get(f"/budget/category/{food}/edit?month=2026-10").text
    assert "Spent this month" in page and 'class="chart-meter-track"' in page and "Save limit" in page


def test_fill_without_a_source_opens_on_one_that_has_rows(client, monkeypatch):
    c, http = client
    first = http.get("/budget/fill?month=2026-10").text
    assert 'name="selected"' in first or "Saving goals" in first
    # A source with nothing says what to do next instead of an empty table
    empty = http.get("/budget/fill?month=2026-10&source=schedule").text
    if 'name="selected"' not in empty:
        assert "Nothing to copy from here" in empty and "Set limits on Budget" in empty


def test_carryover_off_offers_to_turn_it_on(client):
    c, http = client
    page = http.get("/budget/carryover-bridge?month=2026-10").text
    if "Carryover is off" in page:
        assert 'action="/budget/carryover/global"' in page and "Turn on carryover for every category" in page
    else:
        assert "Carried over" in page


def test_budget_keeps_the_ai_prompt_in_the_menu_and_the_unassigned_row_in_the_lead(client):
    """12Q5 (r32 U8): the prompt sits behind the header's More actions, Not yet given a job under the Lead's answer."""
    c, http = client
    page = http.get("/budget?month=2026-10").text
    menu = page[page.index('class="action-menu budget-ai-menu"'):]
    menu = menu[:menu.index("</details>")]
    assert "data-ai-copy" in menu and "data-ai-edit" in menu
    assert page.count("data-ai-copy") == 1 and 'class="ai-line"' not in page
    lead = page[page.index('class="card lead-card lead-hero"'):]
    lead = lead[:lead.index("</section>")]
    assert "Not yet given a job" in lead and 'id="budget-unassigned"' not in page


def test_budget_settings_offers_spending_categories_only_and_keeps_hidden_choices(client):
    c, http = client
    page = http.get("/settings?section=budget").text
    assert "System Categories" not in page and "Investment Fees" not in page and "Unaccounted" not in page
    assert "Tick a category to leave it out of the budget" in page
    zakat = c.categories.find_by_text("Zakat").id
    c.settings.set("budget_one_off_exclusions", f"[{zakat}]")
    page = http.get("/settings?section=budget").text
    assert f'<input type="hidden" name="exclusion_category" value="{zakat}">' in page   # saving keeps it
