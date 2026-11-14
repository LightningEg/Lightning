// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { chromium } = require('playwright');
const fs = require('fs');
const pages = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  p.on('response', r => { if (r.status() >= 400) errs.push(r.status() + ' ' + r.url()); });
  for (const spec of pages) {
    const [name, url] = spec.split('=', 2).length === 2 ? [spec.slice(0, spec.indexOf('=')), spec.slice(spec.indexOf('=') + 1)] : [spec, spec];
    await p.goto('http://127.0.0.1:8766' + url, { waitUntil: 'networkidle' });
    await p.screenshot({ path: `shots/${name}.png`, fullPage: true });
    const main = await p.evaluate(() => (document.querySelector('main') || document.body).innerText);
    fs.writeFileSync(`shots/${name}.txt`, p.url() + '\n' + main);
  }
  console.log(errs.join('\n') || 'no errors');
  await b.close();
})();
