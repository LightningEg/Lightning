"""The posting and estimate dates stay legible and editable on each transaction detail layout."""
import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import chromium_executable, require_chromium


@pytest.mark.parametrize("phone", [False, True], ids=["desktop", "phone"])
def test_save_and_reset_refund_estimate_date(c, setup, phone):
    require_chromium()
    bank = setup[0]["cib"].id
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    purchase = c.transactions.record_outflow("2026-09-28", bank, 1000, food, description="Groceries")
    refund = c.refunds.record_refund(purchase.id, "2026-10-05", 400)
    app = create_app(c)

    @app.middleware("http")
    async def layout(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=chromium_executable())
            page = browser.new_page(viewport={"width": 390 if phone else 1366, "height": 900},
                                    is_mobile=phone, has_touch=phone)
            page.clock.set_fixed_time("2026-08-01T12:00:00Z")
            page.goto(host.launch_url)
            page.goto(f"{host.origin}/transactions/{refund['refund_id']}")
            panel = page.locator("#refund-link")
            editor = panel.locator("details").filter(has=page.locator('input[name="link_id"]'))
            for day, expected in [("2026-08-15", "2026-08-15"), ("", "2026-09-28")]:
                if not editor.evaluate("el => el.open"):
                    editor.locator("summary").click()
                if phone:
                    editor.get_by_role("button", name="Choose date").click()
                    page.locator(f'[data-day="{day}"]' if day else "[data-clear]").click()
                else:
                    editor.locator('[name="estimate_date"]').fill(day)
                expect(editor.locator('[name="estimate_date"]')).to_have_value(day)
                with page.expect_response(lambda response: response.request.method == "POST" and "/refund-link" in response.url):
                    editor.get_by_role("button", name="Save", exact=True).click()
                assert c.db.scalar("SELECT estimate_date_override FROM refund_links") == (day or None)
                expect(page.locator(f'time[datetime="{expected}"]').first).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            browser.close()
    finally:
        host.stop()
