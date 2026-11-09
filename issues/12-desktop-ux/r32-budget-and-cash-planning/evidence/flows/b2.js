const L=require('./lib');(async()=>{const h=await L.open('phone');
 await h.go('/budget');console.log((await h.text(1500,'body')).replace(/\n/g,' | '));
 console.log('LINKS',await h.p.evaluate(()=>[...document.querySelectorAll('main a[href]')].map(a=>a.innerText.trim().split('\n')[0].slice(0,25)+'->'+a.getAttribute('href')).join(' ; ')));
 await h.close();
 const c=await L.open('pc');await c.go('/budget');
 console.log('\nPC untouched/open:',await c.p.evaluate(()=>{document.querySelectorAll('main details').forEach(d=>d.open=true);return [...document.querySelectorAll('main details')].map(d=>d.innerText.replace(/\n+/g,' | ').slice(0,400)).join('\n--\n')}));
 console.log('PC links',await c.p.evaluate(()=>[...document.querySelectorAll('main a[href],main button')].map(a=>(a.innerText.trim().split('\n')[0]||a.getAttribute('aria-label')||'').slice(0,25)+'->'+(a.getAttribute('href')||'btn')).join(' ; ')));
 await c.go('/plan');console.log('\nPLAN menu',await c.p.evaluate(()=>[...document.querySelectorAll('header a[href], .page-head a[href], details.menu a[href], [class*=menu] a[href]')].map(a=>a.innerText.trim().slice(0,25)+'->'+a.getAttribute('href')).join(' ; ')));
 await c.close();})();
