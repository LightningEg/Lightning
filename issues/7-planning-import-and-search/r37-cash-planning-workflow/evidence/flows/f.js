// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { key } = require('./b.js');
require('./lib').run(async p => {
  const post = async (url, action, fields, label) => {
    await p.go(url);
    const f = `main form[action="${action}"]`;
    await p.evaluate(({ f, fields }) => { const form = document.querySelector(f); form.noValidate = true;
      for (const [k, v] of Object.entries(fields)) { const els = form.querySelectorAll(`[name="${k}"]`);
        els.forEach(e => { if (e.type === 'radio') e.checked = (e.value === v); else e.value = v; }); } }, { f, fields });
    await Promise.all([p.waitForLoadState('networkidle'), p.evaluate((f) => document.querySelector(f).submit(), f)]);
    await p.waitForTimeout(300);
    const t = await p.text();
    console.log(`[${label}] -> ${p.url().replace('http://127.0.0.1:8766','')} :: ${t.replace(/^.*?Loans \| /, '').slice(0, 230)}`);
  };
  const N = '/plan/items/new?kind=BILL', A = '/plan/items';
  const base = { name: 'Test', amount: '100', kind: 'BILL', frequency: 'MONTHLY', interval_count: '1', start_date: '2026-12-15' };
  await post(N, A, { ...base, name: '' }, 'blank name');
  await post(N, A, { ...base, amount: '0' }, 'zero');
  await post(N, A, { ...base, amount: '-50' }, 'negative');
  await post(N, A, { ...base, amount: 'abc' }, 'letters');
  await post(N, A, { ...base, interval_count: '0' }, 'every 0');
  await post(N, A, { ...base, start_date: '15/12/2026' }, 'd/m/y date');
  await post(N, A, { ...base, end_date: '2026-12-01' }, 'ends before start');
  await post(N, A, { ...base, name: 'Old bill', start_date: '2026-08-10', past_due: 'due' }, 'past start, not paid');
  await post(N, A, { ...base, name: 'School fees', amount: '30000', frequency: 'ONCE', start_date: '2027-01-15', category_id: '13' }, 'one-off Jan');
  await post(N, A, { ...base, name: 'Freelance', amount: '8000', kind: 'INCOME', start_date: '2026-11-25' }, 'second income 25th');
  await post(N, A, { ...base, name: 'Freelance', amount: '8000', kind: 'INCOME', start_date: '2026-11-25' }, 'duplicate');
  await key(p, 'after items');
  await p.go('/plan'); await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
  const t = await p.text(); console.log('NEXT30: ' + t.slice(t.indexOf('The next 30 days'), t.indexOf('| Free cash | November')));
  console.log('FORECAST: ' + t.slice(t.indexOf('Show the numbers | Month')));
  await p.shot('plan-after-items');
  await p.go('/plan/catch-up'); console.log('CATCHUP: ' + p.url() + ' ' + (await p.text()).slice(0, 900)); await p.shot('catchup');
});
