const L=require('./lib');(async()=>{const c=await L.open('pc');const p=c.p;const T=async(t,n=900,sel)=>{await p.waitForTimeout(600);console.log('\n## '+t+' | URL '+p.url().replace(c.O,'')+'\n'+(await c.text(n,sel)).replace(/\n/g,' | '));};try{
 await c.go('/budget/category/5/edit?month=2026-11');await T('Change limit page (Food)',1200);await c.shot('b/pc_change_limit');
 console.log(await c.controls('main').then(s=>s.split('\n').filter(l=>!/^A (Budget|Transactions)/.test(l)).slice(0,25).join('\n')));
 await c.go('/budget/category/5/sheet?month=2026-11');await T('Category sheet (Food)',900);await c.shot('b/pc_category_sheet');
 await c.go('/budget/fill?month=2026-11');console.log('FILL options',await p.evaluate(()=>[...document.querySelectorAll('main select option')].map(o=>o.text.trim()).join(' | ')));
 await c.go('/plan');await p.fill('main input[name=amount], main input[placeholder=Price]','30000').catch(e=>console.log('fill err'));await p.click('main button:has-text("Check")');await T('Can I afford 30,000',700);await c.shot('b/pc_afford');
 await c.go('/plan');await p.fill('main input[placeholder=Price]','80000');await p.click('main button:has-text("Check")');await T('Can I afford 80,000',500);
 }catch(e){console.log('ERR',e.message.slice(0,300))}await c.close();})();
