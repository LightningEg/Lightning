/* The phone's translation lookup (phone roadmap M8): a cached file instead of inline on every page. Reads window.LIGHTNING_UI.
   An Arabic "{n} <counted noun>" agrees with its number (one, two, 3-10 plural, else singular), like i18n._agree_counts;
   window.LIGHTNING_COUNTED is that table. A number passed as `count` or `n` is formatted for the page after agreement. */
window.lightningT=(text,values)=>{
  const raw=String(text),given=values||{};
  let out=window.LIGHTNING_UI[raw],found={};
  if(!out){
    for(const [pattern,translated] of Object.entries(window.LIGHTNING_UI)){
      if(!pattern.includes('{'))continue;
      const names=[...pattern.matchAll(/\{([a-z_]+)\}/g)].map(m=>m[1]);
      const parts=pattern.split(/\{[a-z_]+\}/g).map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
      const match=new RegExp('^'+parts.join('(.+?)')+'$').exec(raw);
      if(match){out=translated;names.forEach((name,i)=>{found[name]=match[i+1];});break;}
    }
  }
  out=out||raw;
  const counted=window.LIGHTNING_COUNTED||{},forms={};
  for(const [lemma,[one,two,plural]] of Object.entries(counted))for(const form of [lemma,two,plural])forms[form]=lemma;
  const names=Object.keys(forms).sort((a,b)=>b.length-a.length);
  if(names.length){
    const phrase=new RegExp('\\{(\\w+)\\}\\s+('+names.join('|')+')(?![\\u0621-\\u064A])','g');
    out=out.replace(phrase,(whole,key,noun)=>{
      const value=key in given?given[key]:found[key];
      const number=typeof value==='number'?value:Number(String(value).replace(/,/g,''));
      if(value===undefined||value===''||!Number.isFinite(number))return whole;
      const [one,two,plural]=counted[forms[noun]];
      if(number===1)return one;
      if(number===2)return two;
      return Number.isInteger(number)&&number>=3&&number<=10?'{'+key+'} '+plural:'{'+key+'} '+forms[noun];
    });
  }
  for(const [name,value] of Object.entries(found))out=out.replaceAll(`{${name}}`,value);
  for(const [key,value] of Object.entries(given)){
    const shown=typeof value==='number'&&Number.isInteger(value)&&(key==='count'||key==='n')?value.toLocaleString(document.documentElement.lang||undefined):String(value);
    out=out.replaceAll(`{${key}}`,shown);
  }
  return out;
};
