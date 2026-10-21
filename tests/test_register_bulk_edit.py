"""U2: edit many register rows at once; only the changed fields apply, amounts never do."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.ui.web import create_app


NAMES = ["Carrefour", "Vodafone", "Zamalek Club"]


@pytest.fixture
def client(c):
    return TestClient(create_app(c))


@pytest.fixture
def rows(c, setup):
    accounts, cats = setup
    cib = accounts["cib"]
    food = cats["EXP.PERSONAL.FOOD"]
    made = [c.transactions.record_in_account(cib.id, f"2026-09-1{n}", f"-{100 * n}", food.id, None, NAMES[n - 1], "")
            for n in (1, 2, 3)]
    return c, accounts, cats, made


def test_bulk_edit_changes_category_and_notes_and_leaves_amounts(rows):
    c, accounts, cats, made = rows
    software = cats["EXP.WORK.SOFTWARE"]
    changed, skipped = c.transactions.bulk_update([t.id for t in made], {"category_id": software.id, "notes": "team plan"})
    assert changed == [t.id for t in made] and skipped == []
    for n, t in enumerate(made, 1):
        now = c.transactions.get(t.id)
        assert now.notes == "team plan" and now.counterparty == NAMES[n - 1] and now.date == f"2026-09-1{n}"
        assert any(line.category_id == software.id for line in now.lines)
        cash = next(line for line in now.lines if c.assets.get_asset(line.asset_id).is_cash)
        assert cash.quantity == D(-100 * n)


def test_only_changed_fields_apply(rows):
    c, accounts, cats, made = rows
    c.transactions.bulk_update([t.id for t in made], {"notes": "only notes"})
    now = c.transactions.get(made[0].id)
    assert now.notes == "only notes" and now.counterparty == NAMES[0]
    assert any(line.category_id == cats["EXP.PERSONAL.FOOD"].id for line in now.lines)


def test_rows_that_cannot_take_the_change_are_skipped_and_counted(rows):
    c, accounts, cats, made = rows
    stock = c.assets.create_investment("Commercial International Bank", "STOCK", "COMI")
    c.transactions.record_transfer("2026-09-02", accounts["cib"].id, accounts["thndr"].id, "30000")
    buy = c.investments.buy_total("2026-09-10", accounts["thndr"].id, stock.id, "10", "1000")
    changed, skipped = c.transactions.bulk_update([made[0].id, buy.id], {"counterparty": "Somewhere"})
    assert changed == [made[0].id] and skipped == [buy.id]
    assert c.transactions.get(made[0].id).counterparty == "Somewhere"


def test_bulk_edit_route_flashes_and_applies(client, rows):
    c, accounts, cats, made = rows
    r = client.post("/transactions/bulk-edit", follow_redirects=False,
                    data={"txn_ids": [str(t.id) for t in made], "notes": "bulk", "category": "Software",
                          "category_choice": str(cats["EXP.WORK.SOFTWARE"].id), "back": "/accounts/%d" % accounts["cib"].id})
    assert r.status_code in (302, 303)
    assert all(c.transactions.get(t.id).notes == "bulk" for t in made)


def test_bulk_category_still_works(client, rows):
    c, accounts, cats, made = rows
    client.post("/transactions/bulk-category", follow_redirects=False,
                data={"txn_ids": [str(t.id) for t in made], "category_id": str(cats["EXP.WORK.SOFTWARE"].id)})
    assert all(any(l.category_id == cats["EXP.WORK.SOFTWARE"].id for l in c.transactions.get(t.id).lines) for t in made)


def test_edit_page_carries_original_values_for_the_dialog(client, rows):
    c, accounts, cats, made = rows
    html = client.get(f"/accounts/{accounts['cib'].id}?edit={made[0].id}&acct={accounts['cib'].id}").text
    assert "data-original='" in html and NAMES[0] in html


@pytest.fixture
def register_browser(rows):
    """Exercise native checkbox, navigation and submit events, rather than inspecting JS text."""
    import shutil
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host

    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("Chromium is not installed")
    c, accounts, cats, made = rows
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chromium, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.goto(host.launch_url)
            page.goto(f"{host.origin}/accounts/{accounts['cib'].id}")
            yield page, host, made
            browser.close()
    finally:
        host.stop()


def test_browser_selection_range_clear_and_cancel(register_browser):
    page, host, made = register_browser
    boxes = page.locator(".transaction-select:not(:disabled)")
    boxes.first.check()
    boxes.nth(2).click(modifiers=["Shift"])
    assert page.locator("#selection-count").inner_text() == "3 selected"
    assert page.locator("#select-visible").is_checked()
    page.locator("#edit-selected").click()
    page.wait_for_selector("tr.editing")
    assert page.locator("#selection-count").inner_text() == "3 selected"
    page.locator("tr.editing [data-cancel]").evaluate("a => a.click()")
    page.wait_for_selector("tr.editing", state="detached")
    assert page.locator(".transaction-select:checked").count() == 3
    page.reload()
    assert page.locator(".transaction-select:checked").count() == 3
    page.locator("#clear-selected").click()
    assert page.locator("#selection-tools").is_hidden()
    assert page.locator(".transaction-select:checked").count() == 0


def test_browser_bulk_notes_save_and_cancel_dialog(register_browser, rows):
    page, host, made = register_browser
    page.locator("#select-visible").check()
    page.locator("#edit-selected").click()
    page.wait_for_selector("tr.editing")
    page.locator('[form="f-edit"][name="notes"]').fill("shared note")
    page.locator("#f-edit").evaluate("f => { f.requestSubmit(); f.requestSubmit(); }")
    page.wait_for_selector("dialog[open]")
    assert page.locator("dialog[open]").count() == 1
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.wait_for_selector("dialog.ask-dialog", state="detached")
    assert page.locator(".transaction-select:checked").count() == 3
    assert page.locator('[form="f-edit"][name="notes"]').input_value() == "shared note"
    assert page.locator("#f-edit").get_attribute("data-submitting") != "true"
    page.locator("#f-edit").evaluate("f => f.requestSubmit()")
    page.wait_for_selector("dialog[open]")
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.ask-dialog", state="detached")
    assert page.locator("tr.editing").count() == 1
    assert page.locator('[form="f-edit"][name="notes"]').input_value() == "shared note"
    assert page.locator(".transaction-select:checked").count() == 3
    page.locator("#f-edit").evaluate("f => f.requestSubmit()")
    page.get_by_role("button", name="All 3 rows", exact=True).click()
    page.wait_for_selector("tr.editing", state="detached")
    assert all(rows[0].transactions.get(t.id).notes == "shared note" for t in made)
    assert page.locator(".transaction-select:checked").count() == 0


def test_browser_amount_change_is_never_silently_discarded(register_browser, rows):
    page, host, made = register_browser
    page.locator("#select-visible").check()
    page.locator("#edit-selected").click()
    page.wait_for_selector("tr.editing")
    txn_id = int(page.locator("tr.editing").get_attribute("data-txn"))
    page.locator('[form="f-edit"][name="notes"]').fill("one row")
    page.locator('[form="f-edit"][name="amount"]').fill("-350")
    page.locator("#f-edit").evaluate("f => f.requestSubmit()")
    page.wait_for_selector("dialog[open]")
    assert page.get_by_role("button", name="All 3 rows", exact=True).count() == 0
    page.get_by_role("button", name="Only this row", exact=True).click()
    page.wait_for_selector("tr.editing", state="detached")
    saved = rows[0].transactions.get(txn_id)
    assert saved.notes == "one row" and saved.lines[0].quantity == D("-350")
    assert all(rows[0].transactions.get(t.id).notes == "" for t in made if t.id != txn_id)
    page.wait_for_selector("#selection-tools:not([hidden])")
    assert page.locator(".transaction-select:checked").count() == 3


def test_browser_unselected_edit_does_not_change_selected_rows(register_browser, rows):
    page, host, made = register_browser
    page.locator(f'.transaction-select[value="{made[0].id}"]').check()
    page.locator(f'.transaction-select[value="{made[1].id}"]').check()
    page.locator(f'tr:has(.transaction-select[value="{made[2].id}"]) .register-notes-cell').click()
    page.wait_for_selector("tr.editing")
    page.locator('[form="f-edit"][name="notes"]').fill("separate edit")
    page.locator("#f-edit").evaluate("f => f.requestSubmit()")
    page.wait_for_selector("tr.editing", state="detached")
    assert rows[0].transactions.get(made[2].id).notes == "separate edit"
    assert all(rows[0].transactions.get(t.id).notes == "" for t in made[:2])


def test_browser_selection_does_not_leak_into_a_filtered_view(register_browser):
    page, host, made = register_browser
    page.locator("#select-visible").check()
    page.goto(page.url.split("?")[0] + "?q=Carrefour")
    assert page.locator(".transaction-select:checked").count() == 0
    assert page.locator("#selection-tools").is_hidden()


def test_bulk_edit_rejects_an_account_code_as_counterparty(client, rows):
    c, accounts, cats, made = rows
    result = client.post("/transactions/bulk-edit", follow_redirects=False,
                         data={"txn_ids": [str(t.id) for t in made], "counterparty": accounts["wallet"].code})
    assert "Turn%20a%20row" in result.headers["location"]
    assert [c.transactions.get(t.id).counterparty for t in made] == NAMES


def test_browser_phone_select_all_and_clear(rows):
    import shutil
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host

    if not shutil.which("chromium"):
        pytest.skip("Chromium is not installed")
    c, accounts, cats, made = rows
    app = create_app(c)

    async def phone(scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})["phone"] = True
        await app(scope, receive, send)

    host = Host(lambda _: phone).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(host.launch_url)
            page.goto(f"{host.origin}/accounts/{accounts['cib'].id}?select=1")
            assert page.locator("#phone-bulk button:enabled").count() == 0
            page.locator("#phone-select-visible").check()
            assert page.locator(".transaction-select:checked").count() == 3
            assert page.locator("#phone-bulk button:enabled").count() == 2
            page.locator(".transaction-select:not(:disabled)").first.uncheck()
            assert page.locator("#phone-select-visible").evaluate("e => e.indeterminate")
            assert page.locator("#phone-merge-selected").is_visible()
            page.locator("#phone-select-visible").check()
            page.locator("#phone-select-visible").uncheck()
            assert page.locator(".transaction-select:checked").count() == 0
            assert page.locator("#phone-bulk button:enabled").count() == 0
            for width in (360, 320):
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator('label:has(#phone-select-visible)').bounding_box()["height"] >= 48
            page.screenshot(path="/tmp/lightning-phone-selection.png", full_page=True)
            browser.close()
    finally:
        host.stop()
