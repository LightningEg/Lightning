"""r28 polish probe: visits the main PC and phone pages in English and Arabic on a dummy profile with the sample
household and records the small things that make an app feel finished (titles, numbers, dates, type, focus, targets,
leaked internal words, console errors, design-token spread). Needs Playwright, Chromium and the app's dependencies.

    python issues/3-polish-and-arabic/r28-international-polish/evidence/probe.py   # writes probe.json and shots/ here
"""
from __future__ import annotations

import json, os, re, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.environ["LIGHTNING_PRICES_OFFLINE"] = "1"
os.environ["LIGHTNING_TODAY"] = "2026-11-08"
OUT = Path(__file__).resolve().parent

PC = ["/", "/budget", "/transactions", "/accounts", "/accounts/1", "/plan", "/plan/scenarios", "/payday", "/investments",
      "/financial-health", "/reports", "/review", "/settings", "/categories", "/accounts/1/transaction/new", "/search?q=food",
      "/does-not-exist"]
PHONE = ["/home", "/budget", "/activity", "/money", "/money/bills", "/money/report", "/accounts/add-transaction",
         "/settings", "/search?q=food", "/does-not-exist"]
SHOTS = {("pc", "en", "/"), ("pc", "ar", "/"), ("pc", "en", "/transactions"), ("pc", "en", "/plan/scenarios"),
         ("pc", "en", "/does-not-exist"), ("pc", "en", "/accounts/1/transaction/new"), ("phone", "en", "/home"),
         ("phone", "ar", "/home"), ("phone", "en", "/accounts/add-transaction"), ("phone", "ar", "/activity"),
         ("phone", "en", "/does-not-exist")}

PROBE = r"""() => {
  const main = document.querySelector('main') || document.body;
  const vis = e => e.checkVisibility && e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) && e.getBoundingClientRect().height > 0;
  const text = main.innerText;
  const all = [...document.querySelectorAll('body *')].filter(vis);
  const leaves = all.filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()));
  const cs = e => getComputedStyle(e);
  const money = /[-−]?\d{1,3}(?:[,٬]\d{3})+(?:\.\d+)?/;
  const figures = leaves.filter(e => money.test(e.textContent) && e.textContent.trim().length < 40);
  const count = (arr, f) => { const m = {}; for (const e of arr) { const k = f(e); m[k] = (m[k] || 0) + 1; } return m; };
  const targets = [...document.querySelectorAll('a[href], button, summary, input:not([type=hidden]), select, [role=button]')].filter(vis);
  const small = targets.filter(e => { const r = e.getBoundingClientRect(); return r.height < 24 || r.width < 24; })
                       .map(e => (e.innerText || e.getAttribute('aria-label') || e.name || e.tagName).trim().slice(0, 30));
  const unnamed = targets.filter(e => !(e.innerText || '').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title')
      && !e.querySelector('img[alt]:not([alt=""])') && !(e.labels && e.labels.length) && !e.getAttribute('placeholder')
      && !e.getAttribute('aria-labelledby')).map(e => e.outerHTML.slice(0, 90));
  const clipped = leaves.filter(e => e.scrollWidth > e.clientWidth + 1 && ['hidden', 'clip'].includes(cs(e).overflowX)
      && cs(e).textOverflow !== 'ellipsis').map(e => e.textContent.trim().slice(0, 40));
  const ellipsisNoTitle = leaves.filter(e => cs(e).textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1 && !e.title).length;
  const upper = leaves.filter(e => cs(e).textTransform === 'uppercase').map(e => e.textContent.trim().slice(0, 30));
  const pick = (re) => [...new Set((text.match(re) || []).map(s => s.trim()))].slice(0, 8);
  return {
    title: document.title, lang: document.documentElement.lang, dir: document.documentElement.dir || cs(document.documentElement).direction,
    themeColor: !!document.querySelector('meta[name=theme-color]'), colorScheme: cs(document.documentElement).colorScheme,
    h1: [...main.querySelectorAll('h1')].filter(vis).map(e => e.innerText.trim()),
    bodyFont: cs(document.body).fontFamily, h1Font: (() => { const h = main.querySelector('h1'); return h ? cs(h).fontFamily + ' ' + cs(h).fontWeight : ''; })(),
    figures: figures.length,
    figuresTabular: figures.filter(e => cs(e).fontVariantNumeric.includes('tabular')).length,
    hyphenMinus: pick(/(?:^|[\s(])-\d[\d,.]*/gm), trueMinus: (text.match(/−\d/g) || []).length,
    decimalsOnBig: pick(/\b\d{1,3}(?:,\d{3})+\.\d{2}\b/g),
    leaked: pick(/\b(?:None|null|undefined|NaN|nan|True|False|OUT-\d{4}-\d\d-\d\d-\d+|IN-\d{4}-\d\d-\d\d-\d+|[a-z]+_[a-z_]+)\b/g),
    straightQuotes: pick(/\w'\w|"[^"\n]{1,30}"/g), threeDots: (text.match(/\.\.\./g) || []).length,
    oneThings: pick(/(?:^|\s)1 [A-Za-z]+s\b/gm),
    dates: pick(/\b(?:\d{4}-\d\d-\d\d|\d{1,2}\/\d{1,2}\/\d{2,4}|\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?: \d{4})?|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:, \d{4})?)\b/g),
    latinInArabic: document.documentElement.lang.startsWith('ar') ? pick(/\b[A-Za-z][A-Za-z ]{3,}[A-Za-z]\b/g) : [],
    upper, small: small.slice(0, 10), smallCount: small.length, targets: targets.length, unnamed: unnamed.slice(0, 5),
    clipped: clipped.slice(0, 6), ellipsisNoTitle,
    fontSizes: Object.keys(count(leaves, e => cs(e).fontSize)).length, fontWeights: Object.keys(count(leaves, e => cs(e).fontWeight)).sort(),
    radii: Object.keys(count(all, e => cs(e).borderRadius)).filter(r => r !== '0px').length,
    shadows: Object.keys(count(all, e => cs(e).boxShadow)).filter(s => s !== 'none').length,
    inlineStyles: document.querySelectorAll('main [style]').length,
    imgsNoAlt: [...document.querySelectorAll('img:not([alt])')].length,
    overflow: document.documentElement.scrollWidth - innerWidth,
    height: document.documentElement.scrollHeight,
    nativeDialogs: (document.documentElement.outerHTML.match(/\b(?:confirm|alert)\(/g) || []).length,
  };
}"""

FOCUS = r"""() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e);
  return {tag: e.tagName.toLowerCase(), text: (e.innerText || e.name || e.getAttribute('aria-label') || '').trim().slice(0, 30),
    outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0, ring: s.boxShadow !== 'none'}; }"""


def login(page, host, locale):
    page.goto(host.launch_url); page.goto(host.origin + "/profiles/new")
    page.fill("input[name=name]", "Polish probe")
    for f in ("password", "confirm"):
        page.fill(f"input[name={f}]", "a dummy audit password")
    page.fill("input[name=answer]", "Dummy")
    if page.locator("select[name=question]").count():
        page.select_option("select[name=question]", index=1)
    elif page.locator("input[name=question]").count():
        page.fill("input[name=question]", "Dummy question?")
    page.click("form[action='/profiles/new'] button[type=submit]")
    key = re.search(r"\d{4}-\d{4}-\d{4}", page.content()).group(0)
    if page.locator("form[action='/profiles/confirm'] input[name=recovery][type=text]").count():
        page.fill("input[name=recovery]", key)
    page.click("form[action='/profiles/confirm'] button[type=submit]")
    page.goto(host.origin + "/")
    page.evaluate("""async (loc) => { const t = document.querySelector('meta[name=lightning-session]').content;
        await fetch('/demo', {method: 'POST', body: new URLSearchParams({__session: t})});
        if (loc === 'ar') await fetch('/settings/locale', {method: 'POST', body: new URLSearchParams({__session: t, locale: 'ar'})}); }""", locale)


def run(device, locale, results):
    from playwright.sync_api import sync_playwright
    from lightning.runtime.app import profile_app
    from lightning.runtime.devices import Devices
    from lightning.runtime.http import Host
    phone = device == "phone"
    shots = OUT / "shots"; shots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        host = Host(lambda c: profile_app(c, root / "docs", devices=Devices(root / "app", port=0), phone=phone)).start()
        try:
            with sync_playwright() as pw:
                exe = Path("/opt/pw-browsers/chromium")
                browser = pw.chromium.launch(executable_path=str(exe) if exe.exists() else shutil.which("chromium"))
                page = browser.new_page(viewport={"width": 390, "height": 844} if phone else {"width": 1366, "height": 768},
                                        is_mobile=phone, has_touch=phone)
                errors = []
                page.on("console", lambda m: errors.append(m.text[:120]) if m.type == "error" else None)
                page.on("pageerror", lambda e: errors.append(str(e)[:120]))
                login(page, host, locale)
                for path in (PHONE if phone else PC):
                    errors.clear()
                    resp = page.goto(host.origin + path)
                    page.evaluate("document.fonts.ready"); page.wait_for_timeout(120)
                    data = {"status": resp.status if resp else None, **page.evaluate(PROBE)}
                    page.mouse.click(1, 1)
                    rings = []
                    for _ in range(6):
                        page.keyboard.press("Tab"); f = page.evaluate(FOCUS)
                        if f: rings.append(f)
                    data["focus"] = rings
                    data["consoleErrors"] = list(errors)
                    results[f"{device} {locale} {path}"] = data
                    if (device, locale, path) in SHOTS:
                        name = f"{device}-{locale}-" + (path.strip("/").replace("/", "-").replace("?", "-") or "home")
                        page.screenshot(path=str(shots / f"{name}.png"))
                if locale == "en":  # an empty Save: does the app or the browser speak?
                    page.goto(host.origin + ("/accounts/add-transaction" if phone else "/accounts/1/transaction/new"))
                    active = page.evaluate("() => document.activeElement && (document.activeElement.name || document.activeElement.id)")
                    page.keyboard.type("120")
                    amount = page.evaluate("() => (document.querySelector('[name=amount]') || {}).value || ''")
                    results[f"{device} en add-focus"] = {"active": active, "amountAfterTyping120": amount}
                    page.emulate_media(color_scheme="dark"); page.goto(host.origin + ("/home" if phone else "/"))
                    results[f"{device} en dark"] = {"bg": page.evaluate("getComputedStyle(document.body).backgroundColor")}
                    page.screenshot(path=str(shots / f"{device}-en-dark.png"))
                    page.emulate_media(color_scheme="light")
                browser.close()
        finally:
            host.stop()


if __name__ == "__main__":
    results = {}
    for device in ("pc", "phone"):
        for locale in ("en", "ar"):
            run(device, locale, results); print(device, locale, "done", flush=True)
    (OUT / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
