const {chromium}=require('playwright');const fs=require('fs');
const H=JSON.parse(fs.readFileSync(__dirname+'/hosts.json'));
exports.open=async(mode)=>{const phone=mode==='phone';
 const b=await chromium.connectOverCDP('http://127.0.0.1:'+(phone?9334:9333));const ctx=b.contexts()[0];
 const p=ctx.pages()[0]||await ctx.newPage();await p.setViewportSize(phone?{width:390,height:800}:{width:1366,height:768});const O=H[mode].origin;
 const h={p,O,ctx,go:u=>p.goto(O+u),
  text:async(n=1500,sel)=>(await p.evaluate((sel)=>(document.querySelector(sel||'main')||document.body).innerText,sel)).replace(/\n{2,}/g,'\n').slice(0,n),
  shot:n=>p.screenshot({path:__dirname+'/shots/'+n+'.png',fullPage:false}),
  full:n=>p.screenshot({path:__dirname+'/shots/'+n+'.png',fullPage:true}),
  controls:async(sel)=>await p.evaluate((sel)=>[...(document.querySelector(sel||'main')||document.body).querySelectorAll('a[href],button,summary,select[name],input[name]:not([type=hidden]),textarea[name]')].filter(e=>e.checkVisibility()).map(e=>e.tagName==='A'?`A ${e.innerText.trim().slice(0,30)} -> ${e.getAttribute('href')}`:e.tagName==='SELECT'?`SELECT ${e.name} [${[...e.options].map(o=>o.text.trim()).join('|').slice(0,150)}]`:e.tagName==='INPUT'||e.tagName==='TEXTAREA'?`IN ${e.name} ${e.type}${e.required?' req':''}${e.placeholder?' ph='+e.placeholder:''}${e.value?' ='+e.value.slice(0,30):''}`:`${e.tagName} ${(e.innerText.trim()||e.getAttribute('aria-label')||'').slice(0,40)}`).join('\n'),sel),
  close:()=>b.close()};
 return h;};
exports.login=async(h,mode)=>{const p=h.p;await p.goto(H[mode].launch);await p.goto(h.O+'/profiles/new');
 await p.fill('[name=name]','Audit sample');for(const f of ['password','confirm'])await p.fill(`[name=${f}]`,'a dummy audit password');
 await p.fill('[name=answer]','Dummy');
 if(await p.locator('select[name=question]').count())await p.selectOption('[name=question]',{index:1});else await p.fill('[name=question]','Dummy question?');
 await p.click("form[action='/profiles/new'] button[type=submit]");
 const key=(await p.content()).match(/\d{4}-\d{4}-\d{4}/)[0];
 if(await p.locator('input[name=recovery][type=text]').count())await p.fill('[name=recovery]',key);
 await p.click("form[action='/profiles/confirm'] button[type=submit]");await p.goto(h.O+'/');
 await p.evaluate(async()=>{const t=document.querySelector('meta[name=lightning-session]').content;await fetch('/demo',{method:'POST',body:new URLSearchParams({__session:t})})});
 await p.goto(h.O+'/');};
