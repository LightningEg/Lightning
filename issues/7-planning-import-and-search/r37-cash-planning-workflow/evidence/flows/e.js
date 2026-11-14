// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  await p.go('/plan/recurring'); await p.click('a:has-text("Track")'); await p.waitForSelector('dialog[open] form, .popup form', {timeout: 8000});
  await p.screenshot({ path: 'shots/track-view.png' });
  console.log('DIALOG TEXT: ' + await p.text('dialog[open]'));
  await p.click('dialog[open] button:has-text("Add")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(800);
  console.log('after add: ' + p.url() + ' :: ' + (await p.text()).slice(0, 300));
  await key(p, 'after tracking gym 900 from 4 Dec');
  await p.go('/plan/recurring'); const t = await p.text(); console.log('RECURRING: ' + t);
});
