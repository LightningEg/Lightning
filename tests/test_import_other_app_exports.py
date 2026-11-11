"""Moving in from another app's export (owner feedback, 2026-11-05: IV-7Z).

Such a file carries the other app's category group, its own opening-balance and adjustment rows, and its own
category names. The group settles which of two same-named categories a row means; balance rows wait unticked
as Skip so money is not counted twice; and every unknown category name is listed once, so the person sets it once
for all its rows. Dummy rows only.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.ui.web import create_app

HEADER = "Account,Date,Counterparty,Notes,Category_Group,Category,Amount,Split_Amount,Cleared\n"
ROWS = (
    "Bank,2026-09-10,Ride Co,Card purchase,Work,Transportation,-120,0,Cleared\n"
    "Bank,2026-09-11,Ride Co,Card purchase,Personal,Transportation,-80,0,Cleared\n"
    "Bank,2026-09-12,Balance adjustment,Bank showed more,Personal,Other Income,9.17,0,Not cleared\n"
    "Bank,2026-09-01,,Adjustment,Income,Starting Balances,1013.94,0,Not cleared\n"
    "Bank,2026-09-13,Kiosk,Daily expense,Usual Expenses,Daily Expenses,-30,0,Cleared\n"
    "Bank,2026-09-14,Kiosk,Daily expense,Usual Expenses,Daily Expenses,-45,0,Cleared\n"
)


def _staged(c, account_id):
    data = (HEADER + ROWS).encode()
    headers = data.decode().splitlines()[0].split(",")
    mapping = c.bank_imports.suggested_mapping(account_id, headers)
    batch_id, _ = c.bank_imports.stage(account_id, "other-app.csv", data, mapping=mapping)
    return mapping, batch_id, {int(r["_line"]): r for r in c.bank_imports.preview(batch_id)[1]}


def test_the_group_column_is_matched_and_settles_same_named_categories(c, setup):
    accounts, _ = setup
    mapping, _, rows = _staged(c, accounts["cib"].id)
    assert mapping["Group"] == "Category_Group"
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
    personal = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id
    assert (rows[2]["_category_id"], rows[3]["_category_id"]) == (work, personal)
    assert rows[2]["_ready"] and not rows[2].get("_category_ambiguous")


def test_another_apps_balance_rows_wait_as_skip(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    _, batch_id, rows = _staged(c, cib)
    assert rows[4]["_balance_row"] and rows[5]["_balance_row"]
    assert not rows[4]["_ready"] and not rows[2]["_balance_row"]
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get(f"/accounts/{cib}/import/{batch_id}?rows=all").text
    rid = rows[5]["_import_row_id"]
    assert f'name="skip_{rid}" checked' in page
    assert "opening balance or balance adjustment" in page


def test_each_unknown_category_name_is_listed_once_for_all_its_rows(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    _, batch_id, rows = _staged(c, cib)
    label = "Usual Expenses › Daily Expenses"
    assert rows[6]["_file_label"] == rows[7]["_file_label"] == label
    assert rows[2]["_file_label"] == "" and rows[4]["_file_label"] == ""
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get(f"/accounts/{cib}/import/{batch_id}?rows=all").text
    assert page.count(f'data-file-label-pick="{label}"') == 1
    assert page.count(f'data-file-label="{label}"') == 2
