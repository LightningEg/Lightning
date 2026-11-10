const L=require('./lib');
(async()=>{const c=await L.open('pc');const p=c.p;
const msg=async(t)=>{await p.waitForTimeout(700);console.log('\n## '+t+' | '+p.url().replace(c.O,'').slice(0,90)+'\n   MSG: '+await p.evaluate(()=>[...document.querySelectorAll('.flash,.toast,[role=alert],[role=status],.has-error,.error')].map(e=>e.innerText.trim().replace(/\n+/g,' / ').slice(0,200)).filter(Boolean).join(' || ')));};
const top=async(n=3)=>console.log('   ROWS: '+await p.evaluate((n)=>[...document.querySelectorAll('main tbody tr')].filter(r=>r.querySelector('input[type=checkbox]')).slice(0,n).map(r=>r.innerText.replace(/\s+/g,' ').trim().slice(0,110)).join('  ¦  '),n));
const row=()=>p.locator('main form').filter({has:p.locator('[name=amount]')}).first();
try{
 // 1 transfer by typing an account name
 await c.go('/accounts/1');
 await p.fill('main [placeholder="Counterparty or your account"]','Cash wal');await p.waitForTimeout(700);
 console.log('suggest:',await p.evaluate(()=>[...document.querySelectorAll('[role=option],[role=listbox] li,.suggest-item,.ac-item')].filter(e=>e.checkVisibility()).map(e=>e.innerText.trim().replace(/\n/g,' ')).slice(0,6).join(' | ')));
 await p.keyboard.press('ArrowDown');await p.keyboard.press('Enter');await p.waitForTimeout(300);
 await p.fill('main [placeholder="-450 or 1,200"]','-500');await p.keyboard.press('Enter');await msg('1 transfer typed as account name, -500');await top(2);
 // 2 an expense with nothing but amount
 await c.go('/accounts/1');await p.fill('main [placeholder="-450 or 1,200"]','-75');await p.keyboard.press('Enter');await msg('2 amount only, -75');await top(1);
 // 3 positive number with expense category
 await c.go('/accounts/1');await p.fill('main [placeholder="Counterparty or your account"]','Carrefour');await p.keyboard.press('Tab');await p.waitForTimeout(600);
 console.log('category after payee:',await p.inputValue('main [placeholder="Category — type to search"]'));
 await p.fill('main [placeholder="-450 or 1,200"]','200');await p.keyboard.press('Enter');await msg('3 Carrefour +200 (no minus sign)');await top(1);
 // 4 future date
 await c.go('/accounts/1');await p.fill('main input[name=date]','2027-01-01');await p.fill('main [placeholder="Counterparty or your account"]','Carrefour');await p.fill('main [placeholder="-450 or 1,200"]','-10');await p.keyboard.press('Enter');await msg('4 future date');
 // 5 overdraw the wallet
 await c.go('/accounts/2');await p.fill('main [placeholder="Counterparty or your account"]','Carrefour');await p.fill('main [placeholder="-450 or 1,200"]','-999999');await p.keyboard.press('Enter');await msg('5 spend 999,999 from Cash wallet (10,475)');await top(1);
 }catch(e){console.log('ERR',e.message.slice(0,300))}await c.close();})();
