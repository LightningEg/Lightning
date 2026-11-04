"""PC certificate accounts and the first Budget group use searchable own-data pickers."""
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest

from lightning.runtime.app import SessionGate
from lightning.runtime.http import Guard, Host
from lightning.runtime.roles import SessionRole
from lightning.ui.web import create_app


def test_certificate_and_budget_pickers_preserve_submitted_ids(c, setup):
    pytest.importorskip('playwright')
    from playwright.sync_api import sync_playwright
    chromium = shutil.which('chromium') or ('/opt/pw-browsers/chromium' if Path('/opt/pw-browsers/chromium').exists() else None)
    if not chromium:
        pytest.skip('Chromium is not installed')
    accounts, _ = setup
    from test_cd_interest_match import _scenario
    _scenario(c, setup)
    session = SimpleNamespace(container=c, paths=None, journal=None, borrowed=None, role=SessionRole.HOME,
                              token='test-pc-own-picker-session', csrf='test-pc-own-picker-csrf')
    app = create_app(c)

    @app.get('/profiles/health')
    async def health():
        return {'locked': False, 'session': session.token}

    host = Host(lambda cfg: Guard(SessionGate(app, session), cfg)).start()
    try:
        with sync_playwright() as p:
            with p.chromium.launch(executable_path=chromium, args=['--no-sandbox']) as browser:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                page.goto(host.launch_url)
                page.goto(host.origin + f'/deposits/{accounts["cd"].id}')
                fieldsets = page.locator('.cd-interest-receipt fieldset')
                assert fieldsets.count() >= 3
                assert all(style == '0px' for style in fieldsets.evaluate_all(
                    'els => els.map(el => getComputedStyle(el).borderTopWidth)'))
                page.locator('table details > summary').first.click()
                assert page.locator('button.btn.primary:visible').count() == 1
                assert page.get_by_role('button', name='Record CD purchase').evaluate("el => el.classList.contains('primary')")
                funding = page.get_by_role('combobox', name='Buy from')
                funding.fill('Wallet')
                page.get_by_role('option', name='Wallet · Wallet').click()
                assert page.locator('select[name=funding_account_id]').input_value() == str(accounts['wallet'].id)
                funding.fill('not an account')
                assert not funding.evaluate('el => el.checkValidity()')
                funding.fill('CIB Current')
                page.get_by_role('option', name='CIB · CIB Current').click()
                assert funding.evaluate('el => el.checkValidity()')
                payout = page.get_by_role('combobox', name='Forecast payout account').last
                payout.fill('Wallet')
                page.get_by_role('option', name='Wallet · Wallet').click()
                assert page.locator('select[name=destination_account_id][aria-label="Forecast payout account"]').last.input_value() == str(accounts['wallet'].id)
                page.goto(host.origin + '/budget?period=month&month=2026-09')
                group = page.get_by_role('combobox', name='Spending group')
                group.fill('not a spending group')
                assert not group.evaluate('el => el.checkValidity()')
                group.fill('Personal')
                page.get_by_role('option', name='Personal').click()
                assert page.locator('select[name=group_id]').input_value() == str(c.categories.get_by_code('EXP.PERSONAL').id)
                page.locator('[name=broad_limit]').fill('5000')
                page.get_by_role('button', name='Create plan').click()
                assert c.budgets.has_plan('2026-09', schedule=c.schedules.view())
    finally:
        host.stop()
