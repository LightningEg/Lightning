from __future__ import annotations

import pytest

from lightning.bank_imports import decode_csv
from lightning.transactions.domain import TxnSource


def _upload_and_map(client, account_id, filename, data, mapping, amount_model="SINGLE"):
    import re
    response = client.post(f"/accounts/{account_id}/import",
                           files={"file": (filename, data, "text/csv")}, follow_redirects=False)
    if response.status_code == 303:  # Lightning's own column names: nothing to match, straight to review
        assert set(data.decode().splitlines()[0].split(",")) <= {"Date", "Amount", "Counterparty", "Category",
                                                                    "Notes", "Reference"}
        return response
    assert response.status_code == 200 and "Match your columns" in response.text
    payload = re.search(r'name="payload" value="([^"]+)"', response.text).group(1)
    values = {"payload": payload, "filename": filename, "amount_model": amount_model}
    values.update({f"map_{key}": value for key, value in mapping.items()})
    return client.post(f"/accounts/{account_id}/import/map", data=values, follow_redirects=False)


def test_parser_supports_utf8_bom_grouped_amounts_and_column_mapping():
    # Quoted thousands-grouped numbers are valid CSV values.
    data = "\ufeffWhen,Merchant,Net\n25/09/2026,Café,\"-1,200.50\"\n".encode()
    headers, rows = decode_csv(data)
    assert headers == ["When", "Merchant", "Net"]
    assert rows[0]["Net"] == "-1,200.50"


def test_parser_accepts_statements_with_more_than_ten_thousand_rows():
    lines = ["Date,Amount"] + [f"2026-09-25,{index + 1}" for index in range(10_001)]
    _, rows = decode_csv(("\n".join(lines) + "\n").encode())
    assert len(rows) == 10_001


def test_suggested_mapping_uses_canonical_headers_and_bank_aliases(c, setup):
    account_id = setup[0]["cib"].id
    suggest = c.bank_imports.suggested_mapping
    standard = suggest(account_id, ["Date", "Counterparty", "Amount", "Notes"])
    assert standard["Date"] == "Date" and standard["Amount"] == "Amount"
    assert standard["Counterparty"] == "Counterparty" and standard["Notes"] == "Notes"
    bank = suggest(account_id, ["Transaction Date", "Credit", "Debit", "Description"])
    assert bank["Date"] == "Transaction Date"
    assert bank["Inflow"] == "Credit" and bank["Outflow"] == "Debit"
    assert bank["amount_model"] == "SEPARATE"


def test_import_stages_posts_and_same_file_can_be_reviewed_again(c, setup):
    accounts, cats = setup
    data = ("\ufeffDate,Counterparty,Amount,Category,Notes,Reference\n"
            "2026-09-20,Talabaat,-125,Food & Groceries,late meal,R-100\n").encode()
    batch_id, repeated = c.bank_imports.stage(accounts["cib"].id, "september.csv", data)
    assert not repeated
    batch, rows = c.bank_imports.preview(batch_id)
    row = rows[0]
    posted = c.bank_imports.confirm(batch_id, {row["_import_row_id"]: {
        "new_counterparty": "Talabat", "category_id": cats["EXP.PERSONAL.FOOD"].id
    }})
    assert posted["posted"] == 1 and posted["skipped"] == posted["duplicates"] == 0
    transaction = c.db.one("SELECT t.source,t.counterparty_id FROM transactions t JOIN bank_import_rows r "
                           "ON r.transaction_id=t.id WHERE r.batch_id=?", (batch_id,))
    assert transaction["source"] == TxnSource.IMPORT.value
    assert transaction["counterparty_id"] == c.counterparties.resolve("Talabaat")["id"]
    duplicate_batch, repeated = c.bank_imports.stage(accounts["cib"].id, "september.csv", data)
    assert duplicate_batch != batch_id and not repeated
    _, duplicate_rows = c.bank_imports.preview(duplicate_batch)
    assert duplicate_rows[0]["_reference_duplicate"]
    duplicate = c.bank_imports.confirm(duplicate_batch, {
        duplicate_rows[0]["_import_row_id"]: {"skip": True}
    })
    assert duplicate["duplicates"] == 1
    assert c.reporting.account_balance(accounts["cib"].id) == 50000 - 125


def test_import_works_for_non_bank_accounts_and_missing_optional_columns(c, setup):
    accounts, _ = setup
    wallet_id = accounts["wallet"].id
    batch_id, repeated = c.bank_imports.stage(wallet_id, "wallet.csv", b"Date,Amount\n2026-09-22,-25\n")
    assert not repeated
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["Counterparty"] == "" and rows[0]["_category_id"] is None
    summary = c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {}})
    assert summary["posted"] == 1
    assert c.reporting.account_balance(wallet_id) == 1200 - 25


def test_separate_inflow_and_outflow_columns_become_one_signed_amount(c, setup):
    accounts, _ = setup
    account_id = accounts["cib"].id
    data = (b"When,Credit,Debit\n"
            b"2026-09-22,1250.50,\n"
            b"2026-09-23,,400\n")
    batch_id, repeated = c.bank_imports.stage(
        account_id, "two-columns.csv", data,
        {"amount_model": "SEPARATE", "Date": "When", "Inflow": "Credit", "Outflow": "Debit"},
    )
    assert not repeated
    _, rows = c.bank_imports.preview(batch_id)
    assert [row["Amount"] for row in rows] == ["1250.50", "-400"]
    result = c.bank_imports.confirm(batch_id, {row["_import_row_id"]: {} for row in rows})
    assert result["posted"] == 2
    assert c.reporting.account_balance(account_id) == 50000 + 1250.50 - 400
    assert [row["type"] for row in c.db.all(
        "SELECT type FROM transactions WHERE source='IMPORT' ORDER BY date DESC")] == ["OUT", "IN"]


def test_two_column_row_with_both_directions_needs_correction(c, setup):
    accounts, _ = setup
    batch_id, _ = c.bank_imports.stage(
        accounts["cib"].id, "ambiguous.csv", b"Date,Credit,Debit\n2026-09-22,100,50\n",
        {"amount_model": "SEPARATE", "Date": "Date", "Inflow": "Credit", "Outflow": "Debit"},
    )
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["_errors"] == ["A row cannot have both an inflow and an outflow amount."]


def test_ui_maps_two_amount_columns_and_previews_signed_amounts(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    data = b"When,Credit,Debit\n2026-09-22,100,\n2026-09-23,,25\n"
    response = client.post(f"/accounts/{account_id}/import", files={"file": ("statement.csv", data, "text/csv")},
                           follow_redirects=False)
    assert response.status_code == 200 and "In and out columns" in response.text and ">Money in<" in response.text
    import re
    payload = re.search(r'name="payload" value="([^"]+)"', response.text).group(1)
    mapped = client.post(f"/accounts/{account_id}/import/map", data={
        "payload": payload, "filename": "statement.csv", "amount_model": "SEPARATE",
        "map_Date": "When", "map_Inflow": "Credit", "map_Outflow": "Debit",
    }, follow_redirects=False)
    assert mapped.status_code == 303
    batch_id = int(mapped.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(batch_id)
    assert [row["Amount"] for row in rows] == ["100", "-25"]


def test_reference_duplicate_is_flagged_and_not_posted(c, setup):
    accounts, cats = setup
    first = b"Date,Counterparty,Amount,Category,Reference\n2026-09-20,Kiosk,-5,Food & Groceries,REF-X\n"
    first_id, _ = c.bank_imports.stage(accounts["cib"].id, "one.csv", first)
    _, first_rows = c.bank_imports.preview(first_id)
    c.bank_imports.confirm(first_id, {first_rows[0]["_import_row_id"]: {"category_id": cats["EXP.PERSONAL.FOOD"].id, "new_counterparty": "Kiosk"}})
    second = b"Date,Counterparty,Amount,Category,Reference\n2026-09-21,Kiosk,-6,Food & Groceries,REF-X\n"
    second_id, _ = c.bank_imports.stage(accounts["cib"].id, "two.csv", second)
    _, rows = c.bank_imports.preview(second_id)
    assert rows[0]["_reference_duplicate"]
    assert c.bank_imports.confirm(second_id, {rows[0]["_import_row_id"]: {"skip": True}})["duplicates"] == 1
    assert c.reporting.account_balance(accounts["cib"].id) == 49995


def test_duplicate_can_be_explicitly_approved(c, setup):
    accounts, _ = setup
    data = b"Date,Counterparty,Amount,Reference\n2026-09-20,Shop,-5,REF-APPROVE\n"
    first_id, _ = c.bank_imports.stage(accounts["cib"].id, "first.csv", data)
    _, first_rows = c.bank_imports.preview(first_id)
    c.bank_imports.confirm(first_id, {first_rows[0]["_import_row_id"]: {}})
    second_id, _ = c.bank_imports.stage(accounts["cib"].id, "second.csv", data)
    _, rows = c.bank_imports.preview(second_id)
    assert rows[0]["_reference_duplicate"]
    result = c.bank_imports.confirm(second_id, {rows[0]["_import_row_id"]: {}})
    assert result["posted"] == 1 and result["duplicates"] == 0


def test_deleted_transaction_does_not_trigger_duplicate_and_same_file_can_be_reimported(c, setup):
    accounts, _ = setup
    data = b"Date,Counterparty,Amount,Reference\n2026-09-20,Shop,-5,REF-VOID\n"
    first_id, _ = c.bank_imports.stage(accounts["cib"].id, "same.csv", data)
    _, first_rows = c.bank_imports.preview(first_id)
    c.bank_imports.confirm(first_id, {first_rows[0]["_import_row_id"]: {}})
    txn_id = c.db.scalar("SELECT transaction_id FROM bank_import_rows WHERE batch_id=?", (first_id,))
    c.transactions.void(txn_id, "test deletion")

    second_id, repeated = c.bank_imports.stage(accounts["cib"].id, "same.csv", data)
    assert second_id != first_id and not repeated
    _, second_rows = c.bank_imports.preview(second_id)
    assert not second_rows[0]["_reference_duplicate"]
    assert c.bank_imports.confirm(second_id, {second_rows[0]["_import_row_id"]: {}})["posted"] == 1


def test_other_account_statement_flags_the_matching_transfer(c):
    nbe = c.account_flows.open_account("NBE", "BANK", "2026-09-01", "50000")
    cib = c.account_flows.open_account("CIB", "BANK", "2026-09-01", "50000")
    first_id, _ = c.bank_imports.stage(
        nbe.id, "nbe.csv", b"Date,Counterparty,Amount\n2026-09-02,CIB,-100\n")
    _, first_rows = c.bank_imports.preview(first_id)
    c.bank_imports.confirm(first_id, {first_rows[0]["_import_row_id"]: {}})

    second_id, _ = c.bank_imports.stage(
        cib.id, "cib.csv", b"Date,Counterparty,Amount\n2026-09-02,NBE,100\n")
    _, second_rows = c.bank_imports.preview(second_id)
    assert second_rows[0]["_similarity_warning"] is True


def test_malformed_rows_are_previewed_and_can_be_skipped(c, setup):
    accounts, _ = setup
    data = b"Date,Counterparty,Amount\nnot-a-date,Shop,bad\n"
    batch_id, _ = c.bank_imports.stage(accounts["cib"].id, "broken.csv", data)
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["_errors"] and c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {"skip": True}})["skipped"] == 1


def test_ui_upload_review_and_post(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    csv = b"Date,Counterparty,Amount\n2026-09-22,Shop,-14\n"
    upload = _upload_and_map(client, account_id, "month.csv", csv,
                             {"Date": "Date", "Amount": "Amount", "Counterparty": "Counterparty"})
    assert upload.status_code == 303
    preview = client.get(upload.headers["location"])
    assert preview.status_code == 200 and "Post ready rows" in preview.text and 'name="amount_' in preview.text
    batch_id = int(upload.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(batch_id)
    row_id = rows[0]["_import_row_id"]
    posted = client.post(f"/accounts/{account_id}/import/{batch_id}/confirm", data={
        f"counterparty_{row_id}": "Shop", f"counterparty_choice_{row_id}": "new",
        f"category_{row_id}": str(cats["EXP.PERSONAL.FOOD"].id), f"date_{row_id}": "2026-09-22",
        f"amount_{row_id}": "-14"
    }, follow_redirects=False)
    assert posted.status_code == 200 and "Import complete: 1 posted" in posted.text
    assert c.reporting.account_balance(account_id) == 50000 - 14


def test_ui_allows_incomplete_rows_and_defaults_category(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    csv = b"Date,Counterparty,Amount\n2026-09-22,New Shop,-14\n"
    upload = _upload_and_map(client, account_id, "m.csv", csv,
                             {"Date": "Date", "Amount": "Amount", "Counterparty": "Counterparty"})
    batch_id = int(upload.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(batch_id)
    row_id = rows[0]["_import_row_id"]
    response = client.post(f"/accounts/{account_id}/import/{batch_id}/confirm", data={
        f"counterparty_{row_id}": "", f"category_{row_id}": "", f"date_{row_id}": "2026-09-22",
        f"amount_{row_id}": "-14"
    }, follow_redirects=False)
    assert response.status_code == 200 and "Import complete" in response.text
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE source='IMPORT'") == 1
    txn = c.db.one("SELECT counterparty FROM transactions WHERE source='IMPORT'")
    assert txn["counterparty"] == ""
    assert c.db.scalar("SELECT c.code FROM ledger_entries l JOIN categories c ON c.id=l.category_id JOIN transactions t ON t.id=l.transaction_id WHERE t.source='IMPORT'") == "EXP.UNACCOUNTED"


def test_review_form_field_budget_scales_with_import_rows():
    from lightning.ui.routes.bank_imports import _review_form_max_fields
    assert _review_form_max_fields(170) > 1_000
    assert _review_form_max_fields(10) == 1_000


def test_import_confirm_parses_more_than_one_thousand_form_fields(c, setup):
    import asyncio
    from urllib.parse import urlencode
    from starlette.applications import Starlette
    from starlette.requests import Request
    from lightning.ui.routes.bank_imports import confirm
    accounts, _ = setup
    account_id = accounts["cib"].id
    data = ("Date,Amount\n" + "".join(f"2026-09-22,{n + 1}\n" for n in range(292))).encode()
    batch_id, _ = c.bank_imports.stage(account_id, "large-review.csv", data)
    _, rows = c.bank_imports.preview(batch_id)
    fields = {}
    for row in rows:
        row_id = row["_import_row_id"]
        fields.update({f"date_{row_id}": "2026-09-22", f"amount_{row_id}": row["Amount"],
                       f"counterparty_{row_id}": "", f"counterparty_choice_{row_id}": "",
                       f"category_{row_id}": "", f"notes_{row_id}": "",
                       f"whom_{row_id}": "", f"skip_{row_id}": "on"})
    body = urlencode(fields).encode()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    app = Starlette()
    app.state.container = c
    path = f"/accounts/{account_id}/import/{batch_id}/confirm"
    request = Request({"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
                       "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                       "headers": [(b"host", b"testserver"),
                                   (b"content-type", b"application/x-www-form-urlencoded")],
                       "server": ("testserver", 80), "client": ("testclient", 50000), "app": app}, receive)
    response = asyncio.run(confirm(request, account_id, batch_id))
    assert response.status_code == 200
    assert b"Import complete" in response.body
    assert c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='SKIPPED'",
                       (batch_id,)) == 292


def test_ui_maps_nonstandard_headers_once_and_can_reverse_sign(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    first = b"When,Merchant,Net\n25/09/2026,Shop,14\n"
    response = client.post(f"/accounts/{account_id}/import", files={"file": ("sep.csv", first, "text/csv")}, follow_redirects=False)
    assert response.status_code == 200 and "Match your columns" in response.text
    import re
    payload = re.search(r'name="payload" value="([^"]+)"', response.text).group(1)
    mapped = client.post(f"/accounts/{account_id}/import/map", data={
        "payload": payload, "filename": "sep.csv", "map_Date": "When",
        "map_Counterparty": "Merchant", "map_Amount": "Net", "amount_sign": "invert"
    }, follow_redirects=False)
    assert mapped.status_code == 303
    batch_id = int(mapped.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["Date"] == "2026-09-25" and rows[0]["Amount"] == "-14"
    second = b"When,Merchant,Net\n26/09/2026,Shop,22\n"
    auto = client.post(f"/accounts/{account_id}/import", files={"file": ("oct.csv", second, "text/csv")}, follow_redirects=False)
    assert auto.status_code == 303 and "/import/map" not in auto.headers["location"]
    second_id = int(auto.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(second_id)
    assert rows[0]["Date"] == "2026-09-26" and rows[0]["Amount"] == "-22"


def test_same_new_counterparty_on_several_rows_is_created_once(c, setup):
    accounts, cats = setup
    csv = b"Date,Counterparty,Amount\n2026-09-02,CARREFOUR 4587,-100\n2026-09-09,CARREFOUR 4587,-200\n"
    batch_id, _ = c.bank_imports.stage(accounts["cib"].id, "shop.csv", csv)
    _, rows = c.bank_imports.preview(batch_id)
    decisions = {row["_import_row_id"]: {"counterparty": "Carrefour", "counterparty_choice": "new",
                                         "new_counterparty": "Carrefour",
                                         "category_id": str(cats["EXP.PERSONAL.FOOD"].id)} for row in rows}
    result = c.bank_imports.confirm(batch_id, decisions)
    assert result["errors"] == {} and result["posted"] == 2
    assert [row["name"] for row in c.counterparties.list_active()].count("Carrefour") == 1


def test_review_with_a_row_error_rerenders_typed_amounts(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, cats = setup
    client = TestClient(create_app(c))
    account_id = accounts["cib"].id
    csv = b"Date,Counterparty,Amount\n2026-09-02,Shop,-1200\n2026-09-03,Shop,-45\n"
    upload = _upload_and_map(client, account_id, "month.csv", csv,
                             {"Date": "Date", "Amount": "Amount", "Counterparty": "Counterparty"})
    batch_id = int(upload.headers["location"].rsplit("/", 1)[-1])
    _, rows = c.bank_imports.preview(batch_id)
    first, second = (row["_import_row_id"] for row in rows)
    posted = client.post(f"/accounts/{account_id}/import/{batch_id}/confirm", data={
        f"counterparty_choice_{first}": "unlinked", f"amount_{first}": "-1,200.00", f"date_{first}": "2026-09-02",
        f"counterparty_choice_{second}": "unlinked", f"amount_{second}": "-4x5", f"date_{second}": "2026-09-03",
    })
    assert posted.status_code == 200
    assert "Nothing was imported" in posted.text and "To fix 1" in posted.text


def test_foreign_statement_keeps_native_amounts_and_values_both_frames_at_dated_fx(c, monkeypatch):
    from decimal import Decimal
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    c.currencies.register("USD")
    c.fx.save("USD", "2026-09-01", "50")
    c.fx.save("USD", "2026-09-30", "50")
    account = c.account_flows.open_account("Dollar bank", "BANK", "2026-09-01", "100", currency="USD")
    batch, _ = c.bank_imports.stage(account.id, "usd.csv", b"Date,Counterparty,Amount,Category\n2026-09-20,Cafe,-10.50,Food & Groceries\n")
    _, rows = c.bank_imports.preview(batch)
    assert c.bank_imports.confirm(batch, {rows[0]["_import_row_id"]: {}})["posted"] == 1
    assert c.reporting.account_balance(account.id, "2026-09-30") == Decimal("89.50")
    assert c.reporting.account_value(account.id, "2026-09-30") == Decimal("4475")
    app = create_app(c)
    async def phone(scope, receive, send):
        scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)
    for frame in (app, phone):
        page = TestClient(frame).get(f"/accounts/{account.id}")
        assert page.status_code == 200 and "USD" in page.text and "10.50" in page.text


def test_a_future_dated_row_is_marked_to_fix_in_the_review_not_when_posting(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-15")
    accounts, _ = setup
    data = b"Date,Counterparty,Amount\n2026-10-14,Talabat,-50\n2026-12-30,Future,-10\n"
    batch_id, _ = c.bank_imports.stage(accounts["cib"].id, "future.csv", data)
    _, rows = c.bank_imports.preview(batch_id)
    errors = {row["Counterparty"]: row["_errors"] for row in rows}
    assert errors["Talabat"] == []
    assert errors["Future"] and "in the future" in errors["Future"][0]


def test_the_map_page_and_the_account_form_use_the_form_grid(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    mapped = client.post(f"/accounts/{accounts['cib'].id}/import",
                         files={"file": ("sep.csv", b"When,Merchant,Net\n25/09/2026,Shop,14\n", "text/csv")})
    assert 'class="form-grid"' in mapped.text and '<fieldset class="import-amount-model">' not in mapped.text
    assert "One amount column" in mapped.text and "In and out columns" in mapped.text and "Reverse the sign" in mapped.text
    form = client.get("/accounts/new").text
    assert 'class="form-grid"' in form and 'class="soft-section"' in form and 'class="card" id="opening-balance-section"' not in form
    assert 'class="field wide"' in form  # Notes takes the whole row


def test_decimal_amount_reads_common_bank_money_formats():
    from decimal import Decimal as D

    from lightning.bank_imports import _decimal_amount

    assert _decimal_amount("(1,250.00)") == D("-1250.00")
    assert _decimal_amount("1,250.00-") == D("-1250.00")
    assert _decimal_amount("−1,250.00") == D("-1250.00")
    assert _decimal_amount("EGP 1,250.00") == D("1250.00")
    assert _decimal_amount("1,250.00 EGP") == D("1250.00")
    assert _decimal_amount("1,250.00 ج.م") == D("1250.00")
    assert _decimal_amount("١٬٢٥٠٫٠٠") == D("1250.00")
    # Still accepted
    assert _decimal_amount("-1,250.00") == D("-1250.00")
    assert _decimal_amount("1.250,00") == D("1250.00")
    assert _decimal_amount("") == D("0")
    # Two signs and non-numbers stay rejected
    for bad in ("-(5)", "(5)-", "abc", "EGP"):
        with pytest.raises(ValueError):
            _decimal_amount(bad)


@pytest.mark.parametrize("text,expected", [
    (".50", "0.50"), ("-.50", "-0.50"), (".50-", "-0.50"),
    ("(.50)", "-0.50"), ("+1.25", "1.25"), ("EGP .50", "0.50"),
    ("(EGP 1,250.00)", "-1250.00"), ("EGP -1,250.00", "-1250.00"),
])
def test_decimal_amount_preserves_decimal_points_and_one_sign(text, expected):
    from decimal import Decimal
    from lightning.bank_imports import _decimal_amount
    assert _decimal_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["5%", "abc5", "5abc", "+-5", "(-5)", "(+5)", "5+", "EGP 5 USD"])
def test_decimal_amount_rejects_unknown_wrappers_and_extra_signs(text):
    from lightning.bank_imports import _decimal_amount
    with pytest.raises(ValueError):
        _decimal_amount(text)


def test_fractional_accounting_csv_changes_the_ledger_once_by_the_exact_amount(c, setup):
    from decimal import Decimal
    account_id = setup[0]["cib"].id
    before = c.reporting.account_balance(account_id)
    data = b"Date,Amount,Reference\n2026-09-22,(EGP .50),FRACTION-1\n"
    batch_id, _ = c.bank_imports.stage(account_id, "fraction.csv", data)
    _, rows = c.bank_imports.preview(batch_id)
    assert rows[0]["Amount"] == "-0.50"
    assert c.bank_imports.confirm(batch_id, {rows[0]["_import_row_id"]: {}})["posted"] == 1
    expected = before - Decimal("0.50")
    assert c.reporting.account_balance(account_id) == expected
    ledger = c.db.one("SELECT SUM(amount_base_e6) AS balance FROM ledger_entries WHERE account_id=?", (account_id,))
    assert Decimal(ledger["balance"]) / 1000000 == expected
    again, _ = c.bank_imports.stage(account_id, "fraction.csv", data)
    _, duplicates = c.bank_imports.preview(again)
    assert duplicates[0]["_reference_duplicate"]
    assert c.bank_imports.confirm(again, {duplicates[0]["_import_row_id"]: {"skip": True}})["duplicates"] == 1
    assert c.reporting.account_balance(account_id) == expected
