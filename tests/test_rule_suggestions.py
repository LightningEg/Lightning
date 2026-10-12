"""Rules suggested from what the user files: a counterparty filed the same way at least 3 times (and 90% of
its filings) with no rule or default category saying so yet. Dismissed names never return; Settings › Rules shows them; Create rule opens the rule form filled."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _cats(c):
    return {code: c.categories.get_by_code(code).id for code in (
        "EXP.PERSONAL.UTILITIES", "EXP.PERSONAL.FOOD", "EXP.PERSONAL.SHOPPING")}


def _file(c, account, category, name, times, start=1):
    return [c.transactions.record_outflow(f"2026-09-{start + i:02d}", account, "100", category, counterparty=name)
            for i in range(times)]


def _names(c):
    return [s.name for s in c.rules.suggestions()]


def test_three_filings_make_a_suggestion_and_two_do_not(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Spinneys", 2)
    assert _names(c) == []
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Spinneys", 1, start=10)
    [s] = c.rules.suggestions()
    assert (s.name, s.category_id, s.count, s.share) == ("Spinneys", cats["EXP.PERSONAL.FOOD"], 3, 1)


def test_ninety_percent_must_agree(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Carrefour", 8)
    _file(c, cib, cats["EXP.PERSONAL.SHOPPING"], "Carrefour", 1, start=10)   # 8 of 9 = 89%
    assert _names(c) == []
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Carrefour", 1, start=11)       # 9 of 10 = 90%
    [s] = c.rules.suggestions()
    assert (s.count, str(s.share)) == (9, "0.9")


def test_a_rule_or_a_default_category_that_already_gives_it_hides_the_suggestion(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    for name in ("Vodafone", "Spinneys", "Talabat"):
        _file(c, cib, cats["EXP.PERSONAL.FOOD"], name, 3)
    assert _names(c) == ["Spinneys", "Talabat", "Vodafone"]
    c.rules.save({"counterparty": "vodafone", "category_id": str(cats["EXP.PERSONAL.FOOD"])})
    c.db.execute("UPDATE counterparties SET default_category_id=? WHERE name='Spinneys'", (cats["EXP.PERSONAL.FOOD"],))
    assert _names(c) == ["Talabat"]


def test_dismissing_is_remembered(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Talabat", 3)
    c.rules.dismiss_suggestion("TALABAT")
    assert _names(c) == []
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Talabat", 3, start=10)
    assert _names(c) == []


def test_voided_transfer_and_held_for_others_lines_are_not_counted(c, setup):
    accounts, cats = setup[0], _cats(c)
    cib, wallet = accounts["cib"].id, accounts["wallet"].id
    made = _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Talabat", 3)
    c.transactions.void(made[0].id)                        # 2 left
    for day in range(10, 14):
        c.transactions.record_transfer(f"2026-09-{day}", cib, wallet, "50")
    c.db.execute("UPDATE transactions SET counterparty='Talabat' WHERE type='TRF'")
    owner = c.counterparties.create("Dad")
    for day in range(14, 18):
        c.transactions.record_expense_paid_by_person(f"2026-09-{day}", cib, "70", owner, cats["EXP.PERSONAL.FOOD"])
    c.db.execute("UPDATE transactions SET counterparty='Talabat' WHERE counterparty IS NULL OR counterparty=''")
    assert _names(c) == []


def test_a_rule_with_a_different_category_also_hides_the_suggestion(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Vodafone", 3)
    assert _names(c) == ["Vodafone"]
    c.rules.save({"counterparty": "vodafone", "category_id": str(cats["EXP.PERSONAL.UTILITIES"])})
    assert _names(c) == []


def test_the_rules_page_lists_creates_and_dismisses(c, setup):
    cib, cats = setup[0]["cib"].id, _cats(c)
    _file(c, cib, cats["EXP.PERSONAL.FOOD"], "Talabat", 3)
    _file(c, cib, cats["EXP.PERSONAL.UTILITIES"], "Vodafone", 4)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    page = client.get("/rules").text
    assert "Suggested rules" in page and "Vodafone" in page and "Create rule" in page
    form = client.get(f"/rules/new?counterparty_op=is&counterparty=Vodafone&category_id={cats['EXP.PERSONAL.UTILITIES']}")
    assert form.status_code == 200 and 'value="Vodafone"' in form.text
    saved = client.post("/rules", data={"counterparty_op": "is", "counterparty": "Vodafone",
                                        "category_id": str(cats["EXP.PERSONAL.UTILITIES"])}, follow_redirects=False)
    assert saved.status_code == 303 and _names(c) == ["Talabat"]
    gone = client.post("/rules/suggestions/dismiss", data={"name": "Talabat"}, follow_redirects=False)
    assert gone.status_code == 303 and _names(c) == []
    assert "Suggested rules" not in client.get("/rules").text
