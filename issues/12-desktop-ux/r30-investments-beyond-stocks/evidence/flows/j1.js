require('./lib').run(async h=>{
 await h.go('/investments/new?kind=buy');
 await h.fill({account_id:'4',asset_id:'10',quantity:'1',total:'5000'});
 await h.submit('button:has-text("Record buy")');await h.log('J1 buy CD asset inside THNDR broker');console.log(await h.text(500));
 await h.go('/investments/new?kind=buy');
 await h.fill({account_id:'6',asset_id:'9',quantity:'5',total:'30000',cash_account_id:'1'});
 await h.submit('button:has-text("Record buy")');await h.log('J2 buy 5g of 24K reference into Gold at home, paid from CIB');console.log(await h.text(400));
 await h.go('/accounts/6');console.log(await h.text(1800));
});
