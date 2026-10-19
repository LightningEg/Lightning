"""Two levels, few settings (owner, 2026-10-06): six sections at most, five tabs at most in each, every page
inside one tab, and a tab's settings behind its gear. Addresses stay the same, so old links keep working."""
import re

from fastapi.testclient import TestClient

from lightning.ui.sections import MAX_SECTIONS, MAX_TABS, SECTIONS, locate
from lightning.ui.web import create_app


def test_six_sections_and_five_tabs_at_most():
    assert len(SECTIONS) <= MAX_SECTIONS
    assert all(1 <= len(section.tabs) <= MAX_TABS for section in SECTIONS)
    assert [s.label for s in SECTIONS] == ["Overview", "Budget", "Cash planning", "Investments", "Accounts", "Settings"]


def test_every_page_sits_in_one_tab():
    expected = {
        "/": ("overview", "summary"), "/birdview/expenses": ("overview", "spending"),
        "/financial-health": ("overview", "health"), "/accounts/currencies": ("overview", "currencies"),
        "/budget": ("budget", "budget"),
        "/plan": ("plan", "plan"), "/plan/recurring": ("plan", "recurring"), "/reserves/3/payments": ("plan", "reserves"),
        "/investments": ("investments", "holdings"), "/investments/holding/4": ("investments", "holdings"),
        "/investments/planner": ("investments", "planner"), "/investments/reevaluations": ("investments", "prices"),
        "/accounts/2": ("accounts", "accounts"), "/transactions": ("accounts", "transactions"),
        "/money-from-others": ("accounts", "others"), "/zakat": ("accounts", "zakat"), "/settings": ("settings", "data"),
        "/categories/5/edit": ("settings", "categories"), "/checks": ("settings", "checks"),
    }
    for path, (section, tab) in expected.items():
        found = locate(path)
        assert (found[0].key, found[1].key) == (section, tab), path
    # A Settings page that holds a tab's settings opens under that tab.
    assert locate("/settings", "budget")[1].key == "budget"
    assert locate("/settings", "financial-health")[1].key == "health"
    assert locate("/settings", "zakat")[1].key == "zakat"


def test_the_tab_bar_and_gears_lead_where_they_say(c):
    client = TestClient(create_app(c))
    c.zakat.set_enabled(True)   # Zakat is a tab only once turned on (test_zakat checks it off)
    for section in SECTIONS:
        for tab in section.tabs:
            page = client.get(tab.href)
            assert page.status_code == 200, tab.href
            nav = re.search(r'<nav class="nav"(.*?)</nav>', page.text, re.S).group(1)
            assert f'href="{section.href}" class="active"' in nav, tab.href
            if len(section.tabs) > 1:
                assert re.search(rf'href="{re.escape(tab.href)}" aria-current="page">', page.text), tab.href
            if tab.gear:
                assert f'aria-label="{tab.gear_label}"' in page.text and client.get(tab.gear).status_code == 200


def test_the_stylesheet_has_no_stray_declarations():
    # A rule split over two lines lost its first line on 2026-10-06; the orphan broke every rule after it
    # (the Plan timeline drew over the page). Outside a block there must be selectors only, never "prop: value;".
    from pathlib import Path
    css = re.sub(r"/\*.*?\*/", "", (Path(__file__).parents[1] / "lightning/ui/static/style.css").read_text(), flags=re.S)
    depth, outside = 0, []
    for ch in css:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, "a } with no {"
        elif depth == 0:
            outside.append(ch)
    assert depth == 0
    assert ";" not in "".join(outside), "a declaration outside any rule"


def test_each_reserve_matching_criterion_has_its_own_field(c):
    # Matching criteria are independent; each reveals its own adjacent picker.
    page = TestClient(create_app(c)).get("/plan/reserves").text
    form = page.split('id="add-reserve"', 1)[1].split("</form>", 1)[0]
    assert re.findall(r'type="checkbox" name="match_by" value="(\w+)"', form) == ["none", "account", "counterparty", "category"]
    assert len(re.findall(r"data-match-picker=", form)) == 3 and "<select name=\"match_by\"" not in form
