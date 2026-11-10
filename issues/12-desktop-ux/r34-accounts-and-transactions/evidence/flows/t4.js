const L=require('./lib');
(async()=>{const c=await L.open('pc');const p=c.p;
const msg=async(t)=>{await p.waitForTimeout(800);console.log('\n## '+t+' | '+p.url().replace(c.O,'').slice(0,100)+'\n   MSG: '+await p.evaluate(()=>[...document.querySelectorAll('.flash,.toast,[role=alert],.has-error,.error')].map(e=>e.innerText.trim().replace(/\n+/g,' / ').slice(0,220)).filter(Boolean).join(' || ')));};
const top=async(n=2)=>console.log('   ROWS: '+await p.evaluate((n)=>[...document.querySelectorAll('main tbody tr')].filter(r=>r.querySelector('input[type=checkbox]')).slice(0,n).map(r=>r.innerText.replace(/\s+/g,' ').trim().slice(0,100)).join('  ¦  '),n));
try{
 // delete from detail page, then undo
 await c.go('/accounts/1');const href=await p.evaluate(()=>[...document.querySelectorAll('main tbody a')].map(a=>a.getAttribute('href')).find(h=>/edit=\d+/.test(h)));console.log('first edit link',href);
 const id=href.match(/edit=(\d+)/)[1];
 await c.go('/transactions/'+id);console.log('DETAIL',(await c.text(500)).replace(/\n/g,' | '));
 p.once('dialog',d=>{console.log('   DIALOG:',d.message());d.accept()});
 await p.click('main button:has-text("Delete")');await msg('delete '+id);console.log('   after:',(await c.text(300)).replace(/\n/g,' | '));
 await p.click('button:has-text("Undo")').catch(()=>console.log('   no Undo button'));await msg('undo delete');
 // adjust balance
 await c.go('/accounts/2/reconcile');console.log('RECONCILE',(await c.text(500)).replace(/\n/g,' | '));console.log(await c.controls('main'));
 await p.fill('main input[name=balance], main input[name=actual], main input[name=ending_balance], main input[inputmode=decimal]','10900').catch(e=>console.log('fill err',e.message.slice(0,80)));
 await p.click('main button:has-text("Adjust balance")');await msg('adjust Cash wallet to 10,900');console.log('   after:',(await c.text(600)).replace(/\n/g,' | '));await c.shot('t/pc_adjust_result');
 // bulk
 await c.go('/accounts/1');await p.locator('main tbody tr input[type=checkbox]').nth(1).check({force:true});await p.locator('main tbody tr input[type=checkbox]').nth(2).check({force:true});await p.waitForTimeout(500);
 console.log('BULK BAR:',await p.evaluate(()=>[...document.querySelectorAll('.bulk-bar,[class*=bulk],[class*=selection]')].filter(e=>e.checkVisibility()).map(e=>e.innerText.replace(/\n+/g,' | ').slice(0,400)).join(' ## ')));await c.shot('t/pc_bulk');
 // register search
 await c.go('/accounts/1?q=carrefour');await top(3);
 await c.go('/transactions?q=3250');await top(2);
 await c.go('/transactions?q=3,250.75');await top(2);
 await c.go('/transactions?q=groceries');await top(2);
 }catch(e){console.log('ERR',e.message.slice(0,300))}await c.close();})();
