const L=require('./lib');(async()=>{const h=await L.open('phone');const p=h.p;const step=async(t)=>{await p.waitForTimeout(700);console.log('\n## '+t+'\nURL '+p.url().replace(h.O,''));};try{
 // Manual add: amount, who => does category fill itself?
 await h.go('/');await p.click('.phone-add');await p.waitForTimeout(700);
 await p.fill('[name=amount]','120');
 await p.fill('[name=counterparty]','Voda');await p.waitForTimeout(900);
 console.log('suggestions:',await p.evaluate(()=>[...document.querySelectorAll('[role=listbox] *, datalist option, .suggest *, .own-picker-list *')].filter(e=>e.checkVisibility&&e.checkVisibility()&&e.children.length==0).map(e=>e.innerText||e.value).slice(0,8).join(' | ')));
 await h.shot('ph-add-who');
 await p.fill('[name=counterparty]','Vodafone');await p.keyboard.press('Tab');await p.waitForTimeout(900);
 console.log('category after who=Vodafone:',await p.evaluate(()=>{const f=document.querySelector('[name=amount]').form;const c=f.querySelector('[name=category],[name=category_id]');const on=[...f.querySelectorAll('button[aria-pressed=true],button.is-active,button.is-on,.chip.is-active')].map(b=>b.innerText.trim());return (c?c.name+'='+c.value:'no field')+' pressed='+on.join(',')}));
 await h.shot('ph-add-filled');
 await p.click('button:has-text("Save")');await step('after Save');
 console.log((await h.text(500,'body')).replace(/\n/g,' | '));await h.shot('ph-add-saved');
 // Save with no category
 await h.go('/');await p.click('.phone-add');await p.waitForTimeout(700);
 await p.fill('[name=amount]','75');await p.click('button:has-text("Save")');await step('Save amount only (no who, no category)');
 console.log((await h.text(400,'body')).replace(/\n/g,' | '));await h.shot('ph-add-amount-only');
 }catch(e){console.log('ERR',e.message.slice(0,300))}await h.close();})();
