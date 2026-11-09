require('./lib').run(async h=>{
 const P='#main-content form[action$="/purchase"], form[action$="/purchase"]';
 const buy=async(tag,o)=>{await h.go('/deposits/5');
   for(const [k,v] of Object.entries(o)){const el=h.p.locator(`form[action$="/purchase"] [name="${k}"]`).first();
     const t=await el.evaluate(e=>e.tagName);
     if(t==='SELECT')await el.evaluate((e,v)=>{const o=[...e.options].find(o=>o.text.includes(v));e.value=o.value;e.dispatchEvent(new Event('change',{bubbles:true}))},v);
     else await el.fill(String(v),{force:true});}
   await h.submit('button:has-text("Record CD purchase")');await h.log(tag);};
 await buy('J6a CD I already own, bought 2024-01-15 (before tracking began 2026-09-01)',{name:'Old BM certificate',start_date:'2024-01-15',principal:'50000',funding_account_id:'CIB',annual_rate:'27',term_years:'3',payout_frequency:'Monthly',destination_account_id:'CIB'});
 await buy('J6b CD bigger than cash',{name:'Too big',start_date:'2026-11-09',principal:'500000',funding_account_id:'CIB',annual_rate:'20',term_years:'3',payout_frequency:'Monthly',destination_account_id:'CIB'});
 await buy('J6c valid CD, no lock date, 1y at maturity',{name:'CIB 1-year',start_date:'2026-11-09',principal:'20000',funding_account_id:'CIB',annual_rate:'19',term_years:'1',payout_frequency:'At maturity',destination_account_id:'CIB'});
 console.log(await h.text(2200));
 await buy('J6d CD already matured: 2026-09-05 3 months',{name:'Short 3-month',start_date:'2026-09-05',principal:'10000',funding_account_id:'CIB',annual_rate:'18',term_years:'0.25',payout_frequency:'At maturity',destination_account_id:'CIB'});
 await buy('J6e blank term and maturity',{name:'No term',start_date:'2026-11-09',principal:'1000',funding_account_id:'CIB',annual_rate:'18'});
 await buy('J6f zero rate / negative principal',{name:'Bad',start_date:'2026-11-09',principal:'-5',funding_account_id:'CIB',annual_rate:'0',term_years:'1'});
 await h.go('/deposits/5');await h.shot('j6-deposits');
 console.log(await h.p.evaluate(()=>[...document.querySelectorAll('details')].filter(d=>d.querySelector('summary')?.innerText.includes('Actions')).map(d=>{d.open=true;return d.innerText.replace(/\n+/g,' | ').slice(0,600)}).join('\n--\n')));
 // new CD account with starting balance (certs I already own)
 await h.go('/accounts/new');
 await h.fill({institution:'Banque Misr',account_type:'Certificates of deposit (CD portfolio)',name:'BM CDs',opening_balance:'200000'});
 await h.submit('button:has-text("Add account")');await h.log('J6g CD account with starting balance');
 console.log(await h.text(2600));await h.shot('j6-legacy');
});
