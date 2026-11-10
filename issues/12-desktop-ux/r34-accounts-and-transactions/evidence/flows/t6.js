const L=require('./lib');
(async()=>{const h=await L.open('phone');const p=h.p;
try{
 for(const u of ['/transactions','/money','/money/accounts','/accounts/1','/transactions/44/sheet?return_to=/transactions','/money-from-others','/accounts/1/reconcile','/search?q=vodafone']){
  const r=await h.go(u);await p.waitForTimeout(400);console.log('\n=====',u,r.status(),p.url().replace(h.O,'').slice(0,60),'\n'+(await h.text(650,'main')).replace(/\n/g,' | '));await h.full('t/ph'+u.replace(/[\/?=&]/g,'_').slice(0,40));}
 // Move
 await h.go('/');await p.click('.phone-add');await p.waitForTimeout(600);await p.locator('label:has-text("Move"), [value=transfer]').first().click({force:true});await p.waitForTimeout(600);await h.shot('t/ph_move');
 console.log('\nMOVE SHEET:',await p.evaluate(()=>{const f=document.querySelector('[name=amount]').form;return [...f.querySelectorAll('label,button,select')].filter(e=>e.checkVisibility()).map(e=>e.tagName==='SELECT'?'SELECT '+e.name+'['+[...e.options].map(o=>o.text.trim()).join('|')+']':e.innerText.trim().replace(/\n/g,' ')).join(' ; ').slice(0,700)}));
 }catch(e){console.log('ERR',e.message.slice(0,300))}await h.close();})();
