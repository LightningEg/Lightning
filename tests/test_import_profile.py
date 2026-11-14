"""IT-7AA1: a file's date order is decided once for the whole file."""
import pytest

from lightning.core.errors import ValidationError
from lightning.import_profile import profile_dates, read_date


def test_month_first_file_is_read_month_first():
    cells = ["10/02/2026", "10/13/2026", "11/03/2026"]
    profile = profile_dates(cells)
    assert (profile.order, profile.ambiguous) == ("mdy", False)
    assert [read_date(c, profile).isoformat() for c in cells] == ["2026-10-02", "2026-10-13", "2026-11-03"]


def test_day_first_file_and_ambiguous_default():
    profile = profile_dates(["13/10/2026", "10/02/2026"])
    assert profile.order == "dmy" and not profile.ambiguous
    assert read_date("10/02/2026", profile).isoformat() == "2026-02-10"
    assert profile_dates(["10/02/2026", "03/04/2026"]).ambiguous


def test_times_month_names_and_iso():
    assert read_date("2026-10-02 14:05:33").isoformat() == "2026-10-02"
    assert read_date("2026-10-02T14:05:33Z").isoformat() == "2026-10-02"
    assert read_date("02/10/2026 2:05 PM").isoformat() == "2026-10-02"
    assert read_date("01-Oct-2026").isoformat() == "2026-10-01"
    assert read_date("2 Oct 26").isoformat() == "2026-10-02"
    assert read_date("Oct 2, 2026").isoformat() == "2026-10-02"
    assert read_date("٠٢/١٠/٢٠٢٦").isoformat() == "2026-10-02"
    assert profile_dates(["2026-10-02", "2026-11-03"]).order == "ymd"


def test_bad_date_errors():
    with pytest.raises(ValidationError):
        read_date("31/02/2026")


def test_direction_column_sets_the_sign():
    import pytest as _p
    from lightning.bank_import_parsing import normalize_rows
    from lightning.bank_import_rows import direction_sign
    mapping = {"Date": "D", "Amount": "A", "Direction": "T"}
    raw = [{"D": "01/10/2026", "A": "250.50", "T": "DR", "__line__": "2"},
           {"D": "02/10/2026", "A": "15,000", "T": "Credit", "__line__": "3"},
           {"D": "03/10/2026", "A": "-80", "T": "Expense", "__line__": "4"},
           {"D": "04/10/2026", "A": "5", "T": "Card", "__line__": "5"}]
    rows = [parsed for _raw, parsed in normalize_rows(raw, mapping, "SINGLE", False)]
    assert [r["Amount"] for r in rows[:3]] == ["-250.50", "15000", "-80"]
    assert rows[3]["_errors"]
    assert direction_sign("Income") == 1


def test_type_column_is_no_longer_a_category(c, setup):
    headers = ["Date", "Amount", "Type", "Direction"]
    mapping = c.bank_imports.suggested_mapping(setup[0]["cib"].id, headers)
    assert mapping.get("Direction") == "Direction" and "Category" not in mapping


def test_bare_type_column_is_a_direction_only_when_its_values_are(c, setup):
    acc = setup[0]["cib"].id
    drcr = [{"Date": "2026-10-01", "Amount": "5", "Type": "DR"}, {"Date": "2026-10-02", "Amount": "6", "Type": "CR"}]
    assert c.bank_imports.suggested_mapping(acc, ["Date", "Amount", "Type"], drcr).get("Direction") == "Type"
    kinds = [{"Date": "2026-10-01", "Amount": "5", "Type": "Card"}]
    assert "Direction" not in c.bank_imports.suggested_mapping(acc, ["Date", "Amount", "Type"], kinds)


def test_row_in_another_currency_never_posts_its_own_figure():
    from lightning.bank_import_parsing import normalize_rows
    from lightning.bank_import_rows import currency_code
    mapping = {"Date": "D", "Amount": "A", "Currency": "C"}
    raw = [{"D": "2026-10-01", "A": "-40", "C": "USD", "__line__": "2"},
           {"D": "2026-10-02", "A": "-50", "C": "LE", "__line__": "3"},
           {"D": "2026-10-03", "A": "-60", "C": "", "__line__": "4"}]
    usd, le, blank = [p for _r, p in normalize_rows(raw, mapping, "SINGLE", False, "EGP")]
    assert "USD" in usd["_errors"][0] and not le["_errors"] and not blank["_errors"]
    assert currency_code("جنيه") == "EGP"


def test_a_file_with_an_account_column_is_split_into_each_accounts_own_review(c, setup):
    import json
    accounts = setup[0]
    cib = accounts["cib"].id
    other = next(a for a in c.accounts.list(active_only=True) if a.institution and a.institution != "CIB")
    csv = (b"Account,Date,Amount,Counterparty\nCIB Current,2026-10-01,-99,Netflix\n"
           b"CIB-CUR-EGP,2026-10-02,-5,Kiosk\nSomething else,2026-10-03,-7,Kiosk\n")
    batch, _ = c.bank_imports.stage(other.id, "x.csv", csv)
    here = c.db.all("SELECT raw_json FROM bank_import_rows WHERE batch_id=?", (batch,))
    assert [json.loads(r["raw_json"])["parsed"]["Counterparty"] for r in here] == ["Kiosk"]  # only the unknown name stays
    waiting = c.bank_imports.waiting(cib)
    assert len(waiting) == 1 and waiting[0]["waiting"] == 2 and waiting[0]["file_name"] == "x.csv"


def test_a_file_wholly_for_another_account_is_not_posted_here(c, setup):
    import json
    other = next(a for a in c.accounts.list(active_only=True) if a.institution and a.institution != "CIB")
    csv = b"Account,Date,Amount,Counterparty\nCIB Current,2026-10-01,-99,Netflix\nCIB-CUR-EGP,2026-10-02,-5,Kiosk\n"
    batch, _ = c.bank_imports.stage(other.id, "y.csv", csv)
    rows = [json.loads(r["raw_json"])["parsed"] for r in c.db.all("SELECT raw_json FROM bank_import_rows WHERE batch_id=?", (batch,))]
    assert all(r["_errors"] and "CIB Current" in r["_errors"][0] for r in rows)

def test_long_review_is_paged_and_unseen_rows_still_post(c, setup):
    import re
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app

    cib = setup[0]["cib"].id
    SHOPS = ["Seoudi", "Uber", "Netflix", "Carrefour", "Vodafone", "Pharmacy", "Kiosk"]
    lines = ["Date,Amount,Counterparty,Category"] + [
        f"2026-10-{1 + i % 28:02d},-{10 + i}.00,{SHOPS[i % 7]},Food & groceries" for i in range(400)]
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    r = client.post(f"/accounts/{cib}/import", files={"file": ("long.csv", "\n".join(lines).encode(), "text/csv")},
                    follow_redirects=False)
    assert r.status_code == 303
    url = r.headers["location"]
    batch = int(re.search(r"/import/(\d+)", url).group(1))
    assert 'name="date_' not in client.get(url).text  # the questions come first (NF-7AB1)
    page = client.get(url + "?rows=all").text
    assert 100 <= len(re.findall(r'name="date_\d+"', page)) <= 300 and "data-import-more" in page
    more = client.get(f"/accounts/{cib}/import/{batch}/groups?start=999")
    assert more.status_code == 200 and more.headers["X-Remaining"] == "0"
    rest = client.get(f"/accounts/{cib}/import/{batch}/groups?start=1")
    assert 'name="date_' in rest.text and int(rest.headers["X-Remaining"]) < 400
    before = c.reporting.account_balance(cib)
    done = client.post(f"/accounts/{cib}/import/{batch}/confirm", data={}, follow_redirects=False)
    assert done.status_code == 200
    posted = c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='POSTED'", (batch,))
    assert posted == 400 and c.reporting.account_balance(cib) < before


def test_footers_zero_amounts_and_future_holds_are_skips_not_errors():
    from lightning.bank_import_parsing import normalize_rows
    mapping = {"Date": "D", "Amount": "A", "Counterparty": "C"}
    raw = [{"D": "2026-10-01", "A": "-5", "C": "Shop", "__line__": "2"},
           {"D": "", "A": "14749.50", "C": "Total", "__line__": "3"},
           {"D": "2026-10-02", "A": "0", "C": "FEE WAIVED", "__line__": "4"},
           {"D": "2999-01-01", "A": "-999", "C": "PENDING", "__line__": "5"},
           {"D": "", "A": "7", "C": "Shop", "__line__": "6"}]
    rows = [p for _r, p in normalize_rows(raw, mapping, "SINGLE", False)]
    assert [bool(r.get("_skip_reason")) for r in rows] == [False, True, True, True, False]
    assert not any(r["_errors"] for r in rows[:4]) and rows[4]["_errors"]
    assert rows[3]["Amount"] == "-999"


def test_any_layout_reads_encodings_preamble_and_arabic_headers():
    from lightning.bank_import_rows import decode_csv
    preamble = "National Bank\nAccount: 1234\nDate,Description,Amount\n2026-10-01,Shop,-5\n"
    headers, rows = decode_csv(preamble.encode())
    assert headers == ["Date", "Description", "Amount"] and rows[0]["__line__"] == "4"
    arabic = "Date,Description,Amount\r\n2026-10-01,سعودي,-250.50\r\n"
    assert decode_csv(arabic.encode("cp1256"))[1][0]["Description"] == "سعودي"
    assert decode_csv("Date\tAmount\r\n2026-10-01\t-5\r\n".encode("utf-16"))[0] == ["Date", "Amount"]
    assert decode_csv("التاريخ,المبلغ\n2026-10-01,-5\n".encode())[0] == ["التاريخ", "المبلغ"]


def test_balance_only_statement_gets_amounts_from_the_balance_changes():
    from lightning.bank_import_parsing import normalize_rows
    mapping = {"Date": "D", "Balance": "B"}
    for order in (1, -1):
        raw = [{"D": d, "B": b, "__line__": str(i)} for i, (d, b) in enumerate(
            [("2026-10-01", "10000"), ("2026-10-02", "9749.50"), ("2026-10-03", "24749.50")][::order], start=2)]
        rows = {p["Date"]: p for _r, p in normalize_rows(raw, mapping, "BALANCE", False)}
        assert rows["2026-10-01"]["_skip_reason"] and not rows["2026-10-01"]["_errors"]
        assert rows["2026-10-02"]["Amount"] == "-250.50" and rows["2026-10-03"]["Amount"] == "15000.00"


def test_category_paths_subcategory_columns_and_split_lines(c, setup):
    import json
    cib = setup[0]["cib"].id
    cats = [x for x in c.categories.pickable() if x.movement.name == "OUTFLOW" and x.parent_id]
    names = [x.name for x in cats if sum(y.name == x.name for y in cats) == 1][:2]
    a, b = names
    data = (f"Date,Amount,Counterparty,Category,Subcategory,Split\n"
            f"2026-10-01,-100,Carrefour,{a},,-70\n2026-10-01,-100,Carrefour,{b},,-30\n"
            f"2026-10-02,-50,Kiosk,Personal:{a},,\n2026-10-03,-20,Uber,Work,{b},\n").encode()
    batch, _ = c.bank_imports.stage(cib, "s.csv", data)
    _, rows = c.bank_imports.preview(batch)
    first, second, path, sub = rows
    assert first["_split_note"] and second["_skip_reason"] and first["_category_id"]
    assert path["Category"] == a and path["Group"] == "Personal"
    assert sub["Group"] == "Work" and sub["Category"] == b
    c.bank_imports.confirm(batch, {first["_import_row_id"]: {}, second["_import_row_id"]: {"skip": True}})
    txn = c.db.scalar("SELECT transaction_id FROM bank_import_rows WHERE id=?", (first["_import_row_id"],))
    cats_used = c.db.all("SELECT DISTINCT category_id FROM ledger_entries WHERE transaction_id=? AND category_id IS NOT NULL", (txn,))
    assert len(cats_used) == 2


def test_merchant_name_is_cleaned_from_the_description_and_the_raw_text_stays_in_notes():
    from lightning.bank_import_parsing import normalize_rows
    from lightning.bank_import_rows import clean_merchant
    assert clean_merchant("UBER *TRIP HELP.UBER.COM") == "Uber"
    assert clean_merchant("CARD PURCHASE TALABAT") == "Talabat"
    assert clean_merchant("ATM WITHDRAWAL") == ""
    mapping = {"Date": "D", "Amount": "A", "Notes": "N"}
    raw = [{"D": "2026-10-01", "A": "-80", "N": "UBER *TRIP HELP.UBER.COM", "__line__": "2"}]
    (_r, parsed), = normalize_rows(raw, mapping, "SINGLE", False)
    assert parsed["Counterparty"] == "Uber" and parsed["Notes"] == "UBER *TRIP HELP.UBER.COM"


def test_a_statement_with_a_row_removed_is_caught_by_its_balance_column():
    from lightning.import_reconcile import balance_gaps
    full = [("2026-10-01", "-100", "900"), ("2026-10-02", "-50", "850"), ("2026-10-03", "-25", "825"), ("2026-10-04", "10", "835")]
    rows = lambda items: [{"Date": d, "Amount": a, "Balance": b, "_line": str(i), "_errors": []}
                          for i, (d, a, b) in enumerate(items, start=2)]
    assert balance_gaps(rows(full)) == []
    assert balance_gaps(rows(full[::-1])) == []  # newest first reads the same
    gaps = balance_gaps(rows(full[:1] + full[2:]))  # the 50 row is gone
    assert len(gaps) == 1 and gaps[0].moved == -75 and gaps[0].added == -25


def test_review_page_shows_the_balance_gap(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    cib = setup[0]["cib"].id
    data = b"Date,Amount,Counterparty,Balance\n2026-10-01,-100,Seoudi,900\n2026-10-03,-25,Uber,825\n"
    batch, _ = c.bank_imports.stage(cib, "g.csv", data)
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get(f"/accounts/{cib}/import/{batch}")
    assert "does not add up" in page.text


def test_a_category_picked_for_a_file_name_reaches_rows_not_drawn(c, setup):
    import json, re
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    cib = setup[0]["cib"].id
    cat = next(x for x in c.categories.pickable() if x.movement.name == "OUTFLOW" and x.parent_id)
    lines = ["Date,Amount,Counterparty,Category"] + [f"2026-10-{1 + i % 28:02d},-{10 + i}.00,{["Seoudi", "Uber", "Netflix"][i % 3]},Zzz Unknown Name" for i in range(300)]
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    r = client.post(f"/accounts/{cib}/import", files={"file": ("l.csv", "\n".join(lines).encode(), "text/csv")}, follow_redirects=False)
    batch = int(re.search(r"/import/(\d+)", r.headers["location"]).group(1))
    done = client.post(f"/accounts/{cib}/import/{batch}/confirm", data={"labelcat": json.dumps(["Zzz Unknown Name", str(cat.id)])}, follow_redirects=False)
    assert done.status_code == 200
    assert c.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='POSTED'", (batch,)) == 300


def test_the_upload_says_where_the_other_accounts_rows_went(c, setup):
    from urllib.parse import unquote
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    cib = setup[0]["cib"].id
    other = next(a for a in c.accounts.list(active_only=True) if a.institution and a.institution != "CIB")
    csv = b"Account,Date,Amount,Counterparty\nCIB Current,2026-10-01,-99,Netflix\nSomething else,2026-10-03,-7,Kiosk\n"
    r = TestClient(create_app(c), base_url="http://127.0.0.1").post(
        f"/accounts/{other.id}/import", files={"file": ("z.csv", csv, "text/csv")}, follow_redirects=False)
    assert r.status_code == 303 and "CIB Current (1)" in unquote(r.headers["location"])


def test_a_name_chosen_once_resolves_in_the_next_file(c, setup):
    cib = setup[0]["cib"].id
    cat = next(x for x in c.categories.pickable() if x.movement.name == "OUTFLOW" and x.parent_id)
    first = b"Date,Amount,Counterparty,Category\n2026-10-01,-10,Seoudi,Zzz Unknown Name\n"
    batch, _ = c.bank_imports.stage(cib, "a.csv", first)
    _, rows = c.bank_imports.preview(batch)
    assert not rows[0]["_category_id"] and rows[0]["_file_label"] == "Zzz Unknown Name"
    c.bank_imports.confirm(batch, {rows[0]["_import_row_id"]: {"category_id": str(cat.id)}})
    second = b"Date,Amount,Counterparty,Category\n2026-11-01,-20,Uber,Zzz Unknown Name\n"
    batch2, _ = c.bank_imports.stage(cib, "b.csv", second)
    _, rows2 = c.bank_imports.preview(batch2)
    assert rows2[0]["_category_id"] == cat.id and rows2[0]["_ready"] and not rows2[0]["_file_label"]


def test_a_movement_written_as_two_lines_is_offered_once(c, setup):
    cib = setup[0]["cib"].id
    data = (b"Date,Amount,Counterparty,Notes\n2026-10-06,4000,,Ownership to you\n"
            b"2026-10-06,-4000,,Ownership from Mama\n2026-10-07,-30,Uber,Ride\n")
    batch, _ = c.bank_imports.stage(cib, "p.csv", data)
    _, rows = c.bank_imports.preview(batch)
    assert not rows[0].get("_skip_reason") and "Pairs with line 2" in rows[1]["_skip_reason"]
    assert not rows[2].get("_skip_reason")
