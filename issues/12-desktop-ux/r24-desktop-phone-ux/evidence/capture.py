import os, sys, re, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ['LIGHTNING_PRICES_OFFLINE']='1'
os.environ['LIGHTNING_TODAY']='2026-11-05'
from playwright.sync_api import sync_playwright
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host

OUT=Path(str(Path(__file__).resolve().parent))
PAGES=['/','/budget','/transactions','/accounts','/accounts/1','/birdview/expenses','/spending/compare','/reports','/plan','/plan/recurring','/plan/loans','/plan/reserves','/plan/scenarios','/plan/payday','/investments','/investments/planner','/investments/prices','/accounts/currencies','/financial-health','/review','/needs-you','/money-from-others','/reimbursements','/settings','/rules','/categories','/counterparties','/checks','/accounts/1/import','/search?q=carrefour','/more']
def login(page,host):
    page.goto(host.launch_url); page.goto(host.origin+'/profiles/new')
    page.fill('[name=name]', 'Audit sample')
    for f in ('password','confirm'): page.fill(f'[name={f}]','a dummy audit password')
    page.fill('[name=answer]','Dummy')
    if page.locator('select[name=question]').count(): page.select_option('[name=question]',index=1)
    else: page.fill('[name=question]','Dummy question?')
    page.click("form[action='/profiles/new'] button[type=submit]")
    key=re.search(r'\d{4}-\d{4}-\d{4}',page.content()).group(0)
    if page.locator('input[name=recovery][type=text]').count(): page.fill('[name=recovery]',key)
    page.click("form[action='/profiles/confirm'] button[type=submit]")
    page.goto(host.origin+'/')
    page.evaluate("async()=>{const t=document.querySelector('meta[name=lightning-session]').content; await fetch('/demo',{method:'POST',body:new URLSearchParams({__session:t})})}")
METRICS="""() => { const main=document.querySelector('main')||document.body; const visible=e=>e.checkVisibility({checkVisibilityCSS:true})&&e.getBoundingClientRect().height>0&&!e.closest('details:not([open]) > :not(summary)'); return {height:document.documentElement.scrollHeight,overflow:document.documentElement.scrollWidth-innerWidth,text:main.innerText, headings:[...main.querySelectorAll('h1,h2,h3')].filter(visible).map(e=>({text:e.innerText,y:Math.round(e.getBoundingClientRect().top)})),targets:[...main.querySelectorAll('a,button,summary,input:not([type=hidden]),select')].filter(visible).map(e=>{let r=e.getBoundingClientRect();return {text:(e.innerText||e.getAttribute('aria-label')||e.name||'').trim().slice(0,65),x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})} }"""
def run(phone):
    mode='mobile' if phone else 'desktop'; folder=OUT/mode; folder.mkdir(exist_ok=True)
    results={}
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        host=Host(lambda cfg:profile_app(cfg,root/'docs',devices=Devices(root/'app',port=0),phone=phone)).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/usr/bin/chromium')
                page=browser.new_page(viewport={'width':360 if phone else 1366,'height':800 if phone else 768},is_mobile=phone,has_touch=phone)
                login(page,host)
                for i,path in enumerate(PAGES):
                    if not phone and path=='/more': continue
                    resp=page.goto(host.origin+path);page.evaluate('document.fonts.ready');page.wait_for_timeout(150)
                    name=f'{i:02d}-'+(path.strip('/').replace('/','-').replace('?','-') or 'overview')
                    results[path]={'status':resp.status,'url':page.url.split(host.origin)[-1],**page.evaluate(METRICS)}
                    page.screenshot(path=str(folder/(name+'.png')),full_page=True)
                page.goto(host.origin+'/transactions')
                if phone:
                    page.click('.phone-add');page.wait_for_timeout(500)
                    page.screenshot(path=str(folder/'add.png'))
                    results['add']={'text':page.locator('#app-popup').inner_text()}
                (folder/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
                browser.close()
        finally: host.stop()
    print(mode,'done',len(results),flush=True)
if __name__=='__main__':
    for phone in (False,True):run(phone)
