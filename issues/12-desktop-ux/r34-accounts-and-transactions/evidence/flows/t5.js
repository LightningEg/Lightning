const L=require('./lib');
(async()=>{const c=await L.open('pc');const p=c.p;
try{
 await c.go('/transactions/65');await p.click('main button:has-text("Delete")');await p.waitForTimeout(700);
 console.log('AFTER DELETE CLICK:',await p.evaluate(()=>[...document.querySelectorAll('dialog[open],.modal,.popup,[role=dialog]')].filter(e=>e.checkVisibility()).map(e=>e.innerText.replace(/\n+/g,' | ').slice(0,400)).join(' ## ')||'no dialog'));await c.shot('t/pc_delete_confirm');
 const b=p.locator('dialog[open] button, [role=dialog] button').filter({hasText:/Delete|Void|Confirm/}).first();
 if(await b.count()){await b.click();await p.waitForTimeout(900);console.log('URL',p.url().replace(c.O,'').slice(0,120));console.log('MSG',await p.evaluate(()=>[...document.querySelectorAll('.flash,.toast,[role=alert]')].map(e=>e.innerText.replace(/\n+/g,' / ')).join(' || ')));}
 await c.go('/accounts/2/reconcile?date=2026-11-09&balance=9000');console.log('\nBIG DIFF:',(await c.text(900)).replace(/\n/g,' | ').slice(200));await c.shot('t/pc_adjust_big');
 await c.go('/accounts/1');await p.evaluate(()=>{const d=[...document.querySelectorAll('main details')].find(d=>d.innerText.includes('Deleted transactions'));});
 const del=await p.evaluate(()=>[...document.querySelectorAll('main a')].filter(a=>/Deleted transactions|Review activity/.test(a.innerText)).map(a=>a.innerText.trim()+'->'+a.getAttribute('href')).join(' ; '));console.log('\nLINKS',del);
 const m=del.match(/Deleted transactions->(\S+)/);if(m){await c.go(m[1]);console.log('DELETED PAGE:',(await c.text(500)).replace(/\n/g,' | '));}
 await c.go('/money-from-others');await p.evaluate(()=>document.querySelectorAll('main details').forEach(d=>d.open=true));console.log('\nHELD:',(await c.text(1500)).replace(/\n/g,' | '));await c.full('t/pc_held');
 }catch(e){console.log('ERR',e.message.slice(0,300))}await c.close();})();
