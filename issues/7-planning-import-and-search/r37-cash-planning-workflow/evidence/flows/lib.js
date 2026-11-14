// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { chromium } = require('playwright');
exports.run = async (fn) => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
  const p = await ctx.newPage();
  p.on('pageerror', e => console.log('PAGEERR ' + e.message));
  p.on('response', r => { if (r.status() >= 400) console.log('HTTP ' + r.status() + ' ' + r.url()); });
  p.go = async (u) => { await p.goto('http://127.0.0.1:8766' + u, { waitUntil: 'networkidle' }); };
  p.text = async (sel = 'main') => (await p.evaluate((s) => (document.querySelector(s) || document.body).innerText, sel)).split('\n').map(s => s.trim()).filter(Boolean).join(' | ');
  p.grab = async (re) => { const t = await p.text(); const m = t.match(re); return m ? m[0] : '(no match)'; };
  p.shot = async (n) => p.screenshot({ path: `shots/${n}.png`, fullPage: true });
  try { await fn(p); } catch (e) { console.log('SCRIPT ERR ' + e.message.split('\n')[0]); await p.shot('error'); }
  await b.close();
};
