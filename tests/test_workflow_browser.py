"""Browser checks for the activity, planning, reimbursement, and review workflows."""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from lightning.runtime.http import Host
from lightning.ui.web import create_app
from tests.browser_support import require_chromium, chromium_executable


CHROMIUM = chromium_executable()


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_workflow_pages_render_fit_and_keep_interactions_usable(c, setup, phone):
    require_chromium()

    accounts, cats = setup
    account = accounts["cib"]
    food = cats["EXP.PERSONAL.FOOD"]
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    expense = c.transactions.record_outflow("2026-12-10", account.id, "25", food.id,
                                            counterparty="Browser grocery")
    duplicate = c.transactions.record_outflow("2026-12-10", account.id, "25", food.id,
                                              counterparty="Browser grocery")
    c.transactions.record_inflow("2026-12-12", account.id, "10", salary.id)
    c.reimbursements.create_claim(expense.id, "25")
    c.budgets.set_budget(food.id, "2026-12", "100", schedule=c.schedules.view())
    view_id = c.saved_views.save("Browser report", {"preset": "all_time"}, account.id)

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
            page.set_default_timeout(5000)
            page_errors = []
            console_errors = []
            failed_static = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("console", lambda message: console_errors.append(message.text)
                    if message.type == "error" and "Failed to load resource" not in message.text else None)
            page.on("response", lambda response: failed_static.append((response.status, response.url))
                    if response.status >= 400 and "/static/" in response.url else None)
            page.goto(host.launch_url)
            origin = host.origin

            pages = [
                "/activity",
                f"/activity/{expense.id}",
                "/payday",
                "/reimbursements",
                "/review",
                f"/transactions/merge?keep={expense.id}&drop={duplicate.id}",
                f"/transactions/views/{view_id}/report?account_id={account.id}",
            ]
            for path in pages:
                page.goto(origin + path, wait_until="networkidle")
                assert page.locator("h1, main h2").count() or page.title(), path
                widths = (320, 390) if phone else (1366,)
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 900})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (path, width)
                assert not page_errors, (path, page_errors)
                if not phone:
                    from test_brand_audit import COLLECT
                    audit = page.evaluate(COLLECT)
                    problems = {key: audit[key] for key in ('upper', 'colors', 'heads', 'fields', 'overflow') if audit[key]}
                    assert not problems, (path, problems)
                assert not console_errors, (path, console_errors)

            # Choose a category through the page's accessible autocomplete and submit it.
            page.set_viewport_size({"width": 390 if phone else 1366, "height": 900})
            page.goto(origin + f"/activity/{expense.id}", wait_until="networkidle")
            category_input = page.locator(".category-input")
            category_input.evaluate("el => el.scrollIntoView({block: 'center'})")
            category_input.fill(transport.name)
            option = page.locator("#activity-category-results .category-option", has_text=transport.name).first
            option.wait_for(state="visible")
            option.click()
            assert page.locator('input[name="category_choice"]').input_value() == str(transport.id)
            with page.expect_response(lambda response: response.request.method == "POST" and
                                      response.url.endswith(f"/activity/{expense.id}/apply")) as result:
                page.locator("#activity-review button.primary").click()
            assert result.value.status == 303
            page.wait_for_load_state("networkidle")
            assert c.transactions.get(expense.id).lines[0].category_id == transport.id
            assert transport.name in page.locator("body").inner_text()

            # Verify the owned-record picker remains usable and posts a real selected value.
            page.goto(origin + "/reimbursements", wait_until="networkidle")
            picker = page.locator('.counterparty-picker input[role="combobox"]').first
            picker.fill("Browser grocery")
            choice = page.locator('.counterparty-results [role="option"]').filter(has_text="Browser grocery").first
            choice.wait_for(state="visible")
            choice.click()
            assert page.locator('select[name="transaction_id"]').input_value() == str(duplicate.id)

            # The optional funding preference can be switched from the page itself.
            page.goto(origin + "/payday", wait_until="networkidle")
            enable = page.get_by_role("button", name="Turn on cash funding")
            if enable.count():
                with page.expect_response(lambda response: response.request.method == "POST" and
                                          response.url.endswith("/payday/enable")) as result:
                    enable.click()
                assert result.value.status == 303
                page.wait_for_load_state("networkidle")
                assert page.get_by_role("button", name="Pause cash funding").count() == 1

            for error in page_errors:
                pytest.fail(f"Browser JavaScript error: {error}")
            assert not console_errors, console_errors
            assert not failed_static, failed_static
            browser.close()
    finally:
        host.stop()
