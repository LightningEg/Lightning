// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
require('./lib').run(async p => {
  const show = async (q, shot) => { await p.go('/plan/scenarios?' + q); await p.evaluate(() => document.querySelectorAll('details').forEach(d => d.open = true));
    const t = await p.text(); console.log('\n' + q + '\n  HEAD: ' + t.slice(0, 200) + '\n  ' + t.slice(t.indexOf('Show the numbers'), t.indexOf('What do you want')) + '\n  ' + t.slice(t.indexOf('What changes'))); if (shot) await p.shot(shot); };
  await show('what=purchase&purchase=60000&purchase_date=2026-11-20&account_id=1', 'scen-buy');
  await show('what=purchase&purchase=90000&purchase_date=2026-11-20&account_id=1');
  await show('what=purchase&purchase=60000&purchase_date=&account_id=1');
  await show('what=purchase&purchase=60000&purchase_date=2026-11-20&account_id=');
  await show('what=purchase&purchase=60000&purchase_date=2027-06-01&account_id=1');
  await show('what=income', 'scen-income');
  await show('what=income&income=1:2026-12-01&delay=20');
  await show('what=bill', 'scen-bill');
  await show('what=bill&bill=2:2026-12-03&bill_amount=15000');
});
