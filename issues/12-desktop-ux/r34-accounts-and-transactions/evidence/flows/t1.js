const L=require('./lib');
(async()=>{const c=await L.open('pc');const p=c.p;
 for(const u of ['/transactions','/accounts','/accounts/1','/accounts/1/reconcile','/money-from-others','/search?q=vodafone','/transactions/44','/accounts/1/edit','/zakat']){
  const r=await c.go(u);await p.waitForTimeout(400);
  console.log('\n=====',u,r.status(),p.url().replace(c.O,''),'\n'+(await c.text(900)).replace(/\n/g,' | '));
  await c.full('t/pc'+u.replace(/[\/?=]/g,'_'));}
 await c.close();})();
