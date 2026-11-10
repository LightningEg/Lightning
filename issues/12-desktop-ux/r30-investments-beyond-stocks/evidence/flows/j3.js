require('./lib').run(async h=>{
 // J3 gram gold: a 10 g BTC bar
 await h.go('/investments/assets/new?then=buy');
 await h.fill({name:'BTC 10g bar',class_code:'Gold',karat:'24'});
 await h.submit('button:has-text("Save")');await h.log('J3a create Gold investment');console.log(await h.text(300));
 const u=h.p.url();const aid=(u.match(/asset=(\d+)/)||[])[1];console.log('asset',aid);
 if(aid){for(const acct of ['6','4']){await h.go('/investments/new?kind=buy&asset='+aid);
  await h.fill({account_id:acct,asset_id:aid,quantity:'10',total:'62000',cash_account_id:'1'});
  await h.submit('button:has-text("Record buy")');await h.log('J3b buy 10g bar in account '+acct);}}
 await h.go('/accounts/6');await h.shot('j3-gold-account');console.log(await h.text(1500));
 await h.go('/investments/prices');console.log('PRICES\n'+await h.text(2500));
 // J4 apartment as Other investment
 await h.go('/investments/assets/new?then=holding');
 await h.fill({name:'Apartment New Cairo',class_code:'Other Investments'});
 await h.submit('button:has-text("Save")');await h.log('J4a create Other investment');
 const a2=(h.p.url().match(/asset=(\d+)/)||[])[1];console.log('asset',a2,await h.text(900));
});
