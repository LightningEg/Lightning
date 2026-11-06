import re,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
from playwright.sync_api import sync_playwright
out=Path(__file__).resolve().parent;out.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/tmp/chromium')
 for phone in (False,True):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);host=Host(lambda c:profile_app(c,root/'docs',devices=Devices(root/'app',port=0),phone=phone)).start()
   try:
    page=b.new_page(viewport={'width':360 if phone else 1366,'height':800},is_mobile=phone,has_touch=phone)
    page.goto(host.launch_url);page.goto(host.origin+'/profiles/new')
    page.fill('input[name=name]','Theme review')
    for f in ('password','confirm'):page.fill(f'input[name={f}]','A dummy theme password')
    page.fill('input[name=answer]','Dummy')
    if page.locator('select[name=question]').count():page.select_option('select[name=question]',index=1)
    else:page.fill('input[name=question]','Dummy question?')
    page.click('button[type=submit]');key=re.search(r'\d{4}-\d{4}-\d{4}',page.content()).group(0)
    if page.locator('form[action="/profiles/confirm"] input[name=recovery][type=text]').count():page.fill('input[name=recovery]',key)
    page.click('form[action="/profiles/confirm"] button[type=submit]');page.goto(host.origin+'/settings')
    for locale in ('en','ar'):
     page.evaluate("""async locale=>{let token=document.querySelector('meta[name=lightning-session]').content;await fetch('/settings/locale',{method:'POST',body:new URLSearchParams({locale,__session:token})})}""",locale)
     page.reload();assert page.locator('[data-theme-select]').is_visible()
     page.select_option('[data-theme-select]','royal-obsidian-gold')
     expected='السمة اتحفظت.' if locale=='ar' else 'Theme saved.'
     page.wait_for_function('(text)=>document.querySelector("[data-theme-status]").textContent===text',arg=expected)
     page.reload();assert page.locator('html').get_attribute('data-theme')=='royal-obsidian-gold'
     page.select_option('[data-theme-select]','lightning-default')
     page.wait_for_function('(text)=>document.querySelector("[data-theme-status]").textContent===text',arg=expected)
     page.reload();assert page.locator('html').get_attribute('data-theme')=='lightning-default'
     page.select_option('[data-theme-select]','nile');page.wait_for_timeout(300)
     assert page.locator('[data-theme-status]').inner_text();assert page.locator('html').get_attribute('data-theme')=='nile'
     page.reload();assert page.locator('html').get_attribute('data-theme')=='lightning-default'
     assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
     name=('phone' if phone else 'pc')+'-'+locale
     page.screenshot(path=str(out/(name+'-theme-switching.png')),full_page=True)
     results.append({'device':'phone' if phone else 'pc','locale':locale,'saved_and_restored':True,'return_to_default':True,'unowned_preview_not_saved':True,'no_horizontal_overflow':True})
    page.close()
   finally:host.stop()
 b.close()
(out/'theme-switching.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
