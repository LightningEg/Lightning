// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  await p.go('/plan/reserves'); await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true)); await p.waitForTimeout(300);
  await p.shot('reserves-open'); const t0 = await p.text(); console.log('OPEN: ' + t0.slice(t0.indexOf('Could also use')));
  // add a reserve
  await p.evaluate(() => { const f = document.querySelector('main form[action="/reserves"][method="post"]'); f.noValidate = true;
    f.querySelector('[name=name]').value = 'Summer trip'; f.querySelector('[name=target]').value = '24000'; f.querySelector('[name=due_date]').value = '2027-07-01'; f.submit(); });
  await p.waitForLoadState('networkidle'); await p.waitForTimeout(400);
  await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
  const t = await p.text(); console.log('AFTER ADD: ' + p.url() + ' :: ' + t.slice(t.indexOf('What are you saving for?')).slice(0, 1500));
  await p.shot('reserves-goal');
  console.log('forms: ' + await p.evaluate(() => [...document.querySelectorAll('main form')].map(f => f.getAttribute('action') + '[' + [...f.querySelectorAll('input:not([type=hidden]),select,button')].map(e => (e.name || e.innerText.trim())).join(',') + ']').join(' ; ')));
  await key(p, 'after adding goal 24,000 by 1 Jul 2027');
});
