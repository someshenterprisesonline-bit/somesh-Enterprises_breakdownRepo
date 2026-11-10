// Rendered solid-color text checks. Gradients/SVG/paper layouts also receive screenshots.
module.exports = function contrastAudit() {
  const rgb = value => {const n = value.match(/[\d.]+/g)?.map(Number);return n && n.length >= 3 ? [...n.slice(0,3),n[3]??1] : [0,0,0,0];};
  const over = (a,b) => {const alpha = a[3]+b[3]*(1-a[3]);return [0,1,2].map(i=>(a[i]*a[3]+b[i]*b[3]*(1-a[3]))/(alpha||1)).concat(alpha);};
  const lum = a => a.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;}).reduce((n,x,i)=>n+x*[.2126,.7152,.0722][i],0);
  const ratio = (a,b) => (Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
  const bg = el => {const layers=[];for(let e=el;e;e=e.parentElement)layers.unshift(rgb(getComputedStyle(e).backgroundColor));return layers.reduce((n,c)=>over(c,n),[255,255,255,1]);};
  const visible = el => {
    if(!el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
    const r=el.getBoundingClientRect();if(!r.width||!r.height)return false;
    for(let p=el.parentElement;p&&p!==document.body;p=p.parentElement){const s=getComputedStyle(p);if(/hidden|auto|scroll|clip/.test(s.overflow+s.overflowY)){const b=p.getBoundingClientRect();if(r.bottom<=b.top||r.top>=b.bottom||r.right<=b.left||r.left>=b.right)return false;}}
    return true;
  };
  const issues=[],checked=new Set();let tested=0;
  function check(el,text,pseudo) {
    if(!visible(el)||el.closest('[disabled],[aria-hidden=true],svg,.skel,.brand-intro'))return;
    tested++;
    const css=getComputedStyle(el,pseudo),size=parseFloat(css.fontSize),bold=parseInt(css.fontWeight)>=700;
    const background=bg(el),foreground=over(rgb(css.color),background),actual=ratio(foreground,background);
    const minimum=size>=24||(bold&&size>=18.66)?3:4.5;
    if(actual+.02<minimum)issues.push({selector:el.id?'#'+el.id:el.tagName.toLowerCase()+'.'+[...el.classList].join('.'),text:text.trim().slice(0,65),ratio:+actual.toFixed(2),minimum,color:css.color,background:background.slice(0,3).map(Math.round)});
  }
  const modal=document.querySelector('dialog[open]'),walker=document.createTreeWalker(modal||document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()) {const node=walker.currentNode,el=node.parentElement;if(!node.textContent.trim()||!el||checked.has(el)||el.closest('script,style,option,optgroup'))continue;checked.add(el);check(el,node.textContent);}
  (modal||document).querySelectorAll('input,textarea,select').forEach(el=>{check(el,el.value||'Input');if(el.placeholder)check(el,el.placeholder,'::placeholder');});
  return {checked:tested,issues};
};
