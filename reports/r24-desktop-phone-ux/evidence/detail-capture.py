import tempfile,json
from pathlib import Path
from capture import login,METRICS
from probes import probe
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
from playwright.sync_api import sync_playwright
OUT=Path(str(Path(__file__).resolve().parent / 'details'));OUT.mkdir(exist_ok=True)
for phone in (False,True):
    mode='phone' if phone else 'pc'
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); seeded={}
        def factory(cfg):
            app=profile_app(cfg,root/'docs',devices=Devices(root/'app',port=0),phone=phone)
            async def wrapper(scope,receive,send):
                if scope['type']=='http' and scope['path']=='/__auditseed':
                    seeded.update(probe(app.session.container))
                    await send({'type':'http.response.start','status':200,'headers':[]})
                    await send({'type':'http.response.body','body':b'ok'});return
                await app(scope,receive,send)
            return wrapper
        host=Host(factory).start()
        try:
            with sync_playwright() as pw:
                b=pw.chromium.launch(executable_path='/usr/bin/chromium'); page=b.new_page(viewport={'width':360 if phone else 1366,'height':800 if phone else 768},is_mobile=phone,has_touch=phone)
                login(page,host)
                results={}
                for path,name in [('/payday','payday'),('/plan/inputs','forecast-inputs'),('/plan/purchases/new','instalments')]:
                    page.goto(host.origin+path);page.evaluate('document.fonts.ready')
                    page.screenshot(path=str(OUT/f'{mode}-{name}.png'),full_page=True);results[name]=page.evaluate(METRICS)
                if not phone:
                    page.goto(host.origin+'/transactions');page.locator('.transaction-select:not([disabled])').nth(2).check()
                    page.screenshot(path=str(OUT/'pc-bulk-selection.png'),full_page=True);results['bulk']=page.evaluate(METRICS)
                    page.goto(host.origin+'/');page.set_viewport_size({'width':1920,'height':1080});page.screenshot(path=str(OUT/'pc-overview-1920.png'));page.set_viewport_size({'width':1366,'height':768})
                page.goto(host.origin+'/__auditseed')
                for a in seeded['assets']:
                    page.goto(host.origin+'/accounts/'+str(a['account_id']));page.evaluate('document.fonts.ready')
                    name='asset-'+a['opening'];page.screenshot(path=str(OUT/f'{mode}-{name}.png'),full_page=True);results[name]=page.evaluate(METRICS)
                page.goto(host.origin+'/plan/reserves')
                page.locator('.refill-prompt button').click();page.wait_for_load_state('networkidle')
                page.goto(host.origin+'/plan');page.screenshot(path=str(OUT/f'{mode}-after-refill.png'),full_page=True);results['after-refill']=page.evaluate(METRICS)
                (OUT/f'{mode}.json').write_text(json.dumps(results,indent=2));b.close()
        finally:host.stop()
    print(mode,'done',flush=True)
