const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const info=JSON.parse(process.env.TEST_FIXTURE_INFO).neft, base=process.env.TEST_BASE_URL;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'}),errors=[];
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:process.env.TEST_THEME||'light'});
  await context.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));
  p.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=500)errors.push(r.status()+' '+r.url());});
  await p.addInitScript(({token,theme})=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user','Nandha');localStorage.setItem('se_theme_user_Nandha',theme);}, {token:info.token,theme:process.env.TEST_THEME||'light'});
  await p.goto(base);await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===2);
  const n=p.locator('[data-section="neft"]'),w=p.locator('[data-section="worksheet"]');
  await w.locator('.xl-title').click();await w.locator('.xl-grid').waitFor();
  await n.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('neft').preview&&!XL.panels.get('neft').busy);
  const rows=Array.from({length:10},(_,i)=>[[10,2,1][i]||i+1,'Person '+String(10-i).padStart(3,'0'),i%2?'Cleaner':'Guard','Bank '+i,'0000'+i,'Branch '+i,'IFSC'+i,1000+i,'Note '+i]);
  await n.locator('[data-cell="A2"]').evaluate((el,text)=>{const d=new DataTransfer();d.setData('text/plain',text);el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:d,bubbles:true,cancelable:true}));},rows.map(r=>r.join('\t')).join('\n'));
  async function settled(){await p.waitForFunction(()=>{const n=XL.panels.get('neft'),w=XL.panels.get('worksheet');return !n.busy&&!n.dirty()&&n.grid?.neft?.status==='synced'&&!w.busy&&w.id===n.grid.neft.target&&w.book?.revision===n.grid.neft.target_revision&&!!w.grid;});}
  await settled();
  assert.equal(await w.locator('[data-cell="B2"]').inputValue(),'Person 010');assert.equal(await w.locator('[data-cell="D2"]').inputValue(),'1000');
  const original=await p.evaluate(()=>XL.panels.get('neft').id),firstTarget=await p.evaluate(()=>XL.panels.get('worksheet').id);
  console.log('PASS browser paste 10 manual records, autosave and immediate Worksheet mapping including editable salary');
  await w.locator('[data-cell="E2"]').fill('777');await w.locator('[data-cell="G2"]').fill('Keep payroll note');
  async function sort(col,dir){await n.locator('[data-neft-column]').selectOption(String(col));await p.waitForFunction(()=>!XL.panels.get('neft').busy);await n.locator('[data-neft-direction]').selectOption(dir);await settled();}
  await sort(2,'asc');
  assert.equal(await w.locator('[data-cell="E11"]').inputValue(),'777');assert.equal(await w.locator('[data-cell="G11"]').inputValue(),'Keep payroll note');
  await w.locator('[data-xl="save"]').click();await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty()&&!XL.panels.get('worksheet').busy);
  async function values(key){return p.evaluate(key=>XL.panels.get(key).grid.rows.filter(r=>r.cells[1].value).map(r=>r.cells.map(c=>c.value)),key);}
  for(const [col,dir] of [[2,'asc'],[2,'desc'],[3,'asc'],[3,'desc'],[1,'asc'],[1,'desc'],[0,'original']]){
   await sort(col,dir);const nr=await values('neft'),wr=await values('worksheet');assert.deepEqual(nr.map(r=>r.slice(0,3)),wr.map(r=>r.slice(0,3)));
   for(const r of nr){const originalRow=rows.find(o=>o[1]===r[1]);assert.deepEqual(r.slice(0,9).map(String),originalRow.map(String));}
   const expected=col?rows.slice().sort((a,b)=>{const x=a[col-1],y=b[col-1],c=col===1?x-y:String(x).localeCompare(String(y));return dir==='desc'?-c:c;}):rows;
   assert.deepEqual(nr.map(r=>r[1]),expected.map(r=>r[1]));
  }
  console.log('PASS all six sorts and Original Order; complete bank/salary rows, linked order and unsaved Worksheet payroll fields preserved');
  await n.locator('[data-cell="B2"]').fill('Renamed Person');await settled();assert.equal(await w.locator('[data-cell="B2"]').inputValue(),'Renamed Person');
  await n.locator('[data-xl="undo"]').click();await settled();assert.equal(await w.locator('[data-cell="B2"]').inputValue(),'Person 010');
  await sort(2,'asc');await p.reload();await p.locator('#xlDashboard').click();await n.locator('.xl-file').selectOption(original);await n.locator('.xl-grid').waitFor();await p.waitForFunction(()=>!XL.panels.get('neft').busy);
  assert.equal(await n.locator('[data-neft-column]').inputValue(),'2');assert.equal(await n.locator('[data-neft-direction]').inputValue(),'asc');
  await n.locator('[data-neft-open]').click();await settled();assert.equal(await w.locator('[data-cell="G11"]').inputValue(),'Keep payroll note');
  console.log('PASS edit, undo after autosave, refresh/reopen, persisted sort and saved Worksheet-only data');
  await sort(0,'original');await n.locator('.xl-more summary').click();await n.locator('.xl-row').fill('12');await n.locator('[data-xl="add"]').click();await p.waitForFunction(()=>!XL.panels.get('neft').busy);
  await n.locator('[data-cell="B12"]').fill('Added Employee');await n.locator('[data-cell="C12"]').fill('Analyst');await settled();assert.equal(await w.locator('[data-cell="B12"]').inputValue(),'Added Employee');
  await n.locator('.xl-more summary').click();await n.locator('.xl-row').fill('12');p.once('dialog',d=>d.accept());await n.locator('[data-xl="delete"]').click();await settled();assert.ok(!(await values('worksheet')).some(r=>r[1]==='Added Employee'));
  console.log('PASS browser add/delete NEFT row with deletion confirmation and automatic Worksheet update');
  await n.locator('.xl-file-input').setInputFiles(info.upload);await p.locator('.xl-import-dialog [data-confirm]').click();await settled();
  const uploaded=await p.evaluate(()=>XL.panels.get('neft').id);assert.notEqual(uploaded,original);assert.notEqual(await p.evaluate(()=>XL.panels.get('worksheet').id),firstTarget);
  assert.equal(await w.locator('[data-cell="B2"]').inputValue(),'Employee 100');
  const counts=await p.evaluate(async()=>{const n=XL.panels.get('neft'),w=XL.panels.get('worksheet');const a=await n.request('/api/excel/sheet?id='+n.id+'&sheet=NEFT&limit=100'),b=await w.request('/api/excel/sheet?id='+w.id+'&sheet=Worksheet&limit=100');return [a.rows.filter(r=>r.cells[1].value).length,b.rows.filter(r=>r.cells[1].value).length];});assert.deepEqual(counts,[100,100]);
  await sort(2,'asc');assert.equal(await w.locator('[data-cell="B2"]').inputValue(),'Employee 001');
  for(const [panel,name] of [[n,'neft-browser.xlsx'],[w,'worksheet-browser.xlsx']]){await panel.locator('[data-xl="download"]').click();await p.locator('.xl-filename').fill(name);const event=p.waitForEvent('download');await p.locator('[data-download]').click();await (await event).saveAs(path.join(process.env.TEST_ARTIFACT_DIR,name));}
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'neft-'+(process.env.TEST_THEME||'light')+'.png'),fullPage:true});
  assert.equal(await p.evaluate(()=>document.documentElement.dataset.theme),process.env.TEST_THEME||'light');
  await p.setViewportSize({width:390,height:844});assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'neft-mobile-'+(process.env.TEST_THEME||'light')+'.png'),fullPage:true});await p.setViewportSize({width:1440,height:1000});
  const adminLogin=await context.request.post(base+'/api/login',{data:{user:'Admin One',pin:process.env.TEST_ADMIN_PIN}}),adminToken=(await adminLogin.json()).token;
  const targetId=await p.evaluate(()=>XL.panels.get('worksheet').id);
  async function lockTarget(locked){const meta=await (await context.request.get(base+'/api/excel/metadata?id='+targetId,{headers:{'X-Session':adminToken}})).json();const r=await context.request.post(base+'/api/excel/permissions',{headers:{'X-Session':adminToken},data:{id:targetId,revision:meta.book.revision,locked}});assert.equal(r.status(),200);}
  await lockTarget(true);
  const editedAddress=await p.evaluate(()=>XL.panels.get('neft').grid.rows[0].cells[1].address);
  await n.locator('[data-cell="'+editedAddress+'"]').fill('Source name retained');
  await p.waitForFunction(()=>XL.panels.get('neft').grid.neft.status==='error');
  assert.match(await n.locator('.neft-sync-status').innerText(),/Sync failed|Mapping conflict/);
  await lockTarget(false);await n.locator('[data-neft-retry]').click();await settled();
  assert.ok(await p.evaluate(async()=>{const w=XL.panels.get('worksheet');const all=await w.request('/api/excel/sheet?id='+w.id+'&sheet=Worksheet&limit=100');return all.rows.some(r=>r.cells[1].value==='Source name retained');}));
  console.log('PASS responsive controls, visible sync failure protecting a locked target, retained source save and successful Retry sync');
  const other=await browser.newContext({viewport:{width:1440,height:1000}}),q=await other.newPage();
  await q.addInitScript(token=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user','Rupashri');},info.other_token);
  await q.goto(base);await q.locator('#xlDashboard').click();await q.waitForFunction(()=>XL.templates.length===2);
  const otherN=q.locator('[data-section="neft"]');await otherN.locator('.xl-file-input').setInputFiles(info.upload);await q.locator('.xl-import-dialog [data-confirm]').click();
  await q.waitForFunction(()=>XL.panels.get('neft').grid?.neft?.status==='synced'&&!XL.panels.get('neft').busy);
  const ownTarget=await q.evaluate(()=>XL.panels.get('neft').grid.neft.target);assert.notEqual(ownTarget,firstTarget);
  assert.equal(await q.evaluate(async id=>(await fetch('/api/excel/download?id='+id,{headers:{'X-Session':localStorage.getItem('se_token')}})).status,firstTarget),403);
  await other.close();console.log('PASS second employee upload has an independent linked Worksheet; direct access to the first employee document returns 403');
  assert.deepEqual(errors,[]);console.log('PASS 100-row Excel upload, separate document pairing, uploaded sorting, both browser downloads, theme screenshot and no page/API 5xx errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
