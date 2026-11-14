// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
require('./lib').run(async p => {
  for (const q of ['afford=30000', 'afford=51420', 'afford=51421', 'afford=60000', 'afford=70000', 'afford=30000&afford_date=2026-12-10', 'afford=30000&afford_account=3', 'afford=abc', 'afford=-5', 'afford=0', 'afford=30000&afford_date=2025-01-01', 'afford=1,500.50','afford=٣٠٠٠']) {
    await p.go('/plan?' + q);
    const t = await p.text();
    const i = t.indexOf('Can I afford this?'); const j = t.indexOf('The next 30 days');
    console.log(q + ' => ' + t.slice(i, j).replace(/Any account \| CIB Payroll \| Cash wallet \| Vodafone Cash \| THNDR \| /, ''));
  }
  await p.go('/plan?afford=60000'); await p.shot('afford60');
});
