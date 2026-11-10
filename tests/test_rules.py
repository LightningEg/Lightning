"""Rules with conditions (Upcoming projects #5): "Vodafone above 300 is Internet, the rest is Phone".

The engine is checked op by op, with Actual Budget's ranking and a split that always adds up; then a rule
beats the counterparty's usual category on import and in the register, adds its tag, splits an expense,
and refiles past transactions only when asked, with one undo."""
from __future__ import annotations

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.rules import engine
from lightning.rules.engine import Condition, Part, Rule
from lightning.ui.web import create_app


def _txn(name="VODAFONE EG", amount="-350", notes="", account_id=1):
    return {"counterparty": [name], "notes": notes, "amount": D(amount), "account_id": account_id}


# ------------------------------------------------------------------ engine
@pytest.mark.parametrize("condition, txn, holds", [
    (Condition("counterparty", "contains", "vodafone"), _txn(), True),
    (Condition("counterparty", "is", "vodafone eg"), _txn(), True),
    (Condition("counterparty", "is", "vodafone"), _txn(), False),
    (Condition("counterparty", "one_of", "WE, Vodafone EG"), _txn(), True),
    (Condition("notes", "contains", "INTERNET"), _txn(notes="home internet"), True),
    (Condition("notes", "contains", "internet"), _txn(), False),
    (Condition("amount", "is", "350"), _txn(), True),
    (Condition("amount", "about", "330"), _txn(), True),           # 350 is within 7.5% of 330
    (Condition("amount", "about", "300"), _txn(), False),
    (Condition("amount", "between", "100", "300"), _txn(amount="-300"), True),
    (Condition("amount", "between", "100", "300"), _txn(), False),
    (Condition("amount", "more", "300"), _txn(), True),
    (Condition("amount", "less", "300"), _txn(), False),
    (Condition("account", "is", "1"), _txn(), True),
    (Condition("direction", "is", "out"), _txn(), True),
    (Condition("direction", "is", "in"), _txn(), False),
    (Condition("counterparty", "contains", "vodafone"), _txn(name=""), False),  # a missing field never matches
    (Condition("amount", "is", "٣٥٠"), _txn(), True),                           # Arabic-Indic digits
])
def test_each_condition(condition, txn, holds):
    assert engine.holds(condition, txn) is holds


def test_the_most_specific_rule_decides_and_every_matching_rule_adds_its_tag():
    broad = Rule(1, (Condition("counterparty", "contains", "vodafone"),), category_id=10, tags=("phone",))
    big = Rule(2, (Condition("counterparty", "contains", "vodafone"), Condition("amount", "more", "300")),
               category_id=20, tags=("bills",))
    exact = Rule(3, (Condition("counterparty", "is", "vodafone eg"),), category_id=30)
    assert [r.id for r in engine.rank([broad, big, exact])] == [3, 2, 1]
    assert engine.run([broad, big], _txn()).category_id == 20                  # the amount makes it specific
    assert engine.run([broad, big], _txn(amount="-120")).category_id == 10
    assert engine.run([broad, big], _txn()).tags == ("bills", "phone")
    either = Rule(4, (Condition("notes", "contains", "wifi"), Condition("amount", "is", "999")), match_all=False,
                  category_id=40)
    assert engine.run([either], _txn(notes="wifi")).category_id == 40


def test_a_split_always_adds_up_to_the_amount():
    parts = (Part(7, "fixed", D("50")), Part(8, "percent", D("33.33")))
    shares = engine.split(D("100.01"), parts, 9)
    assert shares == [(7, D("50.00")), (8, D("16.67")), (9, D("33.34"))]
    assert sum(v for _, v in shares) == D("100.01")
    assert engine.split(D("40"), (Part(7, "fixed", D("50")),), 9) is None    # nothing left for the rest
    assert engine.split(D("300"), (Part(9, "percent", D("30")),), 9) == [(9, D("300"))]  # same category merges


# ------------------------------------------------------------------ service
def _categories(c):
    return {code: c.categories.get_by_code(code).id for code in (
        "EXP.PERSONAL.UTILITIES", "EXP.PERSONAL.FOOD", "EXP.PERSONAL.ENTERTAINMENT", "EXP.PERSONAL.SHOPPING")}


def test_a_rule_needs_a_condition_and_something_to_set(c):
    cats = _categories(c)
    with pytest.raises(ValidationError, match="Say when"):
        c.rules.save({"category_id": str(cats["EXP.PERSONAL.UTILITIES"])})
    with pytest.raises(ValidationError, match="category or a tag"):
        c.rules.save({"counterparty": "Vodafone"})
    with pytest.raises(ValidationError, match="above the first"):
        c.rules.save({"counterparty": "Vodafone", "amount_op": "between", "amount": "300", "amount_to": "100",
                      "category_id": str(cats["EXP.PERSONAL.UTILITIES"])})
    with pytest.raises(ValidationError, match="leave something"):
        c.rules.save({"counterparty": "Vodafone", "category_id": str(cats["EXP.PERSONAL.UTILITIES"]),
                      "part_category_1": str(cats["EXP.PERSONAL.FOOD"]), "part_value_1": "60%",
                      "part_category_2": str(cats["EXP.PERSONAL.SHOPPING"]), "part_value_2": "40%"})
    rule_id = c.rules.save({"counterparty": "Vodafone", "amount_op": "between", "amount": "100", "amount_to": "300",
                            "category_id": str(cats["EXP.PERSONAL.UTILITIES"]), "tag": "#Bills"})
    words = c.rules.describe(c.rules.get(rule_id))
    assert words["when"] == "Payee contains Vodafone · Amount between 100 and 300"
    assert words["then"].endswith("#bills")


def test_an_import_follows_the_rule_before_the_usual_category_and_splits_the_bill(c, setup):
    accounts, _ = setup
    cats = _categories(c)
    cib = accounts["cib"].id
    for day in ("05", "06", "07"):   # Vodafone is usually filed under Food here
        c.transactions.record_outflow(f"2026-09-{day}", cib, "200", cats["EXP.PERSONAL.FOOD"], counterparty="Vodafone")
    c.rules.save({"counterparty": "vodafone", "amount_op": "more", "amount": "300",
                  "category_id": str(cats["EXP.PERSONAL.UTILITIES"]), "tag": "bills",
                  "part_category_1": str(cats["EXP.PERSONAL.ENTERTAINMENT"]), "part_value_1": "30%"})
    batch_id, _ = c.bank_imports.stage(cib, "october.csv",
                                       b"Date,Counterparty,Amount,Notes\n"
                                       b"2026-10-01,Vodafone,-400,line\n2026-10-02,Vodafone,-150,\n")
    rows = {r["Amount"]: r for r in c.bank_imports.preview(batch_id)[1]}
    big, small = rows["-400"], rows["-150"]
    assert big["_category_id"] == cats["EXP.PERSONAL.UTILITIES"] and big["Notes"] == "line #bills"
    assert [p["amount"] for p in big["_rule_split"]] == ["120.00", "280.00"]
    assert small["_category_id"] == cats["EXP.PERSONAL.FOOD"] and small["_rule_id"] is None
    result = c.bank_imports.confirm(batch_id, {r["_import_row_id"]: {} for r in rows.values()})
    assert result["posted"] == 2 and not result["errors"]
    txn_id = c.db.scalar("SELECT transaction_id FROM bank_import_rows WHERE id=?", (big["_import_row_id"],))
    txn = c.transactions.get(txn_id)
    assert sorted((l.category_id, -l.amount) for l in txn.lines) == sorted(
        [(cats["EXP.PERSONAL.ENTERTAINMENT"], D("120")), (cats["EXP.PERSONAL.UTILITIES"], D("280"))])
    assert txn.notes == "line #bills"


def test_the_register_fills_by_name_and_decides_by_amount_on_save(c, setup):
    accounts, _ = setup
    cats = _categories(c)
    cib = accounts["cib"].id
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    c.counterparties.create("Vodafone", default_category_id=cats["EXP.PERSONAL.FOOD"])
    c.counterparties.create("WE")
    c.rules.save({"counterparty_op": "is", "counterparty": "WE", "category_id": str(cats["EXP.PERSONAL.SHOPPING"])})
    c.rules.save({"counterparty": "Vodafone", "amount_op": "more", "amount": "300",
                  "category_id": str(cats["EXP.PERSONAL.UTILITIES"])})
    assert c.rules.category_for_name("WE") == cats["EXP.PERSONAL.SHOPPING"]
    assert c.rules.depends_on_more_than_name("Vodafone") and not c.rules.depends_on_more_than_name("WE")
    for amount in ("-450", "-90"):
        saved = client.post(f"/accounts/{cib}/register", data={
            "date": "2026-10-03", "counterparty": "Vodafone", "category": "", "amount": amount})
        assert saved.status_code == 200
    rows = c.db.all("SELECT l.category_id, l.amount_e6 FROM ledger_entries l JOIN transactions t ON t.id=l.transaction_id "
                    "WHERE t.counterparty='Vodafone' AND t.date='2026-10-03' ORDER BY l.amount_e6")
    assert [r["category_id"] for r in rows] == [cats["EXP.PERSONAL.UTILITIES"], cats["EXP.PERSONAL.FOOD"]]


def test_the_past_changes_only_when_asked_and_one_undo_puts_it_back(c, setup):
    accounts, _ = setup
    cats = _categories(c)
    cib = accounts["cib"].id
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    old = [c.transactions.record_outflow("2026-09-1" + d, cib, amount, cats["EXP.PERSONAL.FOOD"],
                                         counterparty="Vodafone").id for d, amount in (("1", "500"), ("2", "80"))]
    saved = client.post("/rules", data={"counterparty": "Vodafone", "amount_op": "more", "amount": "300",
                                        "category_id": str(cats["EXP.PERSONAL.UTILITIES"])}, follow_redirects=False)
    assert saved.status_code == 303 and "/past" in saved.headers["location"]
    page = client.get(saved.headers["location"]).text
    assert "would change 1 past transaction" in page and "Leave the past as it is" in page
    assert c.transactions.get(old[0]).lines[0].category_id == cats["EXP.PERSONAL.FOOD"]   # nothing moved yet
    rule_id = c.rules.list()[0].id
    applied = client.post(f"/rules/{rule_id}/apply", data={"transaction_id": str(old[0]),
                          "fingerprint": c.rules.past_token(rule_id)}, follow_redirects=False)
    assert "refiled" in applied.headers["location"]
    category_of = lambda txn_id: next(l.category_id for l in c.transactions.get(txn_id).lines if l.category_id)
    assert category_of(old[0]) == cats["EXP.PERSONAL.UTILITIES"] and category_of(old[1]) == cats["EXP.PERSONAL.FOOD"]
    listing = client.get(applied.headers["location"]).text
    assert "Undo" in listing and "Payee contains Vodafone · Amount more than 300" in listing
    token = applied.headers["location"].split("undo=")[1].split("&")[0]
    client.post("/rules/undo", data={"token": token})
    assert category_of(old[0]) == cats["EXP.PERSONAL.FOOD"]
    assert not c.rules.can_undo(token)


def test_the_rules_screens_open_from_settings(c):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    empty = client.get("/rules").text
    assert "No rules yet" in empty and ">Rules<" in empty and "Add rule" in empty
    form = client.get("/rules/new").text
    assert "All of these" in form and "Split money out" in form and "Keep the usual one" in form
    refused = client.post("/rules", data={"counterparty": "", "category_id": ""})
    assert refused.status_code == 400 and "Say when the rule applies" in refused.text


def test_the_phone_entry_sheet_follows_the_rule_when_the_category_is_left_empty(c, setup):
    accounts, _ = setup
    cats = _categories(c)
    cib = accounts["cib"].id
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    c.rules.save({"counterparty": "Vodafone", "amount_op": "more", "amount": "300",
                  "category_id": str(cats["EXP.PERSONAL.UTILITIES"])})
    saved = client.post(f"/accounts/{cib}/transaction/new", data={
        "kind": "out", "date": "2026-10-03", "counterparty": "Vodafone", "category_id": "", "amount": "450"},
        follow_redirects=False)
    assert saved.status_code == 303
    refused = client.post(f"/accounts/{cib}/transaction/new", data={
        "kind": "out", "date": "2026-10-03", "counterparty": "Vodafone", "category_id": "", "amount": "90"})
    assert refused.status_code == 400 and "Choose a category" in refused.text   # no rule, no habit: he picks
    row = c.db.one("SELECT l.category_id FROM ledger_entries l JOIN transactions t ON t.id=l.transaction_id "
                   "WHERE t.counterparty='Vodafone' AND l.category_id IS NOT NULL")
    assert row["category_id"] == cats["EXP.PERSONAL.UTILITIES"]
