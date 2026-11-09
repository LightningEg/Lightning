require('./lib').run(async h=>{
 for (const acct of ['6','4']){
 await h.go('/investments/new?kind=holding&asset=17');
 await h.fill({account_id:acct,asset_id:'17',quantity:'1',total_cost:'3000000'});
 await h.submit('button:has-text("Record holding")');await h.log('J4b apartment as existing holding in account '+acct);}
 await h.go('/accounts/8');
 await h.fill({kind:'Flat',purchase_date:'2022-03-01',purchase_price:'1800000'}).catch(e=>console.log('fillerr',e.message.slice(0,200)));
 await h.submit('button:has-text("Save details")');await h.log('J5b save details');
 console.log(await h.text(900));await h.shot('j5-other-account');
 await h.go('/investments');await h.shot('j5-investments');console.log(await h.text(3200));
});
