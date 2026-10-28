"""Browser checks for the linked-section pages (NF-7T): they fit PC and phone and pass the brand audit."""
from pathlib import Path
import os
import shutil

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from lightning.bootstrap import build
from lightning.runtime.http import Host
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app

CHROMIUM = Path("/opt/pw-browsers/chromium")
if not CHROMIUM.exists():
    CHROMIUM = Path(shutil.which("chromium") or str(CHROMIUM))
SHOTS = os.environ.get("LIGHTNING_SHOTS", "")


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_linked_pages_fit_and_pass_the_audit(tmp_path, monkeypatch, phone):
    if not CHROMIUM.exists():
        pytest.skip("Chromium is not installed")
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "t.db")
    load_mohab_2026(c)
    loan_txn = c.db.scalar("SELECT p.transaction_id FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
                           "WHERE i.kind='LOAN' AND p.transaction_id IS NOT NULL ORDER BY p.due_date LIMIT 1")
    claim_txn = c.reimbursements.list_claims()[0]["expense_id"]
    pages = [f"/transactions/{loan_txn}", f"/transactions/{claim_txn}", "/counterparties/1", "/counterparties/13",
             "/accounts/1", "/tags/eid"]
    app = create_app(c)

    @app.middleware("http")
    async def phone_frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={"width": 390 if phone else 1366, "height": 900},
                                    is_mobile=phone, has_touch=phone)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(host.launch_url)
            for path in pages:
                page.goto(host.origin + path, wait_until="networkidle")
                for width in ((320, 390) if phone else (1366,)):
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (path, width)
                assert not errors, (path, errors)
                if SHOTS:
                    page.screenshot(path=f"{SHOTS}/{'phone' if phone else 'pc'}{path.replace('/', '_')}.png", full_page=True)
                if not phone:
                    from test_brand_audit import COLLECT
                    audit = page.evaluate(COLLECT)
                    problems = {key: audit[key] for key in ('upper', 'colors', 'heads', 'fields', 'overflow') if audit[key]}
                    assert not problems, (path, problems)
            browser.close()
    finally:
        host.stop()
        c.db.close()
