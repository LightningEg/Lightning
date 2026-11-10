require('./lib').run(async h=>{
 await h.go('/accounts/6/items/new');
 await h.fill({name:'Wedding bracelet',kind:'Bracelet',weight:'20',karat:'22'});
 await h.submit('button:has-text("Create item")');await h.log('J7a 22K item, no reference chosen');
 await h.go('/accounts/6/items/new');
 await h.fill({name:'Wedding bracelet',kind:'Bracelet',weight:'20',karat:'21',reference_asset_id:'8'});
 await h.submit('button:has-text("Create item")');await h.log('J7b 21K item with 21K reference');
 console.log(await h.text(1300));
 // open the trade form of the new item
 const forms=await h.p.evaluate(()=>[...document.querySelectorAll('form[action*="/trade"]')].map(f=>f.getAttribute('action')+' :: '+[...f.querySelectorAll('[name]:not([type=hidden])')].map(e=>e.name+(e.tagName==='SELECT'?'['+[...e.options].map(o=>o.text.trim()).join('|')+']':'')).join(', ')+' :: '+f.innerText.replace(/\n+/g,' | ').slice(0,700)));
 console.log(forms[forms.length-1]);
 await h.p.evaluate(()=>document.querySelectorAll('details').forEach(d=>d.open=true));
 await h.shot('j7-gold-account');
});
