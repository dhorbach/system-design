/* Behaviour shared by every guide page (templates/guide.html loads this with defer).
   It reads everything from the page's markup:
     section[data-toc|data-num|data-group|data-sub|data-nodes|data-more2|data-more3|data-ref]
     [data-l="2|3"]                depth levels
     .minimap .n[data-node][data-go]
     ul[data-reqs="FR|NFR"]        requirement lists; [data-req="FR1 NFR2"] tags the text that delivers them
     dl#glossary                   terms explained on hover
     figure.steps                  step-through diagram: [data-s="n"] parts and ol.stepnotes
     pre[data-lang]                syntax colouring
   A page's own demos start from the guide:ready event, fired once the chrome is built:
     document.addEventListener('guide:ready', e => { const {$, $$} = e.detail; ... });  */
(function(){
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const NAMES={1:'Overview',2:'Mechanics',3:'Full detail'};
const secs=$$('main section'), toc=$('#toc'), side=$('#side'), scrim=$('#scrim'), menu=$('#menu');
const still=matchMedia('(prefers-reduced-motion:reduce)').matches;
let depth=2, active=null;
try{const s=+localStorage.getItem('guide-depth'); if(s>=1&&s<=3) depth=s;}catch(e){}

/* build per-section chrome */
secs.forEach((sec,i)=>{
  const k=[...sec.classList].find(c=>c.startsWith('k-'))||'';
  const li=document.createElement('li');
  li.innerHTML='<a class="'+k+'" href="#'+sec.id+'"><span class="chip">'+(sec.dataset.num||'')+'</span><span>'+sec.dataset.toc+'</span></a><ol></ol>';
  if(sec.dataset.group){ const g=document.createElement('li'); g.className='grp'; g.textContent=sec.dataset.group; toc.appendChild(g); }
  if(sec.dataset.sub) li.classList.add('sub');
  toc.appendChild(li); sec._li=li;
  $$('h3',sec).forEach((h,j)=>{ if(!h.id) h.id=sec.id+'-'+(j+1); });
  if(sec.dataset.more2||sec.dataset.more3){
    const seg=document.createElement('div'); seg.className='seg'; seg.setAttribute('role','group'); seg.setAttribute('aria-label','Depth for this part');
    seg.innerHTML=[1,2,3].map(n=>'<button data-d="'+n+'" title="'+NAMES[n]+'" aria-label="'+NAMES[n]+' for this part"><b>'+n+'</b></button>').join('');
    seg.addEventListener('click',e=>{const b=e.target.closest('button'); if(b) setSec(sec,+b.dataset.d,true);});
    $('.sh',sec).appendChild(seg); sec._seg=seg;
    const m=document.createElement('div'); m.className='more'; sec.appendChild(m); sec._more=m;
  }
  const pn=document.createElement('div'); pn.className='pn';
  const p=secs[i-1], n=secs[i+1];
  pn.innerHTML=(p?'<a href="#'+p.id+'">Previous: '+p.dataset.toc+'</a>':'<span></span>')+(n?'<a href="#'+n.id+'">Next: '+n.dataset.toc+'</a>':'');
  sec.appendChild(pn);
});

function paintSec(sec){
  const d=+sec.dataset.depth;
  sec._li.dataset.d=d; sec._li.firstChild.dataset.diff=(sec._seg&&d!==depth)?'depth '+d:'';
  if(sec._seg) $$('button',sec._seg).forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.d===d)));
  if(sec._more){
    let nx=0; for(let n=d+1;n<=3;n++){ if(sec.dataset['more'+n]){nx=n;break;} }
    sec._more.hidden=!nx;
    if(nx){ sec._more.innerHTML='<span>'+NAMES[nx]+' adds '+sec.dataset['more'+nx]+'.</span><button>Show '+NAMES[nx].toLowerCase()+' for this part</button>';
      $('button',sec._more).onclick=()=>setSec(sec,nx,true); }
  }
  const ol=$('ol',sec._li); ol.innerHTML='';
  $$('h3',sec).forEach(h=>{ if(h.offsetParent===null) return; const li=document.createElement('li'); li.innerHTML='<a href="#'+h.id+'"></a>'; li.firstChild.textContent=h.textContent; ol.appendChild(li); });
}
function keep(fn){
  const a=active||secs[0], y=a.getBoundingClientRect().top; fn();
  window.scrollBy(0,a.getBoundingClientRect().top-y); spy();
}
function setSec(sec,d,anchor){
  const go=()=>{sec.dataset.depth=d; paintSec(sec);};
  if(anchor){ const y=sec.getBoundingClientRect().top; go(); window.scrollBy(0,sec.getBoundingClientRect().top-y); spy(); } else go();
}
function setAll(d,anchor){
  depth=d; try{localStorage.setItem('guide-depth',String(d));}catch(e){}
  const go=()=>secs.forEach(s=>setSec(s,d,false));
  anchor?keep(go):go();
  $$('#gseg button,#pick button').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.d===d)));
}
$('#gseg').addEventListener('click',e=>{const b=e.target.closest('button'); if(b) setAll(+b.dataset.d,true);});
$('#pick').addEventListener('click',e=>{const b=e.target.closest('button'); if(b) setAll(+b.dataset.d,false);});
document.addEventListener('keydown',e=>{
  if(e.target.matches('input,textarea,select')||e.metaKey||e.ctrlKey||e.altKey) return;
  if(e.key>='1'&&e.key<='3') setAll(+e.key,true);
  if(e.key==='Escape') drawer(false);
});

/* reading time per depth */
(function(){
  const w=[0,0,0,0];
  secs.filter(s=>!s.dataset.ref).forEach(s=>{
    const tw=document.createTreeWalker(s,NodeFilter.SHOW_TEXT); let n;
    while(n=tw.nextNode()){
      const el=n.parentElement; if(!el||el.closest('.more,.pn,.seg,.stepnotes,svg')) continue;
      let lv=1, a=el.closest('[data-l]'); while(a){lv=Math.max(lv,+a.dataset.l); a=a.parentElement&&a.parentElement.closest('[data-l]');}
      const c=(n.nodeValue.trim().match(/\S+/g)||[]).length; for(let d=lv;d<=3;d++) w[d]+=c;
    }
  });
  $$('#pick button').forEach(b=>{ $('em',b).textContent='About '+Math.max(1,Math.round(w[+b.dataset.d]/220))+' min'; });
})();

/* navigation */
function goTo(id,push){
  const el=document.getElementById(id); if(!el) return;
  el.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
  const sec=el.closest('section');
  if(push&&sec&&el===sec){ try{history.replaceState(null,'','#'+id);}catch(e){location.hash=id;} }
  drawer(false);
}
document.addEventListener('click',e=>{
  const a=e.target.closest('a[href^="#"]'); if(!a) return;
  const id=(a.getAttribute('href')||'').slice(1); if(!document.getElementById(id)) return;
  e.preventDefault(); goTo(id,true);
});
$$('.minimap .n').forEach(g=>{
  const f=()=>goTo(g.dataset.go,true);
  g.addEventListener('click',f); g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();f();}});
});
function drawer(o){ side.classList.toggle('open',o); scrim.classList.toggle('open',o); menu.setAttribute('aria-expanded',String(o)); }
menu.addEventListener('click',()=>drawer(!side.classList.contains('open')));
scrim.addEventListener('click',()=>drawer(false));

/* scroll spy */
let tick=false;
function spy(){
  tick=false;
  const top=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--bar'))+40;
  let cur=null; secs.forEach(s=>{ if(s.getBoundingClientRect().top<=top) cur=s; });
  if(cur!==active){
    active=cur;
    secs.forEach(s=>{ s._li.classList.toggle('open',s===cur); s._li.firstChild.classList.toggle('cur',s===cur); });
    const on=cur?(cur.dataset.nodes||'').split(' '):[];
    $$('.minimap .n').forEach(g=>g.classList.toggle('on',on.includes(g.dataset.node)));
    if(cur&&side.scrollHeight>side.clientHeight) cur._li.scrollIntoView({block:'nearest'});
  }
  if(cur){ let h=null; $$('h3',cur).forEach(x=>{ if(x.offsetParent!==null&&x.getBoundingClientRect().top<=top) h=x; });
    $$(':scope > ol a',cur._li).forEach(a=>a.classList.toggle('cur',!!h&&a.getAttribute('href')==='#'+h.id)); }
  const max=document.documentElement.scrollHeight-innerHeight;
  $('#prog').style.width=(max>0?Math.min(100,scrollY/max*100):0)+'%';
}
addEventListener('scroll',()=>{ if(!tick){tick=true; requestAnimationFrame(spy);} },{passive:true});
addEventListener('resize',spy);

/* inline term definitions, from <dl id="glossary">: each <dt> is a term and the <dd> after it the
   definition. data-match is the pattern to look for (default: the term itself, optionally plural),
   data-case makes it case-sensitive, data-code lets it match inside <code>. Order is priority. */
(function(){
  const lit=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const T=$$('#glossary dt').map(dt=>{
    const name=dt.textContent.trim(), dd=dt.nextElementSibling;
    return [name,new RegExp(dt.dataset.match||'\\b'+lit(name)+'s?\\b',dt.hasAttribute('data-case')?'':'i'),dd?dd.textContent.trim():'',dt.hasAttribute('data-code')];
  });
  if(!T.length) return;
  const tip=document.createElement('div'); tip.id='tip'; tip.setAttribute('role','tooltip'); tip.hidden=true; document.body.appendChild(tip);
  function show(b){
    const t=T[+b.dataset.t]; tip.innerHTML='<b></b><span></span>'; tip.firstChild.textContent=t[0]; tip.lastChild.textContent=t[2]; tip.hidden=false;
    const r=b.getBoundingClientRect(), w=tip.offsetWidth, h=tip.offsetHeight;
    let y=r.bottom+8; if(y+h>innerHeight-10) y=Math.max(10,r.top-h-8);
    tip.style.left=Math.max(10,Math.min(r.left,innerWidth-w-10))+'px'; tip.style.top=y+'px';
  }
  function hide(){ tip.hidden=true; }
  secs.forEach(sec=>{ [...sec.children].forEach(block=>{
    const used=new Set(), nodes=[], tw=document.createTreeWalker(block,NodeFilter.SHOW_TEXT); let n;
    $$('.brief>b:first-child',block).forEach(b=>T.forEach((t,i)=>{ if(t[1].test(b.textContent)) used.add(i); }));
    while(n=tw.nextNode()) nodes.push(n);
    nodes.forEach(node=>{
      const el=node.parentElement;
      if(!el||!el.closest('p,li,td,figcaption,.brief')||el.closest('a,button,pre,h2,h3,svg,.more,.pn,.ctl,.stepnotes')) return;
      const inCode=!!el.closest('code'), nt=el.closest('[data-noterm]'), ban=nt?nt.dataset.noterm.split('|'):[];
      while(node){
        let best=null;
        T.forEach((t,i)=>{ if(used.has(i)||(inCode&&!t[3])||ban.includes(t[0])) return; const m=t[1].exec(node.nodeValue); if(m&&(!best||m.index<best.m.index)) best={m,i}; });
        if(!best) break;
        const mid=node.splitText(best.m.index), rest=mid.splitText(best.m[0].length);
        const b=document.createElement('button'); b.type='button'; b.className='term'; b.dataset.t=best.i; b.setAttribute('aria-describedby','tip');
        mid.parentNode.replaceChild(b,mid); b.appendChild(mid); used.add(best.i); node=rest;
      }
    });
  });});
  const term=e=>e.target.closest?e.target.closest('.term'):null;
  document.addEventListener('mouseover',e=>{const b=term(e); if(b) show(b);});
  document.addEventListener('mouseout',e=>{const b=term(e); if(b&&document.activeElement!==b) hide();});
  document.addEventListener('focusin',e=>{const b=term(e); if(b) show(b);});
  document.addEventListener('focusout',e=>{ if(term(e)) hide(); });
  document.addEventListener('click',e=>{const b=term(e); b?show(b):hide();});
  addEventListener('scroll',hide,{passive:true});
})();

/* basic syntax colouring for code blocks. The language is <pre data-lang="…">; without it, a block
   starting with "package " is Go, one starting with an SQL statement is SQL, anything else JSON.
   To support another language, add a row: c = line-comment marker, q = string quote, kw = keywords. */
(function(){
  const LANGS={
    go:{c:'//',q:'"',kw:'package import type struct interface func return if else for range switch select case default break continue defer go var const chan map nil true false'},
    sql:{c:'--',q:"'",kw:'SELECT DISTINCT FROM JOIN LEFT INNER ON AS WHERE AND OR NOT IN IS NULL EXISTS CASE WHEN THEN ELSE END GROUP ORDER BY HAVING LIMIT OFFSET UNION ALL WITH '+
      'INSERT INTO VALUES UPDATE SET DELETE RETURNING CONFLICT DO NOTHING FOR SKIP LOCKED BEGIN COMMIT ROLLBACK CREATE ALTER DROP ADD TABLE INDEX PRIMARY KEY UNIQUE DEFAULT REFERENCES'},
    json:{c:'#',q:'"',kw:''}
  };
  const lit=s=>s.replace(/[.*+?^${}()|[\]\\\/]/g,'\\$&');
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  $$('pre code').forEach(c=>{
    const t=c.textContent, pre=c.closest('pre');
    const lang=pre.dataset.lang||(/^package /.test(t)?'go':/^\s*(SELECT|UPDATE|INSERT|DELETE|WITH|BEGIN|CREATE|ALTER)\b/.test(t)?'sql':'json'), L=LANGS[lang];
    if(!L) return;
    const re=new RegExp('('+lit(L.c)+'[^\\n]*)|('+L.q+'(?:[^'+L.q+'\\\\\\n]|\\\\.)*'+L.q+')(\\s*:)?|\\b(\\d+(?:\\.\\d+)?)\\b|\\b([A-Za-z_]\\w*)\\b','g'), kw=L.kw.split(' ');
    let out='', i=0, m;
    while(m=re.exec(t)){
      out+=esc(t.slice(i,m.index)); i=re.lastIndex;
      if(m[1]) out+='<span class="tc">'+esc(m[1])+'</span>';
      else if(m[2]) out+='<span class="'+(lang==='json'&&m[3]?'tk':'ts')+'">'+esc(m[2])+'</span>'+(m[3]||'');
      else if(m[4]) out+='<span class="tn">'+m[4]+'</span>';
      else out+=kw.includes(m[5])?'<span class="tw">'+m[5]+'</span>':m[5];
    }
    c.innerHTML=out+esc(t.slice(i));
  });
})();

/* requirement ids and references: items of <ul data-reqs="FR"> become FR1, FR2, …;
   an element with data-req="FR1 NFR2" gets a tag linking back to each */
(function(){
  const names={};
  $$('ul[data-reqs]').forEach(ul=>{ [...ul.children].forEach((li,i)=>{
    const id=ul.dataset.reqs+(i+1); li.id=id.toLowerCase(); names[id]=$('strong',li).textContent.replace(/\.$/,'');
    const b=document.createElement('span'); b.className='rid'; b.textContent=id; li.insertBefore(b,li.firstChild);
  });});
  $$('[data-req]').forEach(el=>{
    el.dataset.req.trim().split(/\s+/).forEach(id=>{ if(!names[id]) return;
      const a=document.createElement('a'); a.className='req'; a.href='#'+id.toLowerCase(); a.textContent=id; a.title=id+': '+names[id];
      a.setAttribute('aria-label','Implements requirement '+id+': '+names[id]); el.appendChild(a); });
  });
  document.addEventListener('click',e=>{
    const a=e.target.closest('a.req'); if(!a) return;
    const li=document.getElementById(a.getAttribute('href').slice(1));
    if(li){ li.classList.add('rflash'); setTimeout(()=>li.classList.remove('rflash'),1800); }
  });
})();

/* step-through diagrams: <figure class="steps"> holds parts marked data-s="1", "2", … and an
   <ol class="stepnotes"> with one note per step. Play, Next step and Show all are added here. */
$$('figure.steps').forEach(fig=>{
  const steps=$$('[data-s]',fig), cap=$('figcaption',fig), notes=$$('.stepnotes>li',fig).map(li=>li.textContent.trim());
  if(!steps.length||!cap) return;
  const n=Math.max(...steps.map(g=>+g.dataset.s)), base=cap.innerHTML;
  const ctl=document.createElement('div'); ctl.className='ctl';
  ctl.innerHTML='<button>Play</button><button>Next step</button><button>Show all</button>';
  fig.insertBefore(ctl,fig.firstChild);
  const [play,next,all]=ctl.children;
  let cur=n, timer=null, whole=true;
  function show(k){ cur=k; steps.forEach(g=>g.classList.toggle('off',+g.dataset.s>k)); if(whole) cap.innerHTML=base; else cap.textContent=notes[k-1]||''; }
  function stop(){ clearInterval(timer); timer=null; play.textContent='Play'; }
  play.addEventListener('click',()=>{ if(timer){stop();return;} whole=false; if(cur>=n) show(1); else show(cur+1);
    play.textContent='Pause'; timer=setInterval(()=>{ if(cur>=n){stop();return;} show(cur+1); },2200); });
  next.addEventListener('click',()=>{ stop(); whole=false; show(cur>=n?1:cur+1); });
  all.addEventListener('click',()=>{ stop(); whole=true; show(n); });
});

/* the page's own demos */
document.dispatchEvent(new CustomEvent('guide:ready',{detail:{$,$$,still}}));

/* citation address: filled in when the page is served from its own site */
(function(){
  const slot=$('#citeurl'); if(!slot) return;
  let own=false; try{ own=window.top===window.self; }catch(e){}
  if(own&&/^https?:$/.test(location.protocol)){
    const u=location.origin+location.pathname, a=document.createElement('a'); a.href=u; a.textContent=u; slot.replaceWith(a);
  }
})();

/* init + hash routing */
setAll(depth,false);
function route(){ const id=location.hash.slice(1); if(id&&secs.some(s=>s.id===id)) document.getElementById(id).scrollIntoView({block:'start'}); spy(); }
addEventListener('hashchange',route);
route();
})();
