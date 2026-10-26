"""Real browser regressions for selection, forecast baselines and reserve criteria."""
from pathlib import Path

import pytest
pytest.importorskip('playwright.sync_api')
from playwright.sync_api import sync_playwright

from lightning.runtime.http import Host
from lightning.ui.web import create_app


@pytest.fixture
def browser_page(c):
    if not Path('/usr/bin/chromium').exists():
        pytest.skip('System Chromium not installed')
    app = create_app(c)
    host = Host(lambda _: app).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':1366,'height':1000})
            page.set_default_timeout(5000)
            page.goto(host.launch_url)
            yield page, host.origin
            browser.close()
    finally:
        host.stop()


def test_register_selection_survives_edit_without_submitting(c, setup, browser_page):
    page, origin = browser_page
    accounts, cats = setup
    account = accounts['cib']
    txns = [c.transactions.record_outflow('2026-09-10', account.id, str(10+i), cats['EXP.PERSONAL.FOOD'].id, counterparty=['Carrefour','Vodafone','Bakery'][i]) for i in range(3)]
    for _ in range(120):
        c.transactions.record_outflow('2026-09-09', account.id, '1', cats['EXP.PERSONAL.FOOD'].id, counterparty='Bakery')
    transfer = c.transactions.record_transfer('2026-09-10', account.id, accounts['wallet'].id, '5')
    page.goto(origin+'/transactions')
    box = lambda t: page.locator(f'.ledger .transaction-select[value="{t.id}"]')
    def selected(expected, all_=False):
        actual = page.locator('.ledger .transaction-select:checked').evaluate_all('xs=>[...new Set(xs.map(x=>x.value))].sort()')
        assert actual == sorted(str(t.id) for t in expected)
        assert page.locator('#select-visible').evaluate('(x)=>x.indeterminate') == (bool(expected) and not all_)
        if expected:
            assert page.locator('#selection-count').inner_text() == f'{len(expected)} selected'
        assert page.locator('dialog[open]').count() == 0
    box(txns[0]).check(); box(txns[1]).check()
    selected(txns[:2])
    box(txns[0]).locator('xpath=ancestor::tr').locator('.register-counterparty-cell').click()
    page.wait_for_selector('tr.editing')
    selected(txns[:2])
    editing_url = page.url
    page.evaluate("""() => { window.selectionScans=0; const ledger=document.querySelector('.ledger'); const original=ledger.querySelectorAll; ledger.querySelectorAll=function(s){if(s.includes('transaction-select')) window.selectionScans++; return original.call(this,s)}; }""")
    box(txns[0]).uncheck(); selected([txns[1]])
    box(txns[2]).check(); selected(txns[1:])
    box(transfer).first.check()
    assert box(transfer).count() == 2
    assert box(transfer).evaluate_all('xs=>xs.every(x=>x.checked)')
    box(transfer).last.uncheck(); selected(txns[1:])
    page.locator('#select-visible').check()
    assert page.locator('.ledger .transaction-select:checked').count() == 50  # the largest page, from a 120+ transaction ledger
    assert page.locator('#select-visible').is_checked()
    page.locator('#select-visible-header').click(position={'x':3,'y':3})
    selected([])
    box(txns[0]).check(); box(txns[2]).check(); selected([txns[0],txns[2]])
    assert page.url == editing_url
    assert page.evaluate('window.selectionScans') == 0
    software=cats['EXP.WORK.SOFTWARE']
    page.locator('tr.editing .category-input').fill('Soft')
    page.locator('#f-edit-category-results .category-option').filter(has_text=software.name).first.click()
    page.locator('tr.editing input[name=notes]').fill('Browser selected change')
    page.locator('button[form=f-edit].register-submit').click()
    page.get_by_role('button',name='All 2 rows',exact=True).click()
    page.wait_for_url(lambda url: 'edit=' not in str(url))
    assert [c.transactions.get(t.id).notes for t in txns] == ['Browser selected change','','Browser selected change']
    assert [any(l.category_id==software.id for l in c.transactions.get(t.id).lines) for t in txns] == [True,False,True]
    assert [sum(l.quantity for l in c.transactions.get(t.id).lines if l.account_id==account.id) for t in txns] == [-10,-11,-12]
    page.evaluate("sessionStorage.setItem('lightning-selection:/transactions?', '{broken')")
    page.goto(origin+f'/transactions?edit={txns[1].id}&acct={account.id}')
    selected([])
    page.evaluate("ids=>sessionStorage.setItem('lightning-selection:/transactions?', JSON.stringify(ids))", ['999999999',str(txns[1].id)])
    page.reload()
    selected([txns[1]])
    box(txns[1]).uncheck()
    selected([])


@pytest.mark.parametrize('locale,width',[('en',1366),('ar',1366),('en',390),('ar',390)])
def test_forecast_bars_share_baseline(c, setup, browser_page, monkeypatch, locale, width):
    monkeypatch.setenv('LIGHTNING_TODAY','2026-10-15')
    page, origin = browser_page
    accounts,cats = setup
    c.settings.set('locale',locale)
    c.transactions.record_inflow('2026-10-01',accounts['cib'].id,'100',cats['EXP.WORK.SALARY'].id)
    c.transactions.record_outflow('2026-10-02',accounts['cib'].id,'10',cats['EXP.PERSONAL.FOOD'].id)
    c.planning.create(kind='INCOME',name='Next salary',amount='200',frequency='MONTHLY',start_date='2026-11-01')
    c.planning.create(kind='BILL',name='Bill',amount='50',frequency='MONTHLY',start_date='2026-10-20')
    page.set_viewport_size({'width':width,'height':1000})
    page.goto(origin+'/plan')
    bars = page.locator('.flow-bars').evaluate_all("""xs=>xs.map(x=>({display:getComputedStyle(x).display, bars:[...x.querySelectorAll('.flow-bar-col')].map(y=>{const i=y.querySelector('i'),r=i.getBoundingClientRect();return {bottom:r.bottom,height:r.height,percent:parseFloat(i.style.height),label:y.querySelector('small').textContent}})}))""")
    assert bars
    assert any(b['bars'][0]['height']==0 for b in bars)
    for pair in bars:
        assert pair['display']=='flex'
        left,right = pair['bars']
        assert abs(left['bottom']-right['bottom']) <= 1
        for bar in pair['bars']:
            assert bar['label'].strip()
            assert abs(bar['height']-180*bar['percent']/100) <= 1
    if locale=='en' and width==1366:
        page.screenshot(path='/tmp/feedback-forecast.png',full_page=True)
    page.goto(origin+'/?period=month&month=2026-10')
    page.locator('details[aria-labelledby="position-heading"] > summary').click()
    assert page.locator('.net-flow-bars').evaluate('(x)=>getComputedStyle(x).display')=='grid'
    assert page.locator('.net-flow-bars .flow-bar').first.evaluate('(x)=>x.getBoundingClientRect().height')==12


def test_reserve_multiple_pickers_and_autosave(c, browser_page):
    page,origin = browser_page
    account=c.account_flows.open_account('Daily','BANK','2026-09-01','1000')
    food=c.categories.get_by_code('EXP.PERSONAL.FOOD')
    c.transactions.record_outflow('2026-09-03',account.id,'10',food.id,counterparty='Grocer')
    party=c.counterparties.list_active()[0]
    reserve=c.reserves.create('Criteria browser','100',account_id=account.id)
    page.goto(origin+'/plan/reserves')
    details=page.locator('.reserve-edit').filter(has=page.locator(f'form[action="/reserves/{reserve["id"]}/edit"]'))
    details.locator('summary').click()
    form=details.locator('form')
    posts=[]
    page.on('request',lambda req: posts.append(req.post_data) if req.method=='POST' and req.url.endswith('/edit') else None)
    criterion=lambda value: form.locator(f'input[name=match_by][value={value}]')
    criterion('category').check()
    assert form.locator('[data-match-picker=category]').is_visible()
    assert form.locator('[data-match-picker=category] input[role=combobox]').is_enabled()
    # A tick alone is incomplete; blur must not broaden or save the existing rule.
    form.locator('input[name=name]').focus()
    page.wait_for_timeout(150)
    assert posts == []
    def pick(kind,text):
        picker=form.locator(f'[data-match-picker={kind}]')
        picker.locator('input[role=combobox]').fill(text)
        picker.get_by_role('option',name=text,exact=True).click()
        page.wait_for_function("() => document.querySelector('.reserve-edit[open] .inline-save-status').textContent === 'Saved'")
    pick('category',food.name)
    assert c.reserves.get(reserve['id'])['category_id']==food.id
    criterion('counterparty').check()
    pick('counterparty',party['name'])
    assert c.reserves.get(reserve['id'])['counterparty_id']==party['id']
    for kind in ('account','category','counterparty'):
        pair=form.locator(f'.reserve-criterion:has(input[value={kind}])')
        assert pair.locator('[data-match-picker]').is_visible()
        assert pair.locator('[role=combobox]').count()==1
    page.screenshot(path='/tmp/feedback-reserves.png',full_page=True)
    page.reload()
    page.locator('.reserve-edit summary').first.click()
    form=page.locator(f'form[action="/reserves/{reserve["id"]}/edit"]')
    assert all(criterion(k).is_checked() for k in ('account','category','counterparty'))
    for locale in ('en','ar'):
        c.settings.set('locale',locale)
        page.reload()
        page.locator('.reserve-edit summary').first.click()
        form=page.locator(f'form[action="/reserves/{reserve["id"]}/edit"]')
        for width in (320,390):
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert all(form.locator(f'.reserve-criterion:has(input[value={kind}]) [data-match-picker]').is_visible() for kind in ('account','category','counterparty'))
    c.settings.set('locale','en')
    page.reload()
    page.locator('.reserve-edit summary').first.click()
    form=page.locator(f'form[action="/reserves/{reserve["id"]}/edit"]')
    criterion('category').uncheck()
    page.wait_for_function("() => document.querySelector('.reserve-edit[open] .inline-save-status').textContent === 'Saved'")
    assert c.reserves.get(reserve['id'])['category_id'] is None
    criterion('none').check()
    page.wait_for_function("() => document.querySelector('.reserve-edit[open] .inline-save-status').textContent === 'Saved'")
    assert all(c.reserves.get(reserve['id'])[k+'_id'] is None for k in ('account','category','counterparty'))


@pytest.mark.parametrize('spend', ['60', '125'])
def test_savings_picture_browser(c,browser_page,spend):
    page,origin=browser_page
    account=c.account_flows.open_account('Daily','BANK','2026-09-01','1000')
    c.transactions.record_inflow('2026-09-02',account.id,'100',c.categories.get_by_code('EXP.WORK.SALARY').id)
    c.transactions.record_outflow('2026-09-03',account.id,spend,c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    page.goto(origin+'/?period=month&month=2026-09')
    page.locator('details[aria-labelledby="position-heading"] > summary').click()
    page.locator('#savings-squares > summary').click()
    assert page.locator('.inv-waffle i').count()==100
    assert page.locator('.inv-waffle i.invested').count()==0
    page.screenshot(path='/tmp/feedback-savings-'+('overspent' if spend=='125' else 'saved')+'.png',full_page=True)
