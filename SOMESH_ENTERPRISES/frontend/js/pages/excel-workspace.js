"use strict";
const XL={user:null,node:null,books:[],templates:[],panels:new Map(),epoch:0,controllers:new Set(),libraryState:'idle',libraryError:'',libraryPromise:null,requestTimeout:20000};
const XL_SECTIONS=[['neft','NEFT SHEET','xlsx'],['worksheet','WORKSHEET','xlsx'],['letter','COVERING LETTER','docx']];
const xlEligible=()=>isAdmin()||['nandha','jagadeeshwari','sudharsan','rupashri'].includes(String(S.meta?.users.find(u=>u.name===S.user)?.identity_name||S.user||'').toLowerCase());
const xlDirty=()=>[...XL.panels.values()].some(p=>p.dirty());
function viewExcel(){return '<div id="excelHost"></div>';}
function xlDashboard(){return xlEligible()?'<section class="panel xl-dashboard"><div><h2>Excel Workspace</h2><p class="muted">Templates and your saved documents.</p></div><button class="btn primary" id="xlDashboard">Open Excel Workspace</button></section>':'';}
function xlPreserve(){if(XL.node?.isConnected)XL.node.remove();}
function xlResetSession(){XL.epoch++;for(const c of XL.controllers)c.abort();for(const p of XL.panels.values())p.dispose();XL.node?.remove();Object.assign(XL,{user:S.user,node:null,books:[],templates:[],panels:new Map(),controllers:new Set(),libraryState:'idle',libraryError:'',libraryPromise:null,requestTimeout:20000});}
const xlButton=(action,label,disabled=false)=>`<button type="button" class="btn" data-xl="${action}" ${disabled?'disabled':''}>${label}</button>`;
function xlLetter(n){let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
function xlStatus(text,error=false){const el=$('.xl-status',XL.node);if(el){el.textContent=text;el.classList.toggle('xl-error',error);}}
function xlCancelled(){return new DOMException('The profile changed or the request was cancelled.','AbortError');}
async function xlRequest(path,body,scope={}){
 const epoch=scope.epoch??XL.epoch,user=scope.user??S.user,token=scope.token??S.token;
 const current=()=>epoch===XL.epoch&&user===S.user&&token===S.token;
 if(!current())throw xlCancelled();
 const controller=new AbortController(),controllers=XL.controllers;controllers.add(controller);let timedOut=false;
 const timer=setTimeout(()=>{timedOut=true;controller.abort();},XL.requestTimeout);
 try{
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(token?{'X-Session':token}:{})},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:controller.signal});
  if(!current())throw xlCancelled();
  if(!response.ok){const error=await response.json().catch(()=>({error:'The server could not complete the request.'}));if(!current())throw xlCancelled();if(response.status===401&&error.login)logout(true);throw new Error(error.error||'Request failed.');}
  const result=scope.raw?{blob:await response.blob(),disposition:response.headers.get('Content-Disposition')}:await response.json();
  if(!current())throw xlCancelled();if(result.ok===false)throw new Error(result.error||'Request failed.');return result;
 }catch(e){if(!current())throw xlCancelled();if(timedOut)throw new Error('The request timed out. Check the connection and retry.');throw e;}
 finally{clearTimeout(timer);controllers.delete(controller);}
}
async function xlRefresh(){
 if(XL.libraryPromise)return XL.libraryPromise;
 const epoch=XL.epoch;XL.libraryState='loading';XL.libraryError='';for(const p of XL.panels.values())p.options();
 const work=(async()=>{
  try{const data=await xlRequest('/api/excel');if(epoch!==XL.epoch)throw xlCancelled();Object.assign(XL,data);XL.libraryState='ready';for(const p of XL.panels.values())p.options();const retry=XL.node?.querySelector('[data-xl="retrylibrary"]');if(retry)retry.hidden=true;return data;}
  catch(e){if(epoch===XL.epoch&&e.name!=='AbortError'){XL.libraryState='error';XL.libraryError=e.message;for(const p of XL.panels.values()){p.options();p.setState('error','Unable to load the template library. '+e.message);}const retry=XL.node?.querySelector('[data-xl="retrylibrary"]');if(retry)retry.hidden=false;xlStatus('Unable to load templates. '+e.message,true);}throw e;}
 })();XL.libraryPromise=work;
 try{return await work;}finally{if(epoch===XL.epoch)XL.libraryPromise=null;}
}
function wireExcel(){
 const dash=$('#xlDashboard');if(dash)dash.onclick=()=>{S.tab='excel';render();};
 document.body.classList.toggle('xl-wide',S.tab==='excel');if(S.tab!=='excel')return;if(XL.user!==S.user)xlResetSession();
 if(!XL.node){
  XL.node=document.createElement('section');XL.node.className='xl-workspace';
  XL.node.innerHTML=`<div class="xl-heading"><div><h1>Excel Workspace</h1><p class="muted">${esc(S.user)} · Your documents stay private.</p></div>${xlButton('back','Back')}${xlButton('refresh','Synchronize')}<button class="btn" type="button" data-xl="retrylibrary" hidden>Retry templates</button></div><p class="xl-status" role="status">Loading documents...</p><div class="xl-sections"></div>`;
  $('#excelHost').append(XL.node);
  for(const [key,title,format] of XL_SECTIONS){const p=new ExcelSection(key,title,format);XL.panels.set(key,p);$('.xl-sections',XL.node).append(p.root);}
  $('[data-xl="back"]',XL.node).onclick=()=>{S.tab=isAdmin()?'dash':'mine';render();};
  const epoch=XL.epoch;
  const synchronize=async()=>{try{await xlRefresh();if(epoch!==XL.epoch)return;xlStatus('Templates loaded. Hover to preview, or click a heading to pin it open.');for(const p of XL.panels.values())if(p.open&&!p.dirty())await p.run(()=>p.expand(p.pinned,true));}catch(e){if(epoch===XL.epoch&&e.name!=='AbortError')xlStatus(e.message,true);}};
  $('[data-xl="refresh"]',XL.node).onclick=synchronize;$('[data-xl="retrylibrary"]',XL.node).onclick=synchronize;
  xlRefresh().then(async()=>{if(epoch!==XL.epoch)return;xlStatus('Hover to preview, or click a heading to keep it open. New templates start empty.');const id=new URLSearchParams(location.search).get('excel'),b=XL.books.find(b=>b.id===id);if(b){const p=XL.panels.get(b.category);p.id=b.id;p.preview=false;await p.run(()=>p.expand(true));p.options();}}).catch(e=>{if(epoch===XL.epoch&&e.name!=='AbortError')xlStatus(e.message,true);});
 }else $('#excelHost').append(XL.node);
}
class ExcelSection{
 constructor(key,title,format){
  Object.assign(this,{key,title,format,id:null,preview:true,open:false,pinned:false,busy:false,sheet:null,meta:null,grid:null,book:null,document:null,changes:new Map(),touched:new Map(),baselines:new Map(),calculations:new Map(),undo:[],redo:[],offset:0,query:'',column:'0',filter:'',sort:'',direction:'asc',selection:null,widths:new Map(),calcSequence:0,owner:S.user,token:S.token,epoch:XL.epoch,disposed:false,dialogs:new Set(),state:'idle'});
  this.root=document.createElement('article');this.root.className='xl-section';this.root.dataset.section=key;
  this.root.innerHTML=`<div class="xl-section-head"><button type="button" class="xl-title" aria-expanded="false"><h2>${title}</h2><small class="xl-original-name"></small></button><div class="xl-header-actions">${xlButton('upload','Upload Completed File')}${xlButton('blank','New Blank Template')}${xlButton('edit','Edit')}${xlButton('download',format==='docx'?'Download Word':'Download Excel')}${xlButton('expand',format==='docx'?'Preview':'Expand')}</div></div><div class="xl-file-line"><label>Open <select class="in xl-file" aria-label="${title} saved files"></select></label><span class="xl-file-state"></span></div><div class="xl-reveal"><div><div class="xl-section-body"><p class="xl-message" role="status"></p><button type="button" class="btn" data-xl="retry" hidden>Retry preview</button><div class="xl-editor-host"></div></div></div></div><input class="xl-file-input" type="file" accept=".${format}" hidden>`;
  $('.xl-title',this.root).onclick=()=>{this.pinned=true;this.run(()=>this.expand(true));};
  this.root.onpointerenter=e=>{if(e.pointerType==='touch')return;clearTimeout(this.closeTimer);clearTimeout(this.hoverTimer);this.hoverTimer=setTimeout(()=>this.run(()=>this.expand(false)),120);};
  this.root.onpointerleave=()=>{clearTimeout(this.hoverTimer);this.closeTimer=setTimeout(()=>{if(!this.pinned&&!this.dirty()&&!this.root.contains(document.activeElement))this.collapse();},260);};
  $('.xl-file',this.root).onchange=e=>this.run(async()=>{if(this.dirty()&&!confirm('Discard unsaved changes in this document?')){e.target.value=this.preview?'':this.id;return;}this.resetDraft();this.id=e.target.value||this.template()?.id||null;this.preview=!e.target.value;this.sheet=null;this.offset=0;this.query='';this.filter='';this.sort='';this.column='0';this.widths.clear();await this.expand(true,true);});
  $('.xl-reveal',this.root).inert=true;
  $('.xl-file-input',this.root).onchange=e=>{const f=e.target.files[0];if(f)this.run(()=>this.upload(f));e.target.value='';};this.bind(this.root);
 }
 dispose(){this.disposed=true;clearTimeout(this.closeTimer);clearTimeout(this.hoverTimer);clearTimeout(this.calcTimer);this.calcSequence++;for(const dialog of this.dialogs){dialog.dispatchEvent(new Event('cancel'));dialog.close();dialog.remove();}this.dialogs.clear();}
 alive(){return !this.disposed&&this.epoch===XL.epoch&&this.owner===S.user&&this.token===S.token;}
 assertAlive(){if(!this.alive())throw xlCancelled();}
 request(path,body,raw=false){this.assertAlive();return xlRequest(path,body,{epoch:this.epoch,user:this.owner,token:this.token,raw});}
 template(){return XL.templates.find(t=>t.category===this.key);}
 dirty(){return this.changes.size>0;}
 resetDraft(){this.changes.clear();this.touched.clear();this.baselines.clear();this.calculations.clear();this.undo=[];this.redo=[];this.selection=null;this.calcSequence++;clearTimeout(this.calcTimer);}
 message(text,error=false){if(!this.alive())return;const el=$('.xl-message',this.root);el.textContent=text;el.classList.toggle('xl-error',error);el.setAttribute('role',error?'alert':'status');}
 setState(state,text){if(!this.alive())return;this.state=state;this.root.dataset.loadState=state;this.root.setAttribute('aria-busy',state==='loading'?'true':'false');const retry=this.root.querySelector('[data-xl="retry"]');if(retry)retry.hidden=state!=='error';this.message(text,state==='error');}
 async run(fn){const work=(this.pending||Promise.resolve()).then(async()=>{if(!this.alive())return;this.busy=true;this.root.setAttribute('aria-busy','true');try{await fn();}catch(e){if(this.alive()&&e.name!=='AbortError'){this.setState('error',e.message);xlStatus(e.message,true);}}finally{this.busy=false;this.root.setAttribute('aria-busy','false');}});this.pending=work;return work;}
 options(){
  const select=$('.xl-file',this.root),own=XL.books.filter(b=>b.category===this.key&&!b.master),t=this.template(),blanks=own.filter(b=>b.origin==='blank'),saved=own.filter(b=>b.origin!=='blank');
  const group=(label,books)=>books.length?`<optgroup label="${label}">${books.map(b=>`<option value="${b.id}">${esc(b.name)} · v${b.revision}</option>`).join('')}</optgroup>`:'';
  select.innerHTML='<option value="">Blank template preview</option>'+group('My blank templates and work',blanks)+group('Previously saved and uploaded files',saved)+(isAdmin()?group('Master references',XL.books.filter(b=>b.category===this.key&&b.master)):'');select.value=this.preview?'':this.id;
  if(this.preview){const next=t?.id||null;if(this.id!==next){this.grid=null;this.document=null;this.meta=null;this.sheet=null;}this.id=next;}
  $('.xl-original-name',this.root).textContent=(this.preview?t?.name:XL.books.find(b=>b.id===this.id)?.name)||(XL.libraryState==='error'?'Template library unavailable':XL.libraryState==='loading'?'Loading templates...':'Template not configured');$('.xl-file-state',this.root).textContent=this.preview?'Empty template preview':this.dirty()?'Unsaved changes':'Saved document';
  $('[data-xl="blank"]',this.root).disabled=XL.libraryState!=='ready'||!t||t.can_edit===false||t.locked;$('[data-xl="download"]',this.root).disabled=this.preview||!this.id||(!isAdmin()&&this.book&&!this.book.can_download);
 }
 async expand(pin=false,reload=false){
  this.assertAlive();clearTimeout(this.closeTimer);if(pin)this.pinned=true;this.open=true;$('.xl-reveal',this.root).inert=false;this.root.classList.add('is-open');$('.xl-title',this.root).setAttribute('aria-expanded','true');
  if(this.preview&&XL.libraryState==='loading'){this.setState('loading','Loading templates...');await XL.libraryPromise;this.assertAlive();}
  if(this.preview&&XL.libraryState==='error')throw new Error('Unable to load the template library. Use Retry templates or Synchronize.');
  if(!this.id)this.id=this.template()?.id;
  if(!this.id){this.setState('empty','This template is not configured in the shared library. Upload a completed file or ask an admin to configure it.');return;}
  if((!this.grid&&!this.document)||reload||this.state==='error')await this.load();
 }
 collapse(){this.open=false;$('.xl-reveal',this.root).inert=true;this.pinned=false;this.root.classList.remove('is-open','xl-large','xl-fullscreen');$('.xl-title',this.root).setAttribute('aria-expanded','false');}
 async load(){
  this.assertAlive();this.setState('loading','Loading preview...');try{const params=new URLSearchParams({id:this.id,template:this.preview?'1':'0'}),result=await this.request('/api/excel/metadata?'+params);
  if(this.dirty()&&this.book&&result.book.revision!==this.book.revision)throw new Error('A newer version exists. Reset your draft to load it, or save to check for conflicts.');this.book=result.book;this.meta=result;
  if(this.format==='docx'){this.document=result.document;this.grid=null;this.drawDocument();this.loaded();}else{this.sheet=this.sheet&&result.sheets.some(s=>s.name===this.sheet)?this.sheet:result.sheets[0].name;await this.loadGrid();}
  }catch(e){if(this.alive()&&e.name!=='AbortError')this.setState('error',e.message);throw e;}
 }
 loaded(){this.setState('ready',this.preview?'Blank preview ready. Select New Blank Template to start your own document.':this.dirty()?`${this.changes.size} unsaved changes`:'All changes saved.');this.options();}
 async loadGrid(){
  this.assertAlive();this.setState('loading','Loading worksheet...');try{const params=new URLSearchParams({id:this.id,template:this.preview?'1':'0',sheet:this.sheet,offset:this.offset,limit:50,q:this.query,column:this.column,filter:this.filter,sort:this.sort,direction:this.direction}),grid=await this.request('/api/excel/sheet?'+params);
  if(this.dirty()&&this.book&&grid.book.revision!==this.book.revision)throw new Error('Conflict: synchronize after saving or resetting your draft.');this.grid=grid;this.book=grid.book;this.drawEditor();this.loaded();if(this.dirty())this.scheduleCalculation();
  }catch(e){if(this.alive()&&e.name!=='AbortError')this.setState('error',e.message);throw e;}
 }
 bind(root){root.querySelectorAll('[data-xl]').forEach(b=>b.onclick=e=>{e.stopPropagation();this.run(()=>this.action(b.dataset.xl));});}
 tools(){return `<div class="xl-editor-bar">${xlButton('save','Save Changes',this.preview||this.book?.locked||(!isAdmin()&&!this.book?.can_edit))}${xlButton('undo','Undo',this.preview)}${xlButton('redo','Redo',this.preview)}${xlButton('reset','Reset Unsaved Changes',this.preview)}${xlButton('newtab','Open in New Tab',this.preview)}${xlButton('close','Close / Collapse')}</div>`;}
 drawEditor(){
  const host=$('.xl-editor-host',this.root),g=this.grid;
  host.innerHTML=`<div class="xl-editor">${this.tools()}<div class="xl-grid-tools"><label>Worksheet <select class="in xl-sheet">${this.meta.sheets.map(s=>`<option ${s.name===this.sheet?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label><label>Search <input class="in xl-search" type="search" value="${esc(this.query)}"></label><label>Column <select class="in xl-column"><option value="0">All</option>${Array.from({length:g.columns},(_,i)=>`<option value="${i+1}" ${this.column===String(i+1)?'selected':''}>${xlLetter(i+1)}</option>`).join('')}</select></label><label>Filter <input class="in xl-filter" value="${esc(this.filter)}"></label>${xlButton('search','Apply')}<details class="xl-more"><summary>Rows and cell tools</summary><div>${xlButton('add','Add row',this.preview)}${xlButton('delete','Delete row',this.preview)}<label>Row <input class="in xl-row" type="number" placeholder="End of sheet"></label><label>Empty cell type <select class="in xl-type"><option value="text">Text</option><option value="number">Number</option><option value="date">Date</option></select></label></div></details></div><div class="xl-grid-wrap" tabindex="0"><table class="xl-grid" aria-label="${esc(this.sheet)}"></table></div><div class="xl-pagination">${xlButton('prev','Previous',!this.offset)}<span>${g.total?g.offset+1:0}–${Math.min(g.total,g.offset+50)} of ${g.total} rows</span>${xlButton('next','Next',g.offset+50>=g.total)}</div>${isAdmin()?this.admin():''}</div>`;
  $('.xl-sheet',host).onchange=e=>this.run(async()=>{this.sheet=e.target.value;this.offset=0;this.query='';this.filter='';this.sort='';this.selection=null;await this.loadGrid();});this.bind(host);this.drawTable();
 }
 drawTable(){
  const table=$('.xl-grid',this.root),g=this.grid;if(!table)return;
  table.innerHTML=`<thead><tr><th>#</th>${Array.from({length:g.columns},(_,i)=>`<th style="${this.widths.has(i+1)?'width:'+this.widths.get(i+1)+'px;min-width:'+this.widths.get(i+1)+'px':''}"><button type="button" data-sort="${i+1}">${xlLetter(i+1)}</button><span class="xl-resizer" data-resize="${i+1}"></span></th>`).join('')}</tr>${g.header_rows.map(row=>`<tr class="xl-original-header"><th></th>${row.map(v=>`<th>${esc(v??'')}</th>`).join('')}</tr>`).join('')}</thead><tbody>${g.rows.map(r=>`<tr><th>${r.number}</th>${r.cells.map(c=>{const change=this.changes.get(this.sheet+'!'+c.address),calculation=this.calculations.get(this.sheet+'!'+c.address),value=change?change.value:c.formula?(calculation?.display??c.display??c.value):c.value;return `<td class="${c.formula?'xl-calculated ':''}${change?'xl-modified':''}"><input aria-label="${c.address}" data-cell="${c.address}" value="${esc(value)}" ${this.preview||!c.editable?'readonly':''} placeholder="${c.formula&&c.calculation==='pending'?'Recalculation pending':''}" title="${c.formula?'Calculated field':esc(c.address)}" spellcheck="false"></td>`;}).join('')}</tr>`).join('')}</tbody>`;
  $('thead',table).onpointerenter=()=>this.root.classList.add('xl-large');const cells=new Map(g.rows.flatMap(r=>r.cells).map(c=>[c.address,c]));
  table.querySelectorAll('[data-cell]').forEach(input=>{
   const cell=cells.get(input.dataset.cell);input.onfocus=()=>{this.pinned=true;};
   input.onpointerdown=e=>{const r=g.rows.findIndex(r=>r.cells.some(c=>c.address===cell.address)),c=g.rows[r].cells.indexOf(cell);if(e.shiftKey&&this.selection){e.preventDefault();this.selection.end=[r,c];}else this.selection={start:[r,c],end:[r,c]};table.querySelectorAll('td').forEach(t=>t.classList.remove('xl-selected'));const a=this.selection.start,z=this.selection.end;for(let i=Math.min(a[0],z[0]);i<=Math.max(a[0],z[0]);i++)for(let j=Math.min(a[1],z[1]);j<=Math.max(a[1],z[1]);j++)table.tBodies[0].rows[i]?.cells[j+1]?.classList.add('xl-selected');};
   input.oninput=()=>{if(this.preview||!cell.editable)return;this.setCell(cell,input.value);input.parentElement.classList.toggle('xl-modified',this.changes.has(this.sheet+'!'+cell.address));};
   input.onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();this.action(e.key.toLowerCase()==='y'||e.shiftKey?'redo':'undo');return;}const moves={ArrowDown:[1,0],ArrowUp:[-1,0],ArrowLeft:[0,-1],ArrowRight:[0,1],Tab:[0,e.shiftKey?-1:1],Enter:[e.shiftKey?-1:1,0]},m=moves[e.key];if(!m)return;if(['ArrowLeft','ArrowRight'].includes(e.key)&&input.selectionStart!==(e.key==='ArrowLeft'?0:input.value.length))return;const r=[...table.tBodies[0].rows].indexOf(input.closest('tr')),c=input.parentElement.cellIndex-1,target=table.tBodies[0].rows[r+m[0]]?.cells[c+m[1]+1]?.querySelector('input');if(target){e.preventDefault();target.focus();target.select();}};
   input.onpaste=e=>{const text=e.clipboardData.getData('text/plain');if(!/[\t\n]/.test(text))return;e.preventDefault();const ri=[...table.tBodies[0].rows].indexOf(input.closest('tr')),ci=input.parentElement.cellIndex-1,updates=[];for(const [r,line] of text.replace(/\r/g,'').replace(/\n$/,'').split('\n').entries())for(const [c,value] of line.split('\t').entries()){const dest=g.rows[ri+r]?.cells[ci+c];if(this.preview||!dest?.editable){this.message('Paste cancelled: range includes protected cells or extends beyond this page.',true);return;}updates.push([dest,value]);}updates.forEach(([c,v])=>this.setCell(c,v));this.drawTable();};
   input.oncopy=e=>{const sel=this.selection;if(!sel)return;const a=sel.start,z=sel.end;if(a[0]===z[0]&&a[1]===z[1])return;e.preventDefault();e.clipboardData.setData('text/plain',g.rows.slice(Math.min(a[0],z[0]),Math.max(a[0],z[0])+1).map(r=>r.cells.slice(Math.min(a[1],z[1]),Math.max(a[1],z[1])+1).map(c=>this.changes.get(this.sheet+'!'+c.address)?.value??(c.formula?c.display:c.value)).join('\t')).join('\n'));};
  });
  table.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>this.run(async()=>{this.direction=this.sort===b.dataset.sort&&this.direction==='asc'?'desc':'asc';this.sort=b.dataset.sort;this.offset=0;await this.loadGrid();}));
  table.querySelectorAll('[data-resize]').forEach(h=>h.onpointerdown=e=>{e.preventDefault();const th=h.parentElement,x=e.clientX,width=th.getBoundingClientRect().width;h.setPointerCapture(e.pointerId);h.onpointermove=ev=>{const size=Math.max(70,width+ev.clientX-x);th.style.width=th.style.minWidth=size+'px';this.widths.set(Number(h.dataset.resize),size);};h.onpointerup=()=>{h.onpointermove=null;};});
 }
 setCell(cell,value){const key=this.sheet+'!'+cell.address,before=this.changes.get(key)||null,type=cell.type==='n'&&cell.value===''?$('.xl-type',this.root).value:cell.type,after=value===cell.value?null:{sheet:this.sheet,address:cell.address,value,type};if(!this.baselines.has(key))this.baselines.set(key,{sheet:this.sheet,address:cell.address,value:cell.value,type});this.touched.set(key,after||this.baselines.get(key));if(after)this.changes.set(key,after);else this.changes.delete(key);this.undo.push({key,before,after});this.redo=[];this.edited();}
 edited(){this.pinned=true;this.message(`${this.changes.size} unsaved changes`);$('.xl-file-state',this.root).textContent='Unsaved changes';if(this.format==='xlsx')this.scheduleCalculation();}
 scheduleCalculation(){clearTimeout(this.calcTimer);const sequence=++this.calcSequence;this.calcTimer=setTimeout(async()=>{try{const result=await this.request('/api/excel/calculate',{id:this.id,revision:this.book.revision,changes:[...this.touched.values()]});if(sequence!==this.calcSequence)return;this.calculations=new Map(result.calculations.map(c=>[c.sheet+'!'+c.address,c]));for(const c of result.calculations){if(c.sheet!==this.sheet)continue;const input=this.root.querySelector(`[data-cell="${c.address}"]`);if(input){input.value=c.display??c.value;input.placeholder=c.status==='pending'?'Recalculation pending':'';}}}catch(e){if(sequence===this.calcSequence)this.message(e.message,true);}},280);}
 paragraph(p){const changed=this.changes.get(String(p.index)),runs=p.runs.map(r=>`<span style="font-size:${Number(r.size)||12}pt;font-weight:${r.bold?'bold':'normal'};font-style:${r.italic?'italic':'normal'};text-decoration:${r.underline?'underline':'none'};font-family:${esc((r.font||'Times New Roman').replace(/[^a-zA-Z0-9 ,_-]/g,''))}">${esc(r.text)}</span>`).join('');return `<div class="xl-word-block">${(p.images||[]).map(img=>`<img class="xl-word-image" alt="Original document letterhead" draggable="false" src="data:${img.mime};base64,${img.data}">`).join('')}<div class="xl-word-paragraph" data-paragraph="${p.index}" role="textbox" aria-label="Paragraph ${p.index+1}" contenteditable="${!!(!this.preview&&!this.book.locked&&(isAdmin()||this.book.can_edit))}" style="text-align:${['left','right','center','both','justify'].includes(p.alignment)?p.alignment.replace('both','justify'):'left'}">${changed?esc(changed.text):runs||'<br>'}</div></div>`;}
 drawDocument(){
  const host=$('.xl-editor-host',this.root),margin=this.document.page.pgMar||{},padding=['top','right','bottom','left'].map(k=>Math.min(Number(margin[k]||720)/20,80)+'pt').join(' ');
  host.innerHTML=`<div class="xl-editor">${this.tools()}<div class="xl-word-scroll"><div class="xl-word-page" style="padding:${padding}">${this.document.blocks.map(b=>b.type==='paragraph'?this.paragraph(b):'<table class="xl-word-table">'+b.rows.map(row=>'<tr>'+row.map(cell=>'<td>'+cell.map(p=>this.paragraph(p)).join('')+'</td>').join('')+'</tr>').join('')+'</table>').join('')}</div></div>${isAdmin()?this.admin():''}</div>`;
  host.querySelectorAll('[data-paragraph]').forEach(el=>{
   el.onfocus=()=>{this.pinned=true;};
   el.oninput=()=>{const key=el.dataset.paragraph,original=this.document.blocks.flatMap(b=>b.type==='paragraph'?[b]:b.rows.flat(2)).find(p=>String(p.index)===key),before=this.changes.get(key)||null,after=el.innerText===original.text?null:{paragraph:Number(key),text:el.innerText};if(after)this.changes.set(key,after);else this.changes.delete(key);this.undo.push({key,before,after});this.redo=[];this.edited();};
   el.onpaste=e=>{e.preventDefault();document.execCommand('insertText',false,e.clipboardData.getData('text/plain'));};
   el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();document.execCommand('insertLineBreak');}if((e.ctrlKey||e.metaKey)&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();this.action(e.key.toLowerCase()==='y'||e.shiftKey?'redo':'undo');}};
  });this.bind(host);
 }
 admin(){return `<details class="xl-admin"><summary>Admin management</summary><div class="xl-admin-tools"><label>Assign to <select class="in xl-employee">${(XL.employees||[]).map(n=>`<option>${esc(n)}</option>`).join('')}</select></label>${xlButton('assign','Assign blank template')}${xlButton('master','Upload master')}${['can_view','can_edit','can_download','locked','formulas_unlocked'].map(k=>`<label><input type="checkbox" data-permission="${k}" ${this.book[k]?'checked':''}>${esc(k.replaceAll('_',' '))}</label>`).join('')}${xlButton('permissions','Save permissions')}${xlButton('history','Version history')}</div><div class="xl-history"></div></details>`;}
 async upload(file){
  if(!file.name.toLowerCase().endsWith('.'+this.format))throw new Error('Choose a .'+this.format+' file. Convert legacy files first.');if(file.size>10*1024*1024)throw new Error('Upload limit is 10 MB.');this.message('Validating completed file...');
  const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);}),pending=await this.request('/api/excel/preview',{name:file.name,data}),dialog=document.createElement('dialog');dialog.className='xl-dialog xl-import-dialog';
  dialog.innerHTML=`<h2>Upload Completed File</h2><p>${esc(file.name)}</p><p>The uploaded file will be saved independently, with its current values and formulas.</p>${this.format==='xlsx'?`<label>Preview worksheet <select class="in xl-import-sheet">${pending.sheets.map(s=>`<option>${esc(s.name)}</option>`).join('')}</select></label><div class="xl-import-preview"></div>`:'<p>Word document validated. Original layout and text will be retained.</p>'}<div class="xl-dialog-actions"><button class="btn" data-cancel>Cancel</button><button class="btn primary" data-confirm>Confirm import</button></div>`;document.body.append(dialog);this.dialogs.add(dialog);
  if(this.format==='xlsx'){const draw=()=>{const s=pending.sheets.find(s=>s.name===$('.xl-import-sheet',dialog).value);$('.xl-import-preview',dialog).innerHTML='<div class="xl-grid-wrap"><table class="xl-import-table"><thead>'+s.header_rows.map(r=>'<tr>'+r.map(c=>'<th>'+esc(c??'')+'</th>').join('')+'</tr>').join('')+'</thead><tbody>'+s.preview_rows.map(r=>'<tr>'+r.map(c=>'<td>'+esc(c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';};$('.xl-import-sheet',dialog).onchange=draw;draw();}
  const confirmed=await new Promise(resolve=>{dialog.oncancel=()=>resolve(false);$('[data-cancel]',dialog).onclick=()=>{dialog.close();resolve(false);};$('[data-confirm]',dialog).onclick=()=>{dialog.close();resolve(true);};dialog.showModal();});dialog.remove();this.dialogs.delete(dialog);if(!confirmed){this.masterUpload=false;this.message('Upload cancelled. Existing documents are unchanged.');return;}
  const result=await this.request('/api/excel/import',{preview:pending.preview,completed:true,category:this.key,master:!!this.masterUpload,slot:this.key==='neft'?1:this.key==='worksheet'?2:3});this.masterUpload=false;this.resetDraft();this.id=result.id;this.preview=false;this.sheet=null;this.offset=0;this.query='';this.filter='';this.sort='';this.column='0';this.widths.clear();await xlRefresh();await this.expand(true,true);this.message('Completed file imported unchanged as an independent document.');
 }
 async save(){
  if(!this.dirty())return;this.calcSequence++;clearTimeout(this.calcTimer);
  const fields=[...this.root.querySelectorAll('[data-cell],[contenteditable="true"]')];
  const editable=fields.map(el=>el.getAttribute('contenteditable'));
  fields.forEach(el=>{if(el.matches('[data-cell]'))el.disabled=true;else el.contentEditable='false';});
  try{
   const payload={id:this.id,revision:this.book.revision};payload[this.format==='docx'?'paragraphs':'changes']=[...this.changes.values()];
   await this.request('/api/excel/save',payload);this.resetDraft();await this.load();await xlRefresh();this.message('Changes saved.');
  }finally{fields.forEach((el,i)=>{el.disabled=false;if(editable[i]!==null)el.setAttribute('contenteditable',editable[i]);});}
 }
 async download(version){
  const dialog=document.createElement('dialog');dialog.className='xl-dialog xl-filename-dialog';const name=(this.book?.name||this.title).replace(/\.(xlsx|docx)$/i,'');
  dialog.innerHTML=`<h2>${this.format==='docx'?'Download Word':'Download Excel'}</h2><label>File name <input class="in xl-filename" value="${esc(name)}" required maxlength="140"></label><p class="muted">.${this.format} is added automatically.</p>${this.dirty()?'<p>There are unsaved changes. Download the saved version, or save your changes first.</p>':''}<p class="xl-filename-error" role="alert"></p><div class="xl-dialog-actions"><button class="btn" data-cancel>Cancel</button><button class="btn" data-download>${this.dirty()?'Download saved version':'Download'}</button>${this.dirty()?'<button class="btn primary" data-save-download>Save and download</button>':''}</div>`;document.body.append(dialog);this.dialogs.add(dialog);
  const done=await new Promise(resolve=>{const choose=save=>{const value=$('.xl-filename',dialog).value.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/\.(xlsx|docx)$/i,'').trim().replace(/[. ]+$/,'');if(!value){$('.xl-filename-error',dialog).textContent='Enter a filename.';return;}dialog.close();resolve({name:value,save});};dialog.oncancel=()=>resolve(null);$('[data-cancel]',dialog).onclick=()=>{dialog.close();resolve(null);};$('[data-download]',dialog).onclick=()=>choose(false);const save=$('[data-save-download]',dialog);if(save)save.onclick=()=>choose(true);dialog.showModal();$('.xl-filename',dialog).select();});dialog.remove();this.dialogs.delete(dialog);if(!done)return;if(done.save)await this.save();
  const params=new URLSearchParams({id:this.id,filename:done.name,...(version?{version}: {})}),r=await this.request('/api/excel/download?'+params,undefined,true);this.assertAlive();const url=URL.createObjectURL(r.blob),a=document.createElement('a');a.href=url;const disposition=r.disposition?.match(/filename\*=UTF-8''(.+)/i);a.download=disposition?decodeURIComponent(disposition[1]):done.name+'.'+this.format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async action(action){
  this.assertAlive();
  if(action==='retry'){if(XL.libraryState!=='ready')await xlRefresh();this.assertAlive();if(this.preview)this.id=this.template()?.id;await this.expand(true,true);return;}
  if(action==='close'){this.collapse();return;}
  if(action==='upload'||action==='master'){if(this.dirty())throw new Error('Save or reset your draft before uploading.');this.masterUpload=action==='master';$('.xl-file-input',this.root).click();return;}
  if(action==='blank'){if(XL.libraryState!=='ready')await xlRefresh();this.assertAlive();if(this.dirty()&&!confirm('Creating a new document discards this unsaved draft. Continue?'))return;const t=this.template();if(!t)throw new Error('This template is not configured in the shared library.');const result=await this.request('/api/excel/blank',{id:t.id});this.resetDraft();this.id=result.id;this.preview=false;this.sheet=null;this.offset=0;this.query='';this.filter='';this.sort='';this.column='0';this.widths.clear();await xlRefresh();await this.expand(true,true);this.message('New blank template created. Historical records were not copied.');return;}
  if(action==='edit'){if(this.preview)await this.action('blank');else await this.expand(true);this.root.querySelector('[data-cell]:not([readonly]),[contenteditable="true"]')?.focus();return;}
  if(action==='expand'){await this.expand(true);this.root.classList.toggle('xl-fullscreen');return;}
  if(action==='download'){await this.expand(true);if(this.preview)throw new Error('Create a new blank template or select a saved file first.');await this.download();return;}
  if(action==='newtab'){window.open('/?excel='+encodeURIComponent(this.id),'_blank','noopener');return;}
  if(action==='save'){await this.save();return;}
  if(action==='undo'||action==='redo'){const from=action==='undo'?this.undo:this.redo,to=action==='undo'?this.redo:this.undo,item=from.pop();if(!item)return;const value=action==='undo'?item.before:item.after;if(value)this.changes.set(item.key,value);else this.changes.delete(item.key);if(this.format==='xlsx')this.touched.set(item.key,value||this.baselines.get(item.key));to.push(item);if(this.format==='docx')this.drawDocument();else{this.drawTable();this.scheduleCalculation();}this.message(`${this.changes.size} unsaved changes`);return;}
  if(action==='reset'){if(this.dirty()&&!confirm('Reset unsaved changes?'))return;this.resetDraft();await this.load();return;}
  if(action==='search'){this.query=$('.xl-search',this.root).value;this.column=$('.xl-column',this.root).value;this.filter=$('.xl-filter',this.root).value;this.offset=0;this.selection=null;await this.loadGrid();return;}
  if(action==='prev'||action==='next'){this.offset=Math.max(0,this.offset+(action==='next'?50:-50));this.selection=null;await this.loadGrid();return;}
  if(action==='add'||action==='delete'){if(this.dirty())throw new Error('Save cell changes before changing rows.');const info=this.meta.sheets.find(s=>s.name===this.sheet),row=Number($('.xl-row',this.root).value)||(action==='add'?info.data_end+1:info.data_end);if(action==='delete'&&!confirm('Delete row '+row+'? Direct references to deleted cells become #REF!.'))return;await this.request('/api/excel/save',{id:this.id,revision:this.book.revision,rows:[{sheet:this.sheet,action:action==='add'?'add':'delete',row}]});this.query='';this.filter='';this.sort='';this.offset=Math.max(0,Math.floor((row-info.header_end-1)/50)*50);await this.load();return;}
  if(action==='assign'){await this.request('/api/excel/assign',{id:this.id,employee:$('.xl-employee',this.root).value,blank:true});await xlRefresh();this.message('Independent blank template assigned.');return;}
  if(action==='permissions'){const body={id:this.id,revision:this.book.revision};this.root.querySelectorAll('[data-permission]').forEach(c=>body[c.dataset.permission]=c.checked);await this.request('/api/excel/permissions',body);await this.load();this.message('Permissions saved.');return;}
  if(action==='history'){const result=await this.request('/api/excel/history?id='+this.id),el=$('.xl-history',this.root);el.innerHTML=result.versions.map(v=>`<div class="xl-version">Version ${v.revision} · ${esc(v.actor)} · ${esc(v.stamp)} <button class="btn" data-version="${v.revision}">Download</button><button class="btn" data-restore="${v.revision}">Restore</button></div>`).join('');el.querySelectorAll('[data-version]').forEach(b=>b.onclick=()=>this.run(()=>this.download(b.dataset.version)));el.querySelectorAll('[data-restore]').forEach(b=>b.onclick=()=>this.run(async()=>{if(this.dirty())throw new Error('Save or reset your draft first.');if(!confirm('Restore as a new version?'))return;await this.request('/api/excel/restore',{id:this.id,revision:this.book.revision,version:Number(b.dataset.restore)});await this.load();}));}
 }
}
window.addEventListener('beforeunload',e=>{if(xlDirty()){e.preventDefault();e.returnValue='';}});
window.addEventListener('focus',()=>{if(S.tab==='excel')for(const p of XL.panels.values())if(p.open&&!p.dirty()&&!p.busy)p.run(()=>p.expand(p.pinned,true));});
document.addEventListener('keydown',e=>{if(e.key==='Escape')for(const p of XL.panels.values())p.root.classList.remove('xl-fullscreen');});
// Live sync: another session saved a newer version of a document this browser can see. Clean panels reload in place;
// a panel with unsaved edits keeps them and says so (its next save is still revision-checked and reports the conflict).
async function xlRemoteChange(m){
 if(!XL.node||XL.user!==S.user)return;
 if(m.actor===S.user)await new Promise(r=>setTimeout(r,1500));   // let this browser's own save/NEFT flow settle first
 const stale=p=>p.alive()&&p.book&&p.book.id===m.id&&p.book.revision<m.revision;
 const known=XL.books.find(b=>b.id===m.id);
 if(![...XL.panels.values()].some(stale)&&known&&known.revision>=m.revision)return;
 try{await xlRefresh();}catch(e){}
 const who=m.actor===S.user?'you in another window':(m.actor||'another user');
 for(const p of XL.panels.values()){
  if(!stale(p))continue;
  p.run(async()=>{
   if(!stale(p))return;
   if(p.dirty()){xlStatus(`${p.title}: version ${m.revision} was saved by ${who}. Your unsaved edits are kept; saving will report a conflict, so reset your draft to load the new version.`,true);return;}
   if(p.open){await p.expand(p.pinned,true);xlStatus(`${p.title} now shows version ${m.revision}, saved by ${who}.`);}
   else{p.grid=null;p.document=null;}
  });
 }
}
