"""NF-7AQ3: Search answers a typed question on the sample year: the figure is Spending's own, the link's filter
returns the same rows, and words it does not understand fall back to today's results."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.bootstrap import build
from lightning.samples import SAMPLE_TODAY, load_mohab_2026
from lightning.ui.web import create_app
from lightning.workflows.answers import answer


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
        c = build(tmp_path_factory.mktemp("answers") / "s.db")
        load_mohab_2026(c)
        yield c
        c.db.close()


def test_food_in_september_is_spendings_own_figure(sample):
    c = sample
    got = answer(c, "food 2026-09", SAMPLE_TODAY)
    spending = {g.code: g.value for g in c.reporting.spending_by_category("2026-09-01", "2026-09-30")}
    assert got["total"] == spending["EXP.PERSONAL.FOOD"] == D("5043.50")
    assert got["before"] == {g.code: g.value for g in c.reporting.spending_by_category("2026-08-01", "2026-08-31")}[
        "EXP.PERSONAL.FOOD"]
    assert got["period"] == "September 2026" and got["count"] == len(got["rows"]) or got["count"] >= len(got["rows"])
    assert got["href"] == f"/transactions?category_id={c.categories.get_by_code('EXP.PERSONAL.FOOD').id}" \
                          "&date_from=2026-09-01&date_to=2026-09-30"


def test_a_payee_with_a_year_and_a_word_that_matches_nothing(sample):
    c = sample
    carrefour = answer(c, "Carrefour 2026", SAMPLE_TODAY)
    assert carrefour["name"] == "Carrefour" and carrefour["total"] > 0 and carrefour["count"] >= len(carrefour["rows"])
    assert answer(c, "zzzz", SAMPLE_TODAY) is None


def test_the_pc_and_phone_search_show_the_answer_first(sample):
    client = TestClient(create_app(sample))
    page = client.get("/search", params={"q": "food last month"}).text
    assert 'class="search-answer"' in page and "Open in Transactions" in page
    assert page.index("search-answer") < page.index("search-group")
    phone = client.get("/search", params={"q": "food last month", "fragment": "1"},
                       headers={"User-Agent": "Mozilla/5.0 (Linux; Android 14) Mobile"}).text
    assert "search-answer" in phone


def test_pc_and_phone_list_the_same_first_payments(sample):
    """NF-7AQ1: one search for both devices; the PC lists payments first, as the phone does."""
    import re
    from lightning.ui.phone.presenters.search import phone_results
    client = TestClient(create_app(sample))
    page = client.get("/search", params={"q": "food"}).text
    pc = re.findall(r'<a class="recent-row" href="/transactions/(\d+)"', page)[:5]
    phone = [str(row.txn_id) for row in phone_results(sample, "food")["payments"][:5]]
    assert pc and pc == phone
    assert page.index("search-group") < page.index('href="/transactions/' + pc[0])
