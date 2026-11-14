// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  await p.go('/payday'); console.log('PAYDAY0: ' + await p.text());
  await p.click('button:has-text("Turn on cash funding")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500);
  await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
  console.log('PAYDAY1: ' + p.url() + ' :: ' + await p.text()); await p.shot('payday-on');
  console.log('forms: ' + await p.evaluate(() => [...document.querySelectorAll('main form')].map(f => f.getAttribute('action') + '[' + [...f.querySelectorAll('input:not([type=hidden]),select,button')].map(e => (e.name ? e.name + '=' + e.value : e.innerText.trim())).join(',') + ']').join(' ; ')));
  const btn = await p.$('main button:has-text("Confirm"), main button:has-text("Apply"), main button:has-text("Fund")');
  if (btn) { console.log('clicking: ' + await btn.innerText()); await btn.click(); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500);
    console.log('PAYDAY2: ' + p.url() + ' :: ' + await p.text()); await p.shot('payday-applied'); }
  await key(p, 'after payday apply');
  await p.go('/plan/reserves'); console.log('RES: ' + (await p.text()).slice(0, 1800));
});
