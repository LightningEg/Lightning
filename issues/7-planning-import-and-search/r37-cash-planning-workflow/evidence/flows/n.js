// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  // links inside the worked-out card
  await p.go('/plan');
  console.log('WORKED-OUT LINKS: ' + await p.evaluate(() => { const h = [...document.querySelectorAll('main *')].find(e => e.children.length === 0 && e.textContent.trim() === 'How safe to spend is worked out'); const card = h.closest('section, .card, article, div[class]').parentElement; return [...card.querySelectorAll('a')].map(a => a.getAttribute('href') + '«' + a.innerText.trim() + '»').join(' ; ') || 'none'; }));
  // upcoming next month + a day with several
  await p.go('/plan/upcoming'); console.log('UPC links: ' + await p.evaluate(() => [...document.querySelectorAll('main a[href]')].map(a => a.getAttribute('href')).filter(h => !h.startsWith('/plan/upcoming?day')).join(' ; ').slice(0, 900)));
  await p.go('/plan/upcoming?month=2026-12'); console.log('UPC DEC: ' + (await p.text()).replace(/\| Sat \|.*?\| To pay \| Late/, '| [calendar] ').slice(0, 900)); await p.shot('upcoming-dec');
  await p.go('/plan/upcoming?month=2027-07'); console.log('UPC JUL27: ' + (await p.text()).slice(0, 330));
  // early payment preview
  await p.go('/plan/items/6/early-payment'); await p.fill('main [name=principal]', '10000'); await p.click('main button:has-text("Preview")'); await p.waitForLoadState('networkidle');
  console.log('EARLY PREVIEW: ' + await p.text()); await p.shot('early-preview');
  // salary arrives early: mark ACME received today
  await p.go('/plan/items/1/pay?due=2026-12-01&back=/plan'); console.log('RECEIVE FORM: ' + await p.text());
  await p.click('main button:has-text("Record")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(400);
  await key(p, 'salary of 1 Dec recorded as received today (14 Nov)');
  await p.go('/plan'); await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true)); const t = await p.text();
  console.log('HEAD: ' + t.slice(0, 160)); console.log('FORECAST: ' + t.slice(t.indexOf('Show the numbers | Month'), t.indexOf('What is promised?')));
  await p.go('/payday'); console.log('PAYDAY: ' + (await p.text()).slice(0, 600));
});
