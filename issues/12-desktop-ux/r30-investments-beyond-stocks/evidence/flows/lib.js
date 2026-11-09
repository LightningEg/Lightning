const {chromium}=require('playwright');
exports.run=async(fn)=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1280,height:900}});
const B='http://127.0.0.1:8766';
const h={p,go:u=>p.goto(B+u),
 text:async(n=1500)=>(await p.evaluate(()=>(document.querySelector('main')||document.body).innerText)).replace(/\n{2,}/g,'\n').slice(0,n),
 msg:async()=>await p.evaluate(()=>[...document.querySelectorAll('.flash,.alert,.error,.notice,.has-error,[role=alert],.toast,.banner')].map(e=>e.innerText.trim().slice(0,300)).filter(Boolean).join(' || ')),
 fill:async(o)=>{for(const [k,v] of Object.entries(o)){const el=p.locator(`main [name="${k}"]:not([type=hidden])`).first();const tag=await el.evaluate(e=>e.tagName+':'+(e.type||''));
   if(tag.startsWith('SELECT'))await el.evaluate((e,v)=>{const o=[...e.options].find(o=>o.value===String(v)||o.text.trim()===String(v));if(!o)throw new Error('no option '+v+' in '+e.name);e.value=o.value;e.dispatchEvent(new Event('change',{bubbles:true}));},v);
   else if(tag.endsWith('checkbox')){if(v)await el.check({force:true});}
   else await el.fill(String(v),{force:true});}},
 submit:async(sel)=>{await Promise.all([p.waitForLoadState('load'),p.locator(sel).first().click()]);await p.waitForTimeout(500);},
 shot:n=>p.screenshot({path:'shots/'+n+'.png',fullPage:true}),
 log:async(tag)=>{console.log('\n### '+tag+'\nURL '+p.url().replace(B,'')+'\nMSG '+await h.msg());}};
try{await fn(h)}catch(e){console.log('ERR',e.message.slice(0,400))}await b.close()};
