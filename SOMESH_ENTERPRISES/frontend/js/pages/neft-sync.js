// NEFT row ordering and one-way, same-owner Worksheet synchronization.
"use strict";
const NeftSync = {
  enabled(p) { return p.key === 'neft' && !p.preview && !!p.grid?.neft; },
  status(p, text, error = false) {
    const node = p.root.querySelector('.neft-sync-status');
    if (node) { node.textContent = text; node.classList.toggle('neft-sync-error', error); }
  },
  render(p) {
    if (!this.enabled(p)) return;
    const state = p.grid.neft, host = p.root.querySelector('.xl-editor');
    host.querySelector('.neft-controls')?.remove();
    const choices = XL.books.filter(b => b.owner === p.book.owner && b.category === 'worksheet' && !b.master);
    const control = document.createElement('div'); control.className = 'neft-controls';
    control.innerHTML = `<label>Sort NEFT by<select class="in" data-neft-column aria-label="Sort NEFT by">${[[0,'Original entry / upload order'],[1,'S.No (numeric)'],[2,'Name'],[3,'Designation']].map(([n,label])=>`<option value="${n}" ${state.column===n?'selected':''}>${label}</option>`).join('')}</select></label><label>Order<select class="in" data-neft-direction aria-label="NEFT sort direction"><option value="original" ${!state.column?'selected':''}>Original Order</option><option value="asc" ${state.column&&state.direction==='asc'?'selected':''}>Ascending (A–Z / smallest first)</option><option value="desc" ${state.column&&state.direction==='desc'?'selected':''}>Descending (Z–A / largest first)</option></select></label><label>Linked Worksheet<select class="in" data-neft-target aria-label="Linked Worksheet"><option value="new">New separate Worksheet</option>${choices.map(b=>`<option value="${b.id}" ${state.target===b.id?'selected':''}>${esc(b.name)}</option>`).join('')}</select></label><div class="actions"><button class="btn" type="button" data-neft-open ${state.target?'':'disabled'}>Open linked Worksheet</button><button class="btn" type="button" data-neft-retry>Retry sync</button><button class="btn" type="button" data-neft-designations>Use Worksheet designations</button></div><p class="neft-sync-status" role="status" aria-live="polite"></p><small class="muted neft-sync-note"></small>`;
    host.querySelector('.xl-editor-bar').after(control);
    const col = control.querySelector('[data-neft-column]'), direction = control.querySelector('[data-neft-direction]');
    col.onchange = () => { if (col.value !== '0' && direction.value === 'original') direction.value = 'asc'; p.run(() => this.command(p, {action:'sort',column:Number(col.value),direction:col.value==='0'?'original':direction.value})); };
    direction.onchange = () => { if (direction.value !== 'original' && col.value === '0') col.value = '1'; p.run(() => this.command(p,{action:'sort',column:Number(col.value),direction:direction.value})); };
    control.querySelector('[data-neft-target]').onchange = e => {
      const target = e.target.value;
      if (!confirm('Link this NEFT table to this Worksheet? Existing manual values and formulas are protected. The old linked file and all versions remain available.')) { e.target.value=state.target||'new'; return; }
      p.run(() => this.command(p,{action:'sync',target}));
    };
    control.querySelector('[data-neft-designations]').onclick = () => {if(confirm('Replace NEFT designations with unambiguous Worksheet matches? Unmatched manual values will be preserved.'))p.run(()=>this.command(p,{action:'designations'}));};
    control.querySelector('[data-neft-retry]').onclick = () => p.run(() => this.command(p,{action:'retry'}));
    control.querySelector('[data-neft-open]').onclick = () => p.run(() => this.open(p));
    const labels = ['S.No','Name','Designation'];
    p.root.querySelectorAll('[data-sort]').forEach(button => {
      const n = Number(button.dataset.sort); if (n > 3) return;
      button.textContent = `${labels[n-1]} ${state.column===n?(state.direction==='desc'?'↓':'↑'):'↕'}`;
      button.parentElement.setAttribute('aria-sort',state.column===n?(state.direction==='desc'?'descending':'ascending'):'none');
      button.onclick = () => p.run(() => this.command(p,{action:'sort',column:n,direction:state.column===n?(state.direction==='asc'?'desc':'original'):'asc'}));
    });
    this.paint(p);
  },
  paint(p) {
    const state = p.grid?.neft; if (!state) return;
    this.status(p,xlSyncText(state),state.status==='error');
    const warnings=(state.designation_notes||[]).map(n=>`Row ${n.row}: ${n.status==='ambiguous'?'ambiguous employee designation':n.status==='blank'?'Worksheet designation is blank':'employee name not found in Worksheet'}`).join('; ');
    if(warnings)this.status(p,xlSyncText(state)+'. '+warnings);
    const note = p.root.querySelector('.neft-sync-note');
    if (note) note.textContent = `${state.salary_note||'S.No, Name and Designation synchronize automatically.'} NEFT edits auto-save after a short pause. Original versions are retained.`;
  },
  async command(p, action) {
    if (p.dirty()) await p.save();
    this.status(p,'Synchronizing Worksheet…');
    try {
      const result = await p.request('/api/excel/neft',{id:p.id,revision:p.book.revision,sheet:p.sheet,...action});
      p.sort=''; p.offset=0; p.selection=null;
      await p.load(); await this.after(p,result.neft_sync);
    } catch (e) { this.status(p,'Worksheet sync failed: '+e.message,true); throw e; }
  },
  async open(p) {
    const target = XL.panels.get('worksheet'), id = p.grid?.neft?.target; if (!target || !id) return;
    if (target.id !== id && target.dirty()) throw new Error('Save or reset the open Worksheet draft before switching documents.');
    if (target.id !== id) { target.resetDraft(); target.id=id; target.preview=false; target.sheet=null; target.grid=null; }
    await target.expand(true,!target.dirty()); target.options(); target.root.scrollIntoView({block:'start',behavior:'smooth'});
  },
  async after(p, state) {
    if (!p.alive()) return;
    if (state?.source_sheet && state.source_sheet !== p.sheet) state=(await p.request('/api/excel/metadata?id='+p.id)).neft_sheets?.[p.sheet];
    if (state) p.grid.neft=state;
    for(const update of state?.designation_values||[]){
      if(p.changes.has(p.sheet+'!'+update.address))continue;
      for(const row of p.grid.rows){const cell=row.cells.find(c=>c.address===update.address);if(cell)cell.value=update.value;}
      const input=p.root.querySelector(`[data-cell="${update.address}"]`);if(input)input.value=update.value;
    }
    this.paint(p);
    await xlRefresh(); if (!p.alive() || !p.grid?.neft?.target) return;
    state=p.grid.neft;
    const target=XL.panels.get('worksheet'); if (!target) return;
    if (target.preview && !target.dirty()) { target.id=state.target; target.preview=false; target.sheet=null; target.grid=null; target.options(); }
    if (target.id !== state.target || state.status !== 'synced') return;
    if (target.open && (target.book?.id !== state.target || target.book?.revision !== state.target_revision || !target.grid)) {
      // Queue the Worksheet reload; do not wait for it. This runs inside the NEFT panel's queue, and a Worksheet save
      // running at the same moment waits for the NEFT queue (xlWorksheetSynced): awaiting here deadlocked both panels.
      target.run(async()=>{
        if (target.dirty()) await this.rebaseDraft(target);
        else await target.load();
      });
    }
  },
  async rebaseDraft(target) {
    // Unsaved Worksheet-only fields follow row UUIDs across a NEFT reorder.
    const meta=await target.request('/api/excel/metadata?id='+target.id), moved=new Map(meta.employee_rows.map(r=>[r.row_id,r]));
    const rebased=new Map(), keyMap=new Map();
    for (const [key,patch] of target.changes) {
      const row=moved.get(patch.row_id);
      if (!row || row.sheet!==patch.sheet) throw new Error('Worksheet draft retained: an employee row changed or was removed. Review the draft before refreshing.');
      if (/^[ABC][0-9]+$/.test(patch.address)) throw new Error('Worksheet draft retained: save mapped employee fields before synchronizing again.');
      const address=patch.address.replace(/[0-9]+$/,String(row.position)),nextKey=patch.sheet+'!'+address;
      rebased.set(nextKey,{...patch,address}); keyMap.set(key,nextKey);
    }
    const undo=target.undo,redo=target.redo,oldChanges=target.changes;
    target.changes=new Map();
    try { await target.load(); }
    catch(e) { target.changes=oldChanges; throw e; }
    target.changes=rebased;target.touched=new Map(rebased);
    const shift=item=>{const k=keyMap.get(item.key);if(!k)return item;const address=k.split('!').pop();return {...item,key:k,before:item.before?{...item.before,address}:null,after:item.after?{...item.after,address}:null};};
    target.undo=undo.map(shift);target.redo=redo.map(shift);target.drawTable();target.message('Worksheet Synced; your unsaved payroll fields were preserved.');
  },
  schedule(p) {
    if (!this.enabled(p)) return;
    clearTimeout(p.neftSaveTimer);
    p.neftSaveTimer=setTimeout(()=>{if(p.alive()&&p.dirty())p.run(()=>p.save(true));},900);
  },
  async save(p, automatic=false) {
    clearTimeout(p.neftSaveTimer);clearTimeout(p.calcTimer);p.calcSequence++;
    if (!p.dirty()) {if(!automatic)p.message('Changes saved.');return;}
    // IFSC / account number checks: Save Changes shows the VALIDATION ERROR dialog; autosave quietly keeps invalid or
    // incomplete bank cells in the draft (still highlighted) and saves every other edit.
    const problems=p.bankChangeProblems([...p.changes.values()],{required:true});
    if(problems.length&&!automatic){await p.showValidation(problems[0]);return;}
    const held=new Set(problems.map(x=>x.key)),snapshot=new Map([...p.changes].filter(([k])=>!held.has(k)));if(!snapshot.size)return;
    this.status(p,'Saving NEFT and synchronizing Worksheet…');
    try {
      const result=await p.request('/api/excel/save',{id:p.id,revision:p.book.revision,changes:[...snapshot.values()]});
      p.book.revision=result.revision;
      for (const [key,patch] of snapshot) {
        if(patch.sheet===p.sheet)for (const row of p.grid.rows) { const cell=row.cells.find(c=>c.address===patch.address);if(cell)cell.value=patch.value; }
        if(p.changes.get(key)?.value===patch.value){p.changes.delete(key);p.touched.delete(key);}
      }
      if(!automatic){p.undo=[];p.redo=[];p.baselines.clear();await p.load();}
      else if(!p.root.contains(document.activeElement)&&!p.dirty())await p.load();
      else p.neftNeedsReload=true;
      await this.after(p,result.neft_sync);
      p.root.querySelectorAll('.xl-modified').forEach(el=>{const input=el.querySelector('[data-cell]');if(input&&!p.changes.has(p.sheet+'!'+input.dataset.cell))el.classList.remove('xl-modified');});
      if(!p.dirty())p.message(automatic?'NEFT saved automatically.':'Changes saved.');
    } catch(e){
      if(e.validation){this.status(p,'NEFT not saved: '+e.message,true);await p.showValidation(e.validation);return;}  // nothing saved; the draft is kept
      this.status(p,'NEFT save / Worksheet sync failed: '+e.message,true);throw e;
    }
  }
};

const neftOriginal={action:ExcelSection.prototype.action,drawEditor:ExcelSection.prototype.drawEditor,drawTable:ExcelSection.prototype.drawTable,edited:ExcelSection.prototype.edited,setCell:ExcelSection.prototype.setCell,save:ExcelSection.prototype.save,loadGrid:ExcelSection.prototype.loadGrid,upload:ExcelSection.prototype.upload,dispose:ExcelSection.prototype.dispose,resetDraft:ExcelSection.prototype.resetDraft};
ExcelSection.prototype.drawEditor=function(){neftOriginal.drawEditor.call(this);NeftSync.render(this);};
ExcelSection.prototype.drawTable=function(){neftOriginal.drawTable.call(this);if(this.grid?.neft&&this.root.querySelector('.neft-controls'))NeftSync.render(this);};
ExcelSection.prototype.setCell=function(cell,value){
  const key=this.sheet+'!'+cell.address,old=this.changes.get(key)?.value??cell.value;
  neftOriginal.setCell.call(this,cell,value);
  const row=this.grid.rows.find(r=>r.cells.some(c=>c.address===cell.address)),patch=this.changes.get(key);
  if(patch)patch.row_id=row?.row_id;
  if(NeftSync.enabled(this)){
    const item=this.undo[this.undo.length-1];item.before={sheet:this.sheet,address:cell.address,value:old,type:cell.type,row_id:row?.row_id};
    item.after={sheet:this.sheet,address:cell.address,value,type:cell.type,row_id:row?.row_id};
  }
};
ExcelSection.prototype.edited=function(){neftOriginal.edited.call(this);NeftSync.schedule(this);};
ExcelSection.prototype.save=function(automatic=false){return NeftSync.enabled(this)?NeftSync.save(this,automatic):neftOriginal.save.call(this,automatic);};
ExcelSection.prototype.loadGrid=async function(){
  const previousTarget=this.grid?.neft?.target;
  await neftOriginal.loadGrid.call(this);
  if(NeftSync.enabled(this)){
    const target=XL.panels.get('worksheet'),next=this.grid.neft.target;
    if(previousTarget&&next&&next!==previousTarget&&target?.id===previousTarget&&!target.dirty()){
      target.id=next;target.preview=false;target.sheet=null;target.grid=null;
    }
    await NeftSync.after(this,this.grid.neft);
  }
};
ExcelSection.prototype.upload=async function(file){await neftOriginal.upload.call(this,file);if(NeftSync.enabled(this))await NeftSync.after(this,this.grid.neft);};
ExcelSection.prototype.resetDraft=function(){clearTimeout(this.neftSaveTimer);this.neftNeedsReload=false;return neftOriginal.resetDraft.call(this);};
ExcelSection.prototype.dispose=function(){clearTimeout(this.neftSaveTimer);return neftOriginal.dispose.call(this);};
document.addEventListener('focusout',event=>{
  const source=XL.panels.get('neft');if(!source?.neftNeedsReload||!source.root.contains(event.target))return;
  setTimeout(()=>{if(source.alive()&&!source.root.contains(document.activeElement)&&!source.dirty()&&!source.busy){source.neftNeedsReload=false;source.run(()=>source.load());}},50);
});

ExcelSection.prototype.action=async function(action){await neftOriginal.action.call(this,action);if(action==='undo'||action==='redo')NeftSync.schedule(this);};

function xlSyncText(state){
 if(!state)return 'No employee records available';
 if(state.status==='error')return (String(state.error).toLowerCase().includes('conflict')?'Mapping conflict - Review required: ':'Sync failed - Retry: ')+state.error;
 if(state.status==='synced'&&Number(state.records)>0)return `Synced - ${state.records} employee records saved`;
 if(state.status==='empty'||!Number(state.records))return 'No employee records available';
 return 'Syncing...';
}
async function xlWorksheetSynced(panel,state){
 if(!state||!panel.alive())return;
 panel.message(xlSyncText(state),state.status==='error');
 const target=XL.panels.get('neft'),shown=target&&{id:target.id,preview:target.preview};
 await xlRefresh();
 if(!state.neft||!target||state.status==='error')return;
 // The user opened another NEFT document (for example New Blank Template) while this sync was in flight:
 // keep what they chose instead of switching the panel to the linked NEFT behind their back.
 if(target.id!==shown.id||target.preview!==shown.preview)return;
 if(target.dirty()){target.message('Worksheet changes are saved. Your NEFT draft is retained; save/reset it before loading the synchronized revision.',true);return;}
 if(target.preview||target.id!==state.neft){target.resetDraft();target.id=state.neft;target.preview=false;target.sheet=state.sheet;target.grid=null;target.options();}
 if(target.id===state.neft){
  if(target.open)target.run(()=>target.load());   // queued, not awaited: see NeftSync.after (two panels must never wait on each other)
  else target.grid=null;
 }
}
