// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const key = async (p, label) => {
  await p.go('/plan'); const t = await p.text();
  const w = t.slice(t.indexOf('From free cash to safe to spend'), t.indexOf('Can I afford this?'));
  const k = t.slice(t.indexOf('| Free cash | November'), t.indexOf('Where is my cash heading?'));
  console.log(`[${label}] ` + w + '\n     ' + k);
  await p.go('/'); console.log('     HOME: ' + await p.grab(/Safe to spend \|.*?Next 7 days \| [^|]*/));
  await p.go('/plan/upcoming'); console.log('     UPC: ' + (await p.text()).slice(0, 260));
  await p.go('/budget'); console.log('     BUDGET: ' + (await p.text()).slice(0, 330));
};
exports.key = key;
if (require.main === module) require('./lib').run(async p => {
  await key(p, 'before');
  await p.go('/plan/items/4/pay?due=2026-11-20&back=/plan');
  await p.click('button:has-text("Record and mark paid")'); await p.waitForLoadState('networkidle');
  console.log('after pay url: ' + p.url());
  await key(p, 'after paying WE 650');
  // double submit: go to the same pay URL again
  await p.go('/plan/items/4/pay?due=2026-11-20&back=/plan'); console.log('REVISIT PAY: ' + (await p.text()).slice(0, 400));
  await p.go('/plan/items/4/sheet?back=/plan'); console.log('SHEET: ' + await p.text());
});
