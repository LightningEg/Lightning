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


def test_an_account_answers_its_money_out(sample):
    """NF-7AQ5: "CIB last month" is the account's money out, Spending's own per-account figure."""
    c = sample
    got = answer(c, "CIB last month", SAMPLE_TODAY)
    cib = next(a for a in c.accounts.list() if a.name == "CIB Payroll")
    assert got["name"] == "CIB Payroll"
    assert got["total"] == dict(c.reporting.spending_by_account("2026-09-01", "2026-09-30"))[cib.id] > 0
    assert got["before"] == dict(c.reporting.spending_by_account("2026-08-01", "2026-08-31"))[cib.id]
    assert got["count"] >= len(got["rows"]) > 0 and all(row.amount < 0 for row in got["rows"])
    assert got["href"] == f"/transactions?account_id={cib.id}&date_from=2026-09-01&date_to=2026-09-30"


def test_a_tag_answers_the_money_out_of_its_transactions(sample):
    """NF-7AQ5: "#eid 2026" totals Spending's lines of the transactions the tag marks; without the # the
    words are a category, account or payee first ("eid" is the payee Eidiya)."""
    c = sample
    ids = c.transactions.tag_transaction_ids("eid")
    expected = sum(row["value"] for row in c.reporting.spending_lines("2026-01-01", "2026-12-31")
                   if row["transaction_id"] in ids)
    got = answer(c, "#eid 2026", SAMPLE_TODAY)
    assert got["name"] == "#eid" and got["total"] == expected > 0
    assert all(row.id in ids for row in got["rows"])
    assert got["href"].startswith("/transactions?tag=eid&date_from=2026-01-01")
    assert answer(c, "eid 2026", SAMPLE_TODAY)["name"] == "Eidiya"
