"""r30 PC capture: every section tab at 1366 x 768 (first screen and full page) with layout metrics.

Start the sample year first, from the repo root:
    LIGHTNING_TODAY=2026-10-21 LIGHTNING_PRICES_OFFLINE=1 python -m lightning --sample --no-browser --port 8767
then:
    python issues/12-desktop-ux/r30-ux-against-users-questions/evidence/pc_capture.py OUT [en|ar] [/a,/b]
Writes OUT/<page>-fold.png, OUT/<page>-full.png and OUT/metrics.json. Needs Playwright and Chromium. Dummy data only.
"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8767"
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True); LANG = sys.argv[2] if len(sys.argv) > 2 else "en"
PAGES = sys.argv[3].split(",") if len(sys.argv) > 3 else ["/", "/birdview/expenses", "/spending/compare", "/reports", "/budget", "/payday", "/plan", "/plan/recurring", "/plan/loans",
 "/plan/reserves", "/financial-health", "/investments", "/investments/planner", "/investments/prices", "/accounts/currencies",
 "/transactions", "/import", "/accounts", "/accounts/1", "/money-from-others", "/zakat", "/settings", "/rules", "/categories",
 "/counterparties", "/checks", "/search?q=food", "/accounts/add-transaction", "/review", "/activity", "/plan/purchases/new", "/exports/all"]
METRICS = """() => { const q = s => [...document.querySelectorAll(s)].filter(e => e.checkVisibility());
 const main = document.querySelector('main') || document.body;
 const txt = e => (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 90);
 const fold = innerHeight;
 const h = q('main h1, main h2, main h3').map(e => ({t: e.tagName, y: Math.round(e.getBoundingClientRect().top + scrollY), s: txt(e)}));
 const ctl = q('main a.btn, main button, main .btn, main summary').filter(e => e.getBoundingClientRect().top < fold);
 return { title: document.title, h1: txt(q('h1')[0] || document.body).slice(0, 80), status: txt(q('.page-status, .status-sentence, header p')[0] || {innerText: ''}),
  height: document.documentElement.scrollHeight, folds: +(document.documentElement.scrollHeight / fold).toFixed(1),
  cards: q('main .card').length, tables: q('main table').length, selects: q('main select').length, inputsFold: q('main input:not([type=hidden]), main select').filter(e => e.getBoundingClientRect().top < fold).length,
  controlsFold: ctl.length, controls: [...new Set(ctl.map(txt).filter(Boolean))].slice(0, 40), headings: h.slice(0, 40),
  sideways: document.documentElement.scrollWidth - innerWidth,
  words: (main.innerText || '').split(/\\s+/).length }; }"""
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:200]) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("pageerror " + str(e)[:200]))
    pg.goto(BASE + "/")
    if LANG == "ar":
        pg.evaluate("""async () => { const t = document.querySelector('meta[name=lightning-session]'); await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t ? t.content : '', locale: 'ar'})}); }""")
    for path in PAGES:
        errs.clear()
        r = pg.goto(BASE + path); pg.wait_for_timeout(350)
        name = (path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-") or "overview")
        m = pg.evaluate(METRICS); m["status_code"] = r.status if r else None; m["url"] = pg.url.replace(BASE, ""); m["errors"] = list(errs)
        res[path] = m
        pg.screenshot(path=str(OUT / f"{name}-fold.png"))
        pg.screenshot(path=str(OUT / f"{name}-full.png"), full_page=True)
    b.close()
(OUT / "metrics.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
for k, m in res.items():
    print(f"{k:28} {m['status_code']} folds={m['folds']:<4} cards={m['cards']:<3} ctlFold={m['controlsFold']:<3} inFold={m['inputsFold']:<3} sel={m['selects']:<2} words={m['words']:<5} err={len(m['errors'])} | {m['h1'][:50]}")
