const L=require('./lib');(async()=>{const h=await L.open('phone');const p=h.p;
const sheet=async()=>await p.evaluate(()=>{const f=document.querySelector('[name=amount]')?.form;if(!f)return 'NO FORM '+location.pathname+' :: '+document.body.innerText.replace(/\n+/g,' | ').slice(0,500);const v=n=>f.querySelector(`[name="${n}"]`)?.value;const kind=[...f.querySelectorAll('[name=kind]')].find(r=>r.checked)?.value;const hint=[...f.querySelectorAll('.help,.muted,[aria-live],.sms-note,.notice')].filter(e=>e.checkVisibility()).map(e=>e.innerText.trim()).filter(Boolean).join(' / ');return `kind=${kind} amount=${v('amount')} account=${f.querySelector('[name=account_id]')?.selectedOptions?.[0]?.text||v('account_id')} cat=${v('category_id')} who=${v('counterparty')} date=${v('date')} notes=${v('notes')} hints=[${hint.slice(0,300)}]`});
try{await h.ctx.grantPermissions(['clipboard-read','clipboard-write'],{origin:h.O});
 const msgs={
 'NBE ar card (known pattern)':"تم خصم 147.87 EGP من بطاقة الخصم المباشر رقم 1234 عند CARREFOUR MAADI يوم 06/11/26 الساعه 11:13 المتاح 3792.36EGP",
 'CIB EN card':"Your debit card ending with 1234 was charged EGP 250.00 at TALABAT on 08/11/26 at 21:15. Available balance EGP 10,200.50",
 'Vodafone Cash':"تم دفع 150 جنيه من محفظتك فودافون كاش الى التاجر Koshary El Tahrir. رصيدك الحالي 3000 جنيه",
 'USD':"Your card ending 1234 was charged USD 12.99 at NETFLIX.COM on 03/11/26",
 'OTP':"رمز التحقق الخاص بك هو 123456 لعملية شراء بمبلغ 500 جم"};
 let i=0;for(const [n,m] of Object.entries(msgs)){await h.go('/');await p.click('.phone-add');await p.waitForTimeout(600);
  await p.evaluate(t=>navigator.clipboard.writeText(t),m);
  await p.click('button:has-text("Paste SMS")');await p.waitForTimeout(1200);
  console.log('\n## '+n+'\nURL '+p.url().replace(h.O,'')+'\n'+await sheet());await h.shot('ph-sms-'+(++i));}
 }catch(e){console.log('ERR',e.message.slice(0,300))}await h.close();})();
