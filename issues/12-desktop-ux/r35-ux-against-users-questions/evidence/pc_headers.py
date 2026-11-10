"""r30 PC headers: each tab's title, its answer sentence and dates line (the sample app running as for pc_capture.py).

    python issues/12-desktop-ux/r30-ux-against-users-questions/evidence/pc_headers.py OUT    # writes OUT/headers.json
"""
import sys
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
BASE="http://127.0.0.1:8767"
PAGES=["/","/birdview/expenses","/spending/compare","/reports","/budget","/plan","/plan/recurring","/plan/loans","/plan/reserves","/financial-health","/investments","/investments/planner","/investments/prices","/accounts/currencies","/transactions","/import","/accounts","/money-from-others","/zakat","/settings","/rules","/categories","/counterparties","/checks"]
JS="""() => { const vis = e => e.checkVisibility(); const h1 = document.querySelector('main h1, header h1, h1');
 const head = h1.closest('header') || h1.parentElement.parentElement; const r0 = head.getBoundingClientRect();
 const items = [...head.querySelectorAll('a, button, [role=tablist], nav, form, summary')].filter(vis).filter(e => !e.parentElement.closest('a,button,summary'))
   .map(e => { const r = e.getBoundingClientRect(); const lab = (e.getAttribute('aria-label') || e.title || e.innerText || '').trim().replace(/\\s+/g,' ').slice(0,22);
     return {lab, x: Math.round(r.left), y: Math.round(r.top), cls: (e.className||'').toString().slice(0,30)}; }).filter(i => i.lab);
 const ps = [...head.querySelectorAll('p, small, .muted, span')].filter(vis).filter(e => e.children.length === 0 || e.tagName === 'P').map(e => e.innerText.trim().replace(/\\s+/g,' ')).filter(t => t.length > 12).slice(0,3);
 return {h1: h1.innerText.trim().split('\\n')[0], headH: Math.round(r0.height), headCls: head.className, lines: ps, items}; }"""
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg=b.new_page(viewport={"width":1366,"height":768})
    out={}
    for path in PAGES:
        pg.goto(BASE+path); pg.wait_for_timeout(200); m=pg.evaluate(JS); out[path]=m
        ctl=" · ".join(f"{i['lab']}@{i['x']},{i['y']}" for i in m['items'] if i['y']<260)
        print(f"{path:22} H1={m['h1'][:22]!r:26} h={m['headH']:<4} lines={len(m['lines'])} {m['lines'][:1]}\n      {ctl[:330]}")
    OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True); json.dump(out, open(OUT / "headers.json", "w"), indent=1)
    b.close()
