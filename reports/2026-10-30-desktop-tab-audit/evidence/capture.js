// Capture every PC tab on Mohab's sample year at 1366 x 768 and 1920 x 1080 and print how long and busy each page is.
//   python -m lightning --sample --no-browser &                         (from the repo root; serves 127.0.0.1:8767)
//   NODE_PATH=$(npm root -g) node reports/2026-10-30-desktop-tab-audit/evidence/capture.js <out-folder>
const fs = require('fs'), path = require('path'), { chromium } = require('playwright');
const origin = 'http://127.0.0.1:8767', OUT = process.argv[2]; fs.mkdirSync(OUT, { recursive: true });
const tabs = '/,/birdview/expenses,/spending/compare,/reports,/budget,/plan,/plan/recurring,/plan/loans,/plan/reserves,/financial-health,/investments,/investments/planner,/investments/prices,/accounts/currencies,/transactions,/import,/accounts,/money-from-others,/zakat,/settings,/rules,/categories,/counterparties,/checks';
const PAGES = tabs.split(',').concat(['/accounts/1', '/review', '/needs-you', '/explain']);
const METRICS = () => {
  const H = innerHeight, vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const main = document.querySelector('main') || document.body;
  const tabs = document.querySelector('.section-bar'), topbar = document.querySelector('.topbar');
  const content = [...main.children].find(c => !c.matches('.topbar, .section-bar, .flash, script') && vis(c));
  const targets = [...main.querySelectorAll('a, button, summary, input, select, textarea')].filter(vis);
  const fig = /[−+-]?\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?\s?%/g, txt = main.innerText;
  const side = document.querySelector('aside.side');
  const lastNav = [...document.querySelectorAll('.side-add')].pop();
  return { height: document.documentElement.scrollHeight, screens: +(document.documentElement.scrollHeight / H).toFixed(1),
    topbar_px: topbar ? Math.round(topbar.getBoundingClientRect().height) : 0,
    tabs_px: tabs ? Math.round(tabs.getBoundingClientRect().height) : 0,
    content_top: content ? Math.round(content.getBoundingClientRect().top + scrollY) : null,
    figures: (txt.match(fig) || []).length, words: txt.split(/\s+/).length, targets: targets.length,
    inputs: [...main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]), select, textarea')].filter(vis).length,
    notices: [...main.querySelectorAll('.notice, .needs-rows, .flash')].filter(vis).length,
    details: [...main.querySelectorAll('details')].filter(vis).length,
    cards: [...main.querySelectorAll('section.card, .card')].filter(vis).length,
    nested_cards: [...main.querySelectorAll('.card .card')].filter(vis).length,
    headings: [...main.querySelectorAll('h1, h2, h3')].filter(vis).map(h => h.innerText.trim().slice(0, 60)),
    top_actions: [...document.querySelectorAll('.topbar .actions a, .topbar .actions button, .topbar .actions summary, .topbar .actions select')].filter(vis).map(a => (a.innerText || a.getAttribute('aria-label') || a.title || '').trim().slice(0, 30)),
    side_scroll: side ? [side.scrollHeight, side.clientHeight] : null,
    side_add_bottom: lastNav ? Math.round(lastNav.getBoundingClientRect().bottom) : null,
    fold_text: txt.slice(0, 1000) };
};
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium/chrome-linux/chrome' }).catch(() => chromium.launch());
  const page = await b.newPage({ viewport: { width: 1366, height: 768 } });
  await page.goto(origin + '/');
  const res = {};
  for (const [w, h, tag] of [[1366, 768, ''], [1920, 1080, '-1080']]) {
    await page.setViewportSize({ width: w, height: h });
    for (const p of PAGES) {
      const r = await page.goto(origin + p);
      const name = p.replace(/^\/|\/$/g, '').replace(/[\/?=]/g, '-') || 'overview';
      const m = await page.evaluate(METRICS); m.status = r && r.status(); res[p + tag] = m;
      if (!tag) await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
      await page.screenshot({ path: path.join(OUT, `${name}${tag}-fold.png`) });
    }
  }
  await b.close();
  fs.writeFileSync(path.join(OUT, 'metrics.json'), JSON.stringify(res, null, 1));
  for (const [k, v] of Object.entries(res)) console.log(`${k.padEnd(28)} ${v.status} scr=${String(v.screens).padStart(4)} top=${v.topbar_px} tabs=${v.tabs_px} body@${v.content_top} fig=${v.figures} tgt=${v.targets} inp=${v.inputs} note=${v.notices} det=${v.details} cards=${v.cards} nest=${v.nested_cards} side=${v.side_scroll} add@${v.side_add_bottom}`);
})();
