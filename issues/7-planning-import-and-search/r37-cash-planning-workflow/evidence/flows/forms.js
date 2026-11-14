// r37 evidence. Run from the repo root with the demo running: python -m lightning --demo --no-browser (port 8766), then node issues/7-planning-import-and-search/r37-cash-planning-workflow/evidence/flows/<file>.js. Each run changes the demo data; restart the demo for a clean state. Screenshots go to ./shots (create it).
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1366, height: 768 } });
  for (const url of process.argv.slice(2)) {
    await p.goto('http://127.0.0.1:8766' + url, { waitUntil: 'networkidle' });
    const out = await p.evaluate(() => [...document.querySelectorAll('main form, dialog form')].map(f =>
      `FORM ${f.method} ${f.getAttribute('action')} ${f.id||''}\n` + [...f.querySelectorAll('input,select,textarea,button')].filter(e=>e.name!=='csrf_token').map(e =>
        `   ${e.tagName.toLowerCase()} name=${e.name} type=${e.type} value=${(e.value||'').slice(0,30)} ${e.required?'required':''} ${e.tagName==='BUTTON'?'"'+e.innerText.trim()+'"':''} ${e.tagName==='SELECT'?'['+[...e.options].map(o=>o.value+':'+o.text).join('|').slice(0,160)+']':''}`).join('\n')).join('\n'));
    const links = await p.evaluate(() => [...new Set([...document.querySelectorAll('main a[href]')].map(a => a.getAttribute('href') + ' «' + a.innerText.trim().replace(/\s+/g,' ').slice(0,40) + '»'))].join('\n'));
    console.log('######## ' + url + '\n' + out + '\n-- links\n' + links);
  }
  await b.close();
})();
