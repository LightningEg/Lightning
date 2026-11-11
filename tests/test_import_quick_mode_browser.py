"""NF-7AB5: quick mode answers the waiting rows one at a time with the keyboard (1-3, Enter, S)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lightning.ui.routes.bank_imports import _quick_picks
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


def test_quick_mode_answers_five_rows_by_keyboard_and_posts_four(c, setup):
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright
    from lightning.runtime.http import Host

    chromium = require_chromium()
    cib = setup[0]["cib"].id
    names = ["Kiosk Nile", "Corner Shop", "Fuel Point", "Book Stall", "Juice Bar"]
    data = "Date,Counterparty,Amount\n" + "".join(f"2026-09-1{i},{n},-{10 + i}\n" for i, n in enumerate(names))
    batch, _ = c.bank_imports.stage(cib, "quick.csv", data.encode())
    picks = json.loads(_quick_picks(c))["out"]
    assert len(picks) == 3
    host = Host(lambda _: create_app(c)).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chromium))
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(host.launch_url)
            page.goto(f"{host.origin}/accounts/{cib}/import/{batch}")
            page.locator(".import-question[data-state=needs] [data-question-open]").click()
            page.wait_for_selector(".import-question[data-state=needs] .import-line")
            assert page.locator(".import-quick").is_hidden()
            page.locator("[data-quick-start]").click()
            page.wait_for_selector(".import-quick:not([hidden])")
            for key in ("1", "Enter", "s", "2", "Enter"):
                page.keyboard.press(key)
            assert page.locator(".import-quick").is_hidden()
            page.locator("button.btn.primary", has_text="Post ready rows").first.click()
            page.wait_for_selector("text=Import")
            browser.close()
    finally:
        host.stop()
    got = {r["Counterparty"]: (r["_status"], r.get("_transaction_id")) for r in c.bank_imports.preview(batch)[1]}
    assert [got[n][0] for n in names] == ["POSTED", "POSTED", "SKIPPED", "POSTED", "POSTED"]
    expected = {"Kiosk Nile": picks[0]["id"], "Corner Shop": picks[0]["id"], "Book Stall": picks[1]["id"],
                "Juice Bar": picks[0]["id"]}
    for name, category in expected.items():
        assert c.db.scalar("SELECT COUNT(*) FROM ledger_entries WHERE transaction_id=? AND category_id=?",
                           (got[name][1], category)) == 1, name


def test_quick_picks_prefer_the_categories_used_most(c, setup):
    cib = setup[0]["cib"].id
    batch, rows = c.bank_imports.stage(cib, "used.csv", b"Date,Counterparty,Amount\n2026-09-10,A1,-5\n2026-09-11,B2,-6\n")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    _, rows = c.bank_imports.preview(batch)
    c.bank_imports.confirm(batch, {r["_import_row_id"]: {"category_id": str(food), "counterparty_choice": "typed",
                                                         "counterparty": r["Counterparty"]} for r in rows})
    assert json.loads(_quick_picks(c))["out"][0]["id"] == food
    assert TestClient(create_app(c)).get(f"/accounts/{cib}").status_code == 200
