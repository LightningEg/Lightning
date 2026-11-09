require('./lib').run(async h=>{
 for (const acct of ['6','4']){
 await h.go('/investments/new?kind=holding&asset=17');
 await h.fill({account_id:acct,asset_id:'17',quantity:'1',cost:'3000000'}).catch(e=>console.log('fillerr',e.message.slice(0,150)));
 await h.submit('button:has-text("Record holding")');await h.log('J4b apartment as existing holding in account '+acct);}
 await h.go('/investments/holding/17');console.log(await h.text(700));
 await h.go('/accounts/new');
 await h.fill({account_type:'Other',name:'Flat in Madinaty',opening_balance:'2500000'});
 await h.submit('button:has-text("Add account")');await h.log('J5 Other account');
 console.log(await h.text(2500));await h.shot('j5-other-account');
});
