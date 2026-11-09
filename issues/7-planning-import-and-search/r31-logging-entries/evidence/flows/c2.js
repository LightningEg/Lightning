const L=require('./lib');(async()=>{const h=await L.open('pc');const p=h.p;const step=async(t,n=1400)=>{await p.waitForTimeout(700);console.log('\n## '+t+'\nURL '+p.url().replace(h.O,'')+'\n'+(await h.text(n)).replace(/\n/g,' | '));};try{
 await h.go('/sms');
 const msgs=["تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 1234 عند CARREFOUR MAADI يوم 06/11/26 الساعه 11:13 المتاح 3792.36EGP",
 "تم خصم 350.00 EGP من بطاقة الخصم المباشر رقم 1234 عند VODAFONE يوم 07/11/26 الساعه 09:02 المتاح 3442.36EGP",
 "تم خصم 89.00 EGP من بطاقة الخصم المباشر رقم 1234 عند UBER *TRIP HELP.UBER.COM يوم 07/11/26 الساعه 23:40 المتاح 3353.36EGP",
 "Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26 at 21:15. Available balance EGP 10,200.50",
 "تم دفع 150 جنيه من محفظتك فودافون كاش الى التاجر Koshary El Tahrir. رصيدك الحالي 3000 جنيه",
 "Your card ending 1234 was charged USD 12.99 at NETFLIX.COM on 03/11/26"];
 await p.fill('[name=messages]',msgs.join('\n\n'));await p.click('button:has-text("Read them")');await step('after Read them');await h.full('pc-sms-after-paste');
 console.log(await h.controls('main').then(s=>s.split('\n').filter(l=>!/^A (Transactions|Import|Accounts|Held)/.test(l)).slice(0,40).join('\n')));
 }catch(e){console.log('ERR',e.message.slice(0,300))}await h.close();})();
