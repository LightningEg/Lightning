const L=require('./lib');const fs=require('fs');
const PAGES=['/budget','/budget/fill','/budget/raise','/budget/move','/budget/carryover-bridge','/budget/settings','/settings?section=budget','/payday','/plan','/plan/recurring','/plan/loans','/plan/scenarios','/plan/inputs','/plan/items/new','/plan/purchases/new','/setup/salary','/plan/reserves','/review'];
const M=()=>{const main=document.querySelector('main')||document.body;const vis=e=>e.checkVisibility()&&e.getBoundingClientRect().height>0;
 const q=s=>[...main.querySelectorAll(s)].filter(vis).length;
 const inline=[...main.querySelectorAll('[style]')].filter(vis).length;
 return {title:(document.querySelector('h1')||{}).innerText,height:document.documentElement.scrollHeight,cards:q('.card,section.card'),charts:q('svg:not(.icon):not([width="16"]):not([width="18"]):not([width="20"]),canvas,.chart,.bar,.meter,progress,[class*=donut],[class*=spark]'),tables:q('table'),rows:q('tbody tr'),inputs:q('input:not([type=hidden]),select,textarea'),buttons:q('button,a.btn'),inlineStyles:inline,details:q('details'),overflowX:document.documentElement.scrollWidth>innerWidth+2,
  rawSelects:q('select:not([data-own-picker])'),h2:[...main.querySelectorAll('h2,h3')].filter(vis).map(e=>e.innerText.trim()).slice(0,14).join(' · '),
  lead:(main.innerText||'').replace(/\n+/g,' | ').slice(0,260)};};
(async()=>{const out={};for(const mode of ['pc','phone']){const h=await L.open(mode);out[mode]={};
 for(const u of PAGES){try{const r=await h.go(u);await h.p.waitForTimeout(350);const m=await h.p.evaluate(M);m.status=r.status();m.final=h.p.url().replace(h.O,'');out[mode][u]=m;
   const n=(mode==='pc'?'pc':'ph')+u.replace(/[\/?=]/g,'_');await h.shot('b/'+n);await h.full('b/'+n+'_full');}catch(e){out[mode][u]={err:e.message.slice(0,120)}}}
 await h.close();}
 fs.writeFileSync('b-metrics.json',JSON.stringify(out,null,1));
 for(const mode of ['pc','phone'])for(const [u,m] of Object.entries(out[mode]))console.log(mode,u,m.err||`${m.status} ${m.final!==u?'->'+m.final:''} "${m.title}" h=${m.height} cards=${m.cards} charts=${m.charts} tables=${m.tables} inputs=${m.inputs} btn=${m.buttons} inline=${m.inlineStyles} rawSel=${m.rawSelects} ovf=${m.overflowX}`);
})();
