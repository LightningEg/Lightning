// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  const res = async (l) => { await p.go('/plan/reserves'); const t = await p.text(); console.log(`RES[${l}]: ` + t.slice(0, 1500)); };
  await p.go('/plan/reserves'); await p.click('button:has-text("Refill 5,404")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500);
  await res('after refill 5,404'); await p.shot('reserves-after-refill');
  await key(p, 'after refill');
  await p.go('/budget'); const b = await p.text(); console.log('BUDGET job: ' + b.slice(b.indexOf('Not yet given a job'), b.indexOf('Not yet given a job') + 400));
});
