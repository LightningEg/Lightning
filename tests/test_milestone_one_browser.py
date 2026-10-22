"""New actions work inside the existing PC dialog and phone sheet."""
from pathlib import Path
import shutil

import pytest

pytest.importorskip('playwright')
from playwright.sync_api import sync_playwright
from lightning.runtime.http import Host
from lightning.ui.web import create_app

CHROMIUM = Path('/opt/pw-browsers/chromium')
if not CHROMIUM.exists():
    CHROMIUM = Path(shutil.which('chromium') or str(CHROMIUM))


@pytest.mark.parametrize('phone', [False, True], ids=['pc', 'phone'])
def test_purchase_preview_edit_save_and_export_download(c, setup, phone, tmp_path):
    if not CHROMIUM.exists():
        pytest.skip('Chromium is not installed')
    app = create_app(c)
    @app.middleware("http")
    async def phone_frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(CHROMIUM))
            page = browser.new_page(viewport={'width': 360 if phone else 1366, 'height': 800}, accept_downloads=True)
            page.goto(host.launch_url)
            page.goto(host.origin + '/plan/loans')
            page.locator('a[href="/plan/purchases/new"]').click()
            page.locator('#app-popup-content input[name=name]').fill('Phone')
            page.locator('#app-popup-content input[name=price]').fill('3000')
            page.locator('#app-popup-content input[name=months]').fill('3')
            page.locator('#app-popup-content input[name=first_date]').fill('2027-01-01')
            page.locator('#app-popup-content button.btn.primary').click()
            page.locator('#app-popup-content input[name=intent][value=save]').wait_for(state='attached')
            assert page.locator('#app-popup').is_visible()
            assert '1,000.00' in page.locator('#app-popup-content').inner_text()
            page.locator('#app-popup-content a', has_text='Edit').click()
            assert page.locator('#app-popup-content input[name=price]').input_value().replace(',', '') == '3000'
            page.locator('#app-popup-content button.btn.primary').click()
            page.locator('#app-popup-content input[name=intent][value=save]').wait_for(state='attached')
            page.locator('#app-popup-content button.btn.primary').click()
            page.wait_for_url('**/plan/loans*')
            # The sheet leaves the URL on /plan/loans while saving, so the URL alone does not wait for the new row.
            page.locator('.plan-loan').get_by_role('link', name='Phone', exact=True).wait_for()
            page.locator('a[href$="/early-payment"]').click()
            page.locator('#app-popup-content input[name=principal]').fill('1000')
            page.locator('#app-popup-content input[role=combobox]').fill('CIB')
            page.locator('#app-popup-content [role=option]', has_text='CIB Current').click()
            page.locator('#app-popup-content button.btn.primary').click()
            page.locator('#app-popup-content input[name=intent][value=record]').wait_for(state='attached')
            assert '2,000' in page.locator('#app-popup-content').inner_text()
            page.locator('#app-popup-content button.btn.primary').click()
            page.wait_for_url('**/plan/loans*')
            page.locator('a[href$="/early-payment"]').wait_for()
            page.goto(host.origin + '/settings')
            page.locator('a[href="/exports/all"]').click()
            with page.expect_download() as result:
                page.locator('#app-popup-content button.btn.primary').click()
            assert result.value.suggested_filename == 'lightning-all-data.xlsx'
            for path in ('/setup/salary', '/plan/purchases/new', '/exports/all'):
                page.goto(host.origin + path)
                if phone:
                    for width in (360, 320):
                        page.set_viewport_size({'width': width, 'height': 800})
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                else:
                    from test_brand_audit import COLLECT
                    audit = page.evaluate(COLLECT)
                    assert not {key: audit[key] for key in ('upper', 'colors', 'links', 'heads', 'fields', 'overflow') if audit[key]}, (path, audit)
            browser.close()
    finally:
        host.stop()
