// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
require('./lib').run(async p => {
  await p.go('/plan/catch-up'); await p.click('main :text-is("It was paid")'); await p.waitForLoadState('networkidle');
  console.log('defaults: ' + await p.evaluate(() => ['date_paid','amount','account_id'].map(n => n + '=' + document.querySelector(`main [name=${n}]`).value).join(' ')));
  await p.click('button:has-text("Record and mark paid")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500);
  console.log('after record: ' + p.url() + ' :: ' + (await p.text()).slice(0, 300));
  await p.go('/plan/catch-up'); console.log('catch-up now: ' + (await p.text()).slice(0, 200));
  // skip
  await p.click('main :text-is("It was paid")'); await p.waitForLoadState('networkidle');
  await p.click('button:has-text("Skip this one")'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500);
  console.log('after skip: ' + p.url() + ' :: ' + (await p.text()).slice(0, 300));
  await p.go('/plan/catch-up'); await p.click('main :text-is("Not yet")'); await p.waitForLoadState('networkidle');
  console.log('after not yet: ' + p.url() + ' :: ' + (await p.text()).slice(0, 300));
  await p.click('main :text-is("Not yet")').catch(()=>{}); await p.waitForLoadState('networkidle');
  console.log('after not yet 2: ' + p.url() + ' :: ' + (await p.text()).slice(0, 400)); await p.shot('catchup-end');
  // item 9 sheet + stop/delete
  await p.go('/plan/items/9/sheet?back=/plan'); console.log('SHEET9: ' + await p.text());
});
