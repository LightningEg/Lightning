const L=require('./lib');(async()=>{const h=await L.open('pc');const p=h.p;const step=async(t,n=1800)=>{await p.waitForTimeout(800);console.log('\n## '+t+'\nURL '+p.url().replace(h.O,'')+'\n'+(await h.text(n)).replace(/\n/g,' | '));};try{
 await h.go('/sms');await p.click('button:has-text("Review 3 messages")');await step('click Review 3 messages');
 console.log(await h.controls('main').then(s=>s.split('\n').filter(l=>!/^A (Transactions|Import|Accounts|Held)/.test(l)).slice(0,30).join('\n')));await h.full('pc-sms-assign');
 }catch(e){console.log('ERR',e.message.slice(0,300))}await h.close();})();
