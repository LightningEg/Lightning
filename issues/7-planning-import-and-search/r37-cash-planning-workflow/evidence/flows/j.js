// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
require('./lib').run(async p => {
  const post = async (url, action, fields, label, btn) => {
    await p.go(url);
    const f = `main form[action="${action}"]`;
    await p.evaluate(({ f, fields }) => { const form = document.querySelector(f); form.noValidate = true;
      for (const [k, v] of Object.entries(fields)) form.querySelectorAll(`[name="${k}"]`).forEach(e => { if (e.type === 'radio') e.checked = (e.value === v); else e.value = v; }); }, { f, fields });
    await Promise.all([p.waitForLoadState('networkidle'), p.evaluate((f) => document.querySelector(f).submit(), f)]);
    await p.waitForTimeout(300);
    console.log(`[${label}] -> ${p.url().replace('http://127.0.0.1:8766','')} :: ${(await p.text()).replace(/^.*?Loans \| /, '').slice(0, 600)}`);
  };
  const P = '/plan/purchases/new';
  await post(P, P, { name: 'Laptop', price: '36000', months: '12', first_date: '2026-12-10', account_id: '1', fee: '1200' }, 'instalment preview');
  await p.shot('purchase-preview');
  console.log('preview buttons: ' + await p.evaluate(() => [...document.querySelectorAll('main form button')].map(b => b.innerText.trim() + '/' + (b.name||'') + '=' + (b.value||'')).join(' ; ')));
  const save = await p.$('main button:has-text("Add"), main button:has-text("Save"), main button:has-text("Confirm")');
  if (save) { await save.click(); await p.waitForLoadState('networkidle'); await p.waitForTimeout(500); console.log('saved -> ' + p.url() + ' :: ' + (await p.text()).slice(0, 1200)); }
  await post(P, P, { name: 'X', price: '0', months: '12', first_date: '2026-12-10' }, 'price 0');
  await post(P, P, { name: 'X', price: '1000', months: '0', first_date: '2026-12-10' }, 'months 0');
  await post(P, P, { name: 'X', price: '1000', months: '3', first_date: '2026-12-10', fee: '5000' }, 'fee > price');
  await post('/plan/items/new?kind=LOAN', '/plan/items', { name: 'Bank loan', amount: '3000', kind: 'LOAN', frequency: 'MONTHLY', interval_count: '1', start_date: '2026-12-20', payment_count: '36', account_id: '1', principal: '80000' }, 'bank loan 36x3000 borrowed 80000');
  await p.go('/plan/loans'); console.log('LOANS: ' + await p.text()); await p.shot('loans-after');
  await p.go('/'); console.log('HOME NW: ' + await p.grab(/Net worth.*?What you owe \| [^|]*/));
});
