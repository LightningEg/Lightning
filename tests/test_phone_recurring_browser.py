"""The changed-payment warning must remain readable on narrow English and Arabic screens."""
from datetime import date

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from lightning.runtime.http import Host
from lightning.ui.phone.router import mount_phone
from lightning.ui.web import create_app
from tests.browser_support import require_chromium


def test_changed_monthly_payment_warning_fits_phone(c, setup, monkeypatch):
    executable = require_chromium()
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-06')
    accounts, cats = setup
    category = cats['EXP.PERSONAL.FOOD']
    party_id = c.counterparties.create('North Cairo Electricity')
    item_id = c.planning.create(kind='BILL', name='North Cairo Electricity', amount='100', frequency='MONTHLY',
                                start_date='2026-10-02', account_id=str(accounts['cib'].id),
                                category_id=str(category.id), counterparty_id=party_id, match_tolerance_pct='10')
    c.transactions.record_outflow('2026-10-02', accounts['cib'].id, '108', category.id,
                                  counterparty='North Cairo Electricity')
    assert c.planning.match_payments(date(2026, 10, 6)) == 1
    future_party = c.counterparties.create('Future Electricity')
    future_id = c.planning.create(kind='BILL', name='Future Electricity', amount='100', frequency='MONTHLY',
                                  start_date='2026-10-10', account_id=str(accounts['cib'].id),
                                  category_id=str(category.id), counterparty_id=future_party, match_tolerance_pct='10')
    c.transactions.record_outflow('2026-10-06', accounts['cib'].id, '140', category.id,
                                  counterparty='Future Electricity')
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    c.account_flows.open_account('Dollar savings', 'BANK', '2026-09-01', '100', currency='USD',
                                 opening_balance_date='2026-09-01')
    c.fx.save('USD', '2026-09-30', '55')
    assert c.reevaluations.process_date('2026-09-30', 'MONTH_END')
    app = create_app(c)
    mount_phone(app)
    async def phone_app(scope, receive, send):
        scope.setdefault('state', {})['phone'] = True
        await app(scope, receive, send)
    host = Host(lambda _: phone_app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=executable)
            for language in ('en', 'ar'):
                c.settings.set('locale', language)
                context = browser.new_context(viewport={'width': 320, 'height': 800}, is_mobile=True, has_touch=True)
                context.add_cookies([{'name': 'lightning_ui_locale', 'value': language, 'url': host.origin}])
                page = context.new_page()
                for width in (320, 360):
                    page.set_viewport_size({'width': width, 'height': 800})
                    response = page.goto(host.origin + '/plan/recurring')
                    assert response and response.status == 200
                    assert page.locator('html').get_attribute('lang') == ('ar-EG' if language == 'ar' else 'en')
                    warning = page.locator(f'section.phone-card:has(form[action="/plan/items/{item_id}/amount"])')
                    assert warning.count() == 1
                    review = page.locator(f'a.phone-recurring-review[href^="/plan/items/{future_id}/pay?"]')
                    assert review.count() == 1 and review.is_visible()
                    assert review.evaluate('''e => {
                        const r = e.getBoundingClientRect(), name = e.previousElementSibling.getBoundingClientRect();
                        const text = e.querySelector('span').getBoundingClientRect();
                        return r.top >= name.bottom - 1 && r.height >= 48 && text.left >= r.left &&
                               text.right <= r.right && e.scrollWidth <= e.clientWidth + 1;
                    }''')
                    assert warning.evaluate('''e => {
                        const h = e.querySelector('h2').getBoundingClientRect();
                        const p = e.querySelector('p').getBoundingClientRect();
                        const card = e.getBoundingClientRect();
                        return h.bottom <= p.top + 1 && card.left >= 0 && card.right <= innerWidth &&
                          e.scrollWidth <= e.clientWidth + 1;
                    }''')
                    page.goto(host.origin + '/accounts/currencies?period=all')
                    chart = page.locator('.chart-trend').first
                    assert chart.count() == 1
                    legend = chart.locator('.phone-chart-legend')
                    assert legend.locator('.phone-row').count() == 2
                    assert legend.bounding_box()['y'] >= chart.locator('.chart-plot').bounding_box()['y'] + chart.locator('.chart-plot').bounding_box()['height']
                    chart.locator('.chart-table > summary').click()
                    names = chart.locator('.chart-table .phone-row small').all_text_contents()
                    assert len(set(names)) == 2
                    page.goto(host.origin + '/settings?section=currencies&tab=rates')
                    assert page.locator('table').count() == 0
                    assert page.get_by_text('Dollar savings', exact=False).count() > 0
                    assert page.locator('.currency-settings .phone-row').evaluate_all(
                        'rows => rows.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    page.goto(host.origin + '/settings?section=valuations')
                    assert page.locator('table').count() == 0
                    factor_rows = page.locator('.factor-phone-rows .phone-row')
                    assert factor_rows.count() > 0
                    if language == 'ar':
                        assert all('the default' not in t and 'Deposits' not in t for t in page.locator('.factor-from').all_text_contents())
                    assert factor_rows.evaluate_all('rows => rows.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    if language == 'en' and width == 320:
                        factor = factor_rows.locator('input[name=factor]').first
                        with page.expect_response(lambda r: '/settings/liquidation-factor/' in r.url and r.request.method == 'POST') as saved:
                            factor.fill('82')
                            factor.press('Tab')
                        assert saved.value.status == 204
                    page.goto(host.origin + '/plan/loans')
                    ratios = page.locator('[data-loan-ratios] .phone-row')
                    assert ratios.count() == 3
                    assert ratios.evaluate_all('rows => rows.every(e => e.scrollWidth <= e.clientWidth + 1)')
                    page.goto(host.origin + '/transactions?period=month')   # the register; the bare address is Activity now
                    page.locator('.phone-more-menu > summary').first.click()
                    activity = page.locator('.phone-more-menu a[href="/activity"]').first
                    assert activity.is_visible()
                    assert activity.evaluate('e => { const r=e.getBoundingClientRect(); return r.height >= 48 && r.left >= 0 && r.right <= innerWidth; }')
                    page.goto(host.origin + '/review')
                    assert page.locator('details.flow-disclosure > summary').first.bounding_box()['height'] >= 44
                    page.goto(host.origin + '/money/reviews')   # the weekly review sits behind Money's Reports and reviews (IV-11H)
                    assert page.locator('a.phone-row[href="/review"]').first.bounding_box()['height'] >= 48
                context.close()
            browser.close()
    finally:
        host.stop()


def test_phone_recurring_suggestion_menu_can_dismiss_and_restore(c, setup, monkeypatch):
    executable = require_chromium()
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    accounts, cats = setup
    party_id = c.counterparties.create('Monthly Gym')
    for day in ('2026-10-05', '2026-11-05', '2026-12-05'):
        c.transactions.record_outflow(day, accounts['cib'].id, '100', cats['EXP.PERSONAL.FOOD'].id,
                                      counterparty='Monthly Gym')
    app = create_app(c)
    async def phone_app(scope, receive, send):
        scope.setdefault('state', {})['phone'] = True
        await app(scope, receive, send)
    host = Host(lambda _: phone_app).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=executable)
            for language in ('en', 'ar'):
                c.settings.set('locale', language)
                context = browser.new_context(viewport={'width': 320, 'height': 800}, is_mobile=True, has_touch=True)
                page = context.new_page()
                for width in (320, 360):
                    page.set_viewport_size({'width': width, 'height': 800})
                    assert page.goto(host.origin + '/plan/recurring').status == 200
                    assert page.locator('html').get_attribute('lang') == ('ar-EG' if language == 'ar' else 'en')
                    row = page.locator('.phone-suggest').filter(has_text='Monthly Gym')
                    assert row.count() == 1
                    actions = row.locator('xpath=following-sibling::div[1]')
                    assert '/plan/items/new?' in actions.locator('a').first.get_attribute('href')
                    actions.locator('summary').click()
                    dismiss = actions.locator('form[action$="/not-recurring"] button')
                    assert dismiss.is_visible() and dismiss.bounding_box()['height'] >= 48
                    with page.expect_response(lambda r: r.url.endswith('/not-recurring') and r.request.method == 'POST') as posted:
                        dismiss.click()
                    assert posted.value.status == 303
                    page.wait_for_load_state()
                    assert page.locator('.phone-suggest').filter(has_text='Monthly Gym').count() == 0
                    restore = page.locator(f'form[action="/plan/suggestions/{party_id}/restore"]')
                    restore.locator('xpath=ancestor::details[1]/summary').click()
                    assert restore.locator('button').is_visible()
                    with page.expect_response(lambda r: r.url.endswith('/restore') and r.request.method == 'POST') as restored:
                        restore.locator('button').click()
                    assert restored.value.status == 303
                    page.wait_for_load_state()
                context.close()
            browser.close()
    finally:
        host.stop()
