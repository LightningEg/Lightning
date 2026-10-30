"""Import review as rows (feedback batch 004, T12 to T14): every row has its own counterparty, category and
held-for, so "money in from Dad" and "transfer to THNDR held for Dad" can both be right."""
from __future__ import annotations

from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _stage(c, account_id, csv_text, name="statement.csv"):
    batch_id, _ = c.bank_imports.stage(account_id, name, csv_text.encode())
    return batch_id, c.bank_imports.preview(batch_id)[1]


def _post(c, account_id, batch_id, answers):
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    return client.post(f"/accounts/{account_id}/import/{batch_id}/confirm", data=answers, follow_redirects=False)


def _ids(rows):
    return {int(r["_line"]): r["_import_row_id"] for r in rows}


def test_the_dad_scenario_posts_both_rows_with_the_right_owner(c, setup):
    accounts, _ = setup
    cib, thndr = accounts["cib"].id, accounts["thndr"].id
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,INSTAPAY FROM DAD,20000\n"
                                 "2026-09-11,TRANSFER TO THNDR,-20000\n")
    ids = _ids(rows)
    answers = {
        f"counterparty_{ids[2]}": "Dad", f"counterparty_pick_{ids[2]}": "new:Dad",   # money in from Dad ...
        f"whom_{ids[2]}": "Dad", f"whom_pick_{ids[2]}": "new:Dad",                  # ... that he asked you to hold
        f"counterparty_{ids[3]}": "THNDR", f"counterparty_pick_{ids[3]}": f"account:{thndr}",  # your account: a transfer
        f"whom_{ids[3]}": "Dad", f"whom_pick_{ids[3]}": "new:Dad",                  # of Dad's money
    }
    response = _post(c, cib, batch, answers)
    assert response.status_code == 200 and "Import complete" in response.text, response.text[-600:]
    summary = c.bank_imports.summary(batch)
    assert summary["posted"] == 2
    dads = [p for p in c.counterparties.list_active() if p["name"] == "Dad"]
    assert len(dads) == 1                                   # created once, from both wells
    mfo = c.money_from_others
    assert mfo.cash_balance("Dad", cib, "2026-09-30") == D("0")      # it left the bank ...
    assert mfo.cash_balance("Dad", thndr, "2026-09-30") == D("20000")  # ... still Dad's, now at THNDR
    assert c.db.scalar("SELECT COUNT(*) FROM transactions WHERE type='TRF' AND status='POSTED'") == 1


def test_two_rows_with_the_same_imported_name_can_get_different_counterparties(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,INSTAPAY,-100\n2026-09-11,INSTAPAY,-200\n")
    ids = _ids(rows)
    food = str(cats["EXP.PERSONAL.FOOD"].id)
    response = _post(c, cib, batch, {
        f"counterparty_{ids[2]}": "Alpha", f"counterparty_pick_{ids[2]}": "new:Alpha", f"category_{ids[2]}": food,
        f"counterparty_{ids[3]}": "Beta", f"counterparty_pick_{ids[3]}": "new:Beta", f"category_{ids[3]}": food})
    assert "Import complete" in response.text
    names = {r["counterparty_id"]: r["name"] for r in c.db.all(
        "SELECT t.counterparty_id, p.name FROM transactions t JOIN counterparties p ON p.id=t.counterparty_id")}
    assert sorted(names.values()) == ["Alpha", "Beta"]
    # the statement's own spelling is remembered for both, so next time it resolves
    assert c.counterparties.resolve("INSTAPAY") is not None


def test_a_new_counterparty_typed_on_several_rows_is_made_once(c, setup):
    accounts, cats = setup
    cib = accounts["cib"].id
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,A,-10\n2026-09-11,B,-20\n2026-09-12,C,-30\n")
    ids = _ids(rows)
    answers = {}
    for line in (2, 3, 4):
        answers[f"counterparty_{ids[line]}"] = "Shop"
        answers[f"counterparty_pick_{ids[line]}"] = "new:Shop"
        answers[f"category_{ids[line]}"] = str(cats["EXP.PERSONAL.FOOD"].id)
    assert "Import complete" in _post(c, cib, batch, answers).text
    assert len([p for p in c.counterparties.list_active() if p["name"] == "Shop"]) == 1


def test_held_for_on_a_transfer_with_no_category_moves_the_custody(c, setup):
    accounts, _ = setup
    cib, wallet = accounts["cib"].id, accounts["wallet"].id
    mom = c.counterparties.create("Mom")
    custody = c.categories.get_by_code("EXP.SYSTEM.CUSTODY")
    txn = c.transactions.record_inflow("2026-09-05", cib, "5000", custody.id, allow_system_category=True)
    c.money_from_others.sync_transaction(txn.id, "2026-09-05", "Mom", cib, D("5000"))
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,WALLET TOPUP,-3000\n")
    row = rows[0]["_import_row_id"]
    response = _post(c, cib, batch, {
        f"counterparty_{row}": "Wallet", f"counterparty_pick_{row}": f"account:{wallet}",
        f"whom_{row}": "Mom", f"whom_pick_{row}": f"counterparty:{mom}"})
    assert "Import complete" in response.text, response.text[-500:]
    assert c.money_from_others.cash_balance("Mom", wallet, "2026-09-30") == D("3000")
    assert c.money_from_others.cash_balance("Mom", cib, "2026-09-30") == D("2000")


def test_the_review_page_is_rows_with_chips_and_a_bulk_bar(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,SHOP,-10\n2026-09-11,SHOP,-20\n")
    page = TestClient(create_app(c), base_url="http://127.0.0.1").get(f"/accounts/{cib}/import/{batch}").text
    assert page.count('<div class="import-line is-') == 2
    for chip in ("All", "To fix", "Needs you", "Possible duplicates", "Ready"):
        assert f"{chip} " in page
    assert 'id="import-bulk"' in page and "Use this category for this counterparty next time" in page
    assert 'name="group_' not in page and "Save as" not in page


def test_bulk_bar_writes_into_the_ticked_rows_and_posts(c, setup):
    """Browser: tick a name, fill the bar, Apply, then post; the account shows both rows with the new counterparty."""
    import shutil
    from pathlib import Path

    import pytest
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host

    chromium = Path("/opt/pw-browsers/chromium")
    if not chromium.exists():
        chromium = Path(shutil.which("chromium") or str(chromium))
    if not chromium.exists():
        pytest.skip("Chromium is not installed")
    accounts, cats = setup
    cib = accounts["cib"].id
    batch, rows = _stage(c, cib, "Date,Counterparty,Amount\n2026-09-10,SHOP,-10\n2026-09-11,SHOP,-20\n")
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chromium))
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            page.goto(host.launch_url)
            page.goto(f"{host.origin}/accounts/{cib}/import/{batch}")
            assert page.locator("#import-bulk").is_hidden()
            page.locator(".import-pick-group").first.check()
            assert page.locator("#import-bulk").is_visible()
            assert page.locator("[data-bulk-count]").inner_text() == "2"
            page.locator("#bulk-cp").fill("Mega Shop")
            page.locator("#bulk-cp-pick").evaluate("e => e.value = 'new:Mega Shop'")
            page.locator("#bulk-category").evaluate(
                f"e => {{ e.value = '{cats['EXP.PERSONAL.FOOD'].id}'; e.dispatchEvent(new Event('change', {{bubbles: true}})); }}")
            page.locator("[data-bulk-apply]").click()
            ids = _ids(rows)
            assert page.locator(f"#cp-{ids[2]}").input_value() == "Mega Shop"
            assert page.locator(f"#cp-pick-{ids[3]}").input_value() == "new:Mega Shop"
            assert page.locator(f"#category-{ids[2]}").input_value() == str(cats["EXP.PERSONAL.FOOD"].id)
            page.locator("button.btn.primary", has_text="Post ready rows").first.click()
            page.wait_for_selector("text=Import complete")
            browser.close()
    finally:
        host.stop()
    assert len([p for p in c.counterparties.list_active() if p["name"] == "Mega Shop"]) == 1
    assert c.bank_imports.summary(batch)["posted"] == 2


def _income_code(c):
    return c.db.scalar("SELECT id FROM categories WHERE code LIKE 'INC.%' ORDER BY id LIMIT 1")


def test_same_day_money_in_posts_first_when_the_day_ends_above_zero(c, setup):
    accounts, cats = setup
    fresh = c.account_flows.open_account("Fresh", "BANK", "2026-09-01", "0").id
    batch, rows = _stage(c, fresh, "Date,Counterparty,Amount\n2026-09-10,Carrefour,-2000\n2026-09-10,Zara,-500\n"
                                   "2026-09-10,Employer,10000\n")
    ids = _ids(rows)
    food = str(cats["EXP.PERSONAL.FOOD"].id)
    response = _post(c, fresh, batch, {
        f"counterparty_{ids[2]}": "Carrefour", f"category_{ids[2]}": food,
        f"counterparty_{ids[3]}": "Zara", f"category_{ids[3]}": food,
        f"counterparty_{ids[4]}": "Employer", f"category_{ids[4]}": str(_income_code(c))})
    assert "Import complete" in response.text
    assert c.bank_imports.summary(batch)["posted"] == 3
    assert c.reconciliation.balance(fresh, "2026-09-10") == D("7500")
    posted = c.db.all("SELECT t.id, le.quantity_e6 q FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                      "WHERE le.account_id=? AND t.status='POSTED' AND le.quantity_e6<>0 ORDER BY t.id", (fresh,))
    running = D(0)
    for row in posted:                                     # money in first: never below zero while posting
        running += D(row["q"]) / D(1_000_000)
        assert running >= 0


def test_a_day_ending_below_zero_keeps_statement_order(c, setup):
    accounts, cats = setup
    fresh = c.account_flows.open_account("Fresh", "BANK", "2026-09-01", "0").id
    batch, rows = _stage(c, fresh, "Date,Counterparty,Amount\n2026-09-10,Carrefour,-2000\n2026-09-10,Employer,10\n")
    ids = _ids(rows)
    order = []
    orig = c.bank_imports._post_import_row
    c.bank_imports._post_import_row = lambda b, rid, *a, **k: (order.append(rid), orig(b, rid, *a, **k))[1]
    c.bank_imports.confirm(batch, {ids[2]: {"counterparty": "Carrefour", "category": str(cats["EXP.PERSONAL.FOOD"].id)},
                                   ids[3]: {"counterparty": "Employer", "category": str(_income_code(c))}})
    assert order[:2] == [ids[2], ids[3]]


def test_a_new_counterparty_on_the_review_page_is_saved_at_once(c, setup):
    """"+ New counterparty" does not wait for "Post ready rows" (owner, 2026-10-30): the name exists as soon as it is chosen,
    a name that already matches is reused, and "Held for" saves a person."""
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    accounts, _ = setup
    client = TestClient(create_app(c))
    url = f"/accounts/{accounts['cib'].id}/import/counterparty"
    made = client.post(url, data={"name": "  Uber   Egypt "}).json()
    assert made["name"] == "Uber Egypt" and made["pick"] == f"counterparty:{made['id']}"
    assert c.counterparties.resolve("uber egypt")["id"] == made["id"]
    assert client.post(url, data={"name": "UBER EGYPT"}).json()["id"] == made["id"]  # never doubled
    person = client.post(url, data={"name": "Fatma Abdullah", "kind": "PERSON"}).json()
    assert c.counterparties.get(person["id"])["kind"] == "PERSON"
    refused = client.post(url, data={"name": "   "})
    assert refused.status_code == 400 and refused.json()["error"]


def test_merging_a_counterparty_moves_its_history_and_keeps_its_names_as_aliases(c, setup):
    """Merge contacts (owner request, 2026-10-30): the old name's transactions follow the kept name, and both the old name and
    its aliases lead there afterwards."""
    from fastapi.testclient import TestClient
    from lightning.core.errors import ValidationError
    from lightning.ui.web import create_app
    accounts, cats = setup
    bank = accounts['cib'].id
    keep = c.counterparties.create("Uber")
    drop = c.counterparties.create("Uber Downtown", alias="UBER TRIP CAIRO")
    client = TestClient(create_app(c))
    for name in ("Uber Downtown", "Uber"):
        assert client.post(f'/accounts/{bank}/register', data={
            'date': '2026-12-30', 'amount': '-85', 'counterparty': name,
            'category': cats['EXP.PERSONAL.FOOD'].name}).status_code == 200
    page = client.get('/counterparties').text
    assert 'name="merge_into"' in page and 'value="merge"' in page and 'id="merge-parties"' in page
    done = client.post('/counterparties', data={'counterparty_action': 'merge', 'counterparty_id': str(drop),
                                                'merge_into': f'counterparty:{keep}'})
    assert done.status_code == 200 and 'Merged Uber Downtown into Uber.' in done.text
    assert c.counterparties.get(drop) is None
    assert c.db.scalar('SELECT count(*) FROM transactions WHERE counterparty_id=?', (keep,)) == 2
    assert c.counterparties.resolve("uber downtown")["id"] == keep
    assert c.counterparties.resolve("UBER TRIP CAIRO")["id"] == keep
    try:
        c.counterparties.merge(keep, keep)
        assert False, "merging a name into itself must be refused"
    except ValidationError:
        pass


def test_same_named_categories_are_never_guessed_between(c, setup):
    """Personal and Work both have a "Transportation": a CSV row that says just that is left for the person (with the two
    choices named), and the register's own text for a shared name carries its group (owner, 2026-10-30: ids, not names)."""
    from lightning.ui.routes.register import counterparty_category_map
    personal = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT")
    party = c.counterparties.create("Uber Test", default_category_id=personal.id)
    row = {"Category": "Transportation", "Amount": "-10", "Counterparty": "Uber Test"}
    assert c.bank_imports._category_for(row, c.counterparties.get(party), None, lambda: {}) is None
    assert "Personal › Transportation" in row["_category_ambiguous"] and "Work › Transportation" in row["_category_ambiguous"]
    exact = {"Category": "Work › Transportation", "Amount": "-10", "Counterparty": "Uber Test"}
    assert c.bank_imports._category_for(exact, c.counterparties.get(party), None, lambda: {}) == work.id
    shown = counterparty_category_map(c, ["Uber Test"])["Uber Test"]
    assert shown == {"id": personal.id, "name": "Personal › Transportation"}
