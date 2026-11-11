const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict'),path=require('node:path');
const base=process.env.TEST_BASE_URL;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const ctx=await browser.newContext({colorScheme:process.env.TEST_THEME||'dark',viewport:{width:1600,height:1100}});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  const p=await ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(base);await p.locator('[data-login-toggle="admins"]').waitFor();
  const meta=await (await ctx.request.get(base+'/api/meta')).json();
  assert.equal(await p.locator('[data-user]').count(),meta.users.length);
  assert.equal(await p.locator('[data-login-group="admins"] [data-user]').count(),meta.users.filter(u=>u.admin).length);
  assert.match(await p.locator('.runtime-notice').textContent(),/not the office/);
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'critical-login.png')});
  const failedContext=await browser.newContext();await failedContext.route('**/api/meta',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Profile store unavailable'})}));
  const failedPage=await failedContext.newPage();await failedPage.goto(base);await failedPage.getByText(/Unable to load user profiles/).waitFor();assert.equal(await failedPage.locator('[data-user]').count(),0);await failedContext.close();
  await p.locator('[data-login-toggle="admins"]').click();await p.locator('[data-user="Admin One"]').click();await p.locator('#pin').fill(process.env.TEST_ADMIN_PIN);await p.locator('#pinGo').click();await p.waitForFunction(()=>S.user==='Admin One'&&S.tab==='dash');
  await p.evaluate(()=>logout());await p.locator('[data-login-toggle="employees"]').click();await p.locator('[data-user="Nandha"]').click();await p.waitForFunction(()=>S.user==='Nandha');
  await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===3);
  const work=p.locator('[data-section="worksheet"]'),neft=p.locator('[data-section="neft"]');
  await work.locator('.xl-title').click();await work.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('worksheet').busy&&!XL.panels.get('worksheet').preview);
  for(const [a,v] of Object.entries({A7:'2',B7:'wqe',C7:'ew',D7:'2323',E7:'2323',F7:'23',H7:'21',A8:'3',B8:'ew',C8:'we',D8:'2323',E8:'2323',F8:'32',H8:'21'}))await work.locator(`[data-cell="${a}"]`).fill(v);
  await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty()&&!XL.panels.get('worksheet').busy&&XL.panels.get('neft').id&&!XL.panels.get('neft').preview);
  await neft.locator('.xl-title').click();await neft.locator('[data-cell="B2"]').waitFor();
  await p.waitForFunction(()=>document.querySelector('[data-section="neft"] [data-cell="B2"]')?.value==='wqe');
  assert.equal(await neft.locator('[data-cell="B3"]').inputValue(),'ew');assert.equal(Number(await neft.locator('[data-cell="H2"]').inputValue()),1590.75);
  assert.match(await neft.locator('.neft-sync-status').textContent(),/Synced.*2 employee records/);
  await neft.locator('[data-cell="E2"]').fill('001234567');await neft.locator('[data-cell="D2"]').fill('Bank preserved');await p.waitForFunction(()=>!XL.panels.get('neft').dirty()&&!XL.panels.get('neft').busy);
  const correctNeft=await p.evaluate(()=>XL.panels.get('neft').id);
  await p.evaluate(async()=>{const n=XL.panels.get('neft');const master=XL.templates.find(t=>t.category==='neft');const other=await n.request('/api/excel/blank',{id:master.id});n.resetDraft();n.id=other.id;n.preview=false;n.sheet=null;n.grid=null;await n.load();});
  await work.locator('[data-cell="C7"]').fill('Updated designation');await work.locator('[data-cell="D7"]').fill('4000');
  await p.waitForFunction(()=>document.querySelector('[data-section="neft"] [data-cell="C2"]')?.value==='Updated designation');
  assert.equal(await p.evaluate(()=>XL.panels.get('neft').id),correctNeft);
  assert.equal(await neft.locator('[data-cell="E2"]').inputValue(),'001234567');assert.equal(await work.locator('[data-cell="D7"]').inputValue(),'4000');
  for(const direction of ['asc','desc']){
   await neft.locator('[data-neft-column]').selectOption('2');await p.waitForFunction(()=>!XL.panels.get('neft').busy);
   await neft.locator('[data-neft-direction]').selectOption(direction);await p.waitForFunction(()=>!XL.panels.get('neft').busy);
   const record=await p.evaluate(()=>XL.panels.get('neft').grid.rows.find(r=>r.cells[1].value==='wqe').cells.map(c=>c.value));assert.equal(record[4],'001234567');
  }
  const ids=await p.evaluate(()=>({work:XL.panels.get('worksheet').id,neft:XL.panels.get('neft').id,revision:XL.panels.get('neft').book.revision,token:S.token}));
  const adminResponse=await ctx.request.post(base+'/api/login',{data:{user:'Admin One',pin:process.env.TEST_ADMIN_PIN}}),admin=(await adminResponse.json()).token;
  async function lockNeft(locked){const m=await(await ctx.request.get(base+'/api/excel/metadata?id='+ids.neft,{headers:{'X-Session':admin}})).json();const result=await ctx.request.post(base+'/api/excel/permissions',{headers:{'X-Session':admin},data:{id:ids.neft,revision:m.book.revision,locked}});assert.equal(result.status(),200);}
  await lockNeft(true);await work.locator('[data-cell="D7"]').fill('4500');
  await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty()&&!XL.panels.get('worksheet').busy);
  assert.match(await work.locator('.xl-message').textContent(),/Sync failed/);
  await lockNeft(false);await work.locator('[data-xl="retryworksheet"]').click();
  await p.waitForFunction(()=>!XL.panels.get('worksheet').busy&&XL.panels.get('neft').grid?.neft?.status==='synced');
  assert.match(await work.locator('.xl-message').textContent(),/Synced.*2 employee records/);
  // A second browser's old revision cannot overwrite a newly synchronized salary.
  const ctx2=await browser.newContext();await ctx2.addInitScript(({token})=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user','Nandha');},{token:ids.token});const p2=await ctx2.newPage();await p2.goto(base+'/?excel='+ids.neft);await p2.waitForFunction(()=>!!XL.panels.get('neft').grid);
  const stale=await p2.evaluate(()=>XL.panels.get('neft').book.revision);
  await work.locator('[data-cell="D7"]').fill('5000');await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty()&&!XL.panels.get('worksheet').busy);
  const staleResponse=await ctx2.request.post(base+'/api/excel/save',{headers:{'X-Session':ids.token},data:{id:ids.neft,revision:stale,changes:[{sheet:'NEFT',address:'E2',value:'stale bank data',type:'text'}]}});if(staleResponse.status()!==400)console.log('RACE DEBUG',await p.evaluate(()=>({message:XL.panels.get('worksheet').root.querySelector('.xl-message').textContent,work:XL.panels.get('worksheet').book.revision,neft:XL.panels.get('neft').book.revision,dirty:XL.panels.get('worksheet').dirty()})),{stale});assert.equal(staleResponse.status(),400);await ctx2.close();
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'critical-sync.png'),fullPage:true});
  await p.goto(base+'/?excel='+ids.neft);await p.waitForFunction(()=>XL.panels.get('neft')?.grid?.rows.some(r=>r.cells[1].value==='wqe'&&r.cells[4].value==='001234567'));
  assert.deepEqual(errors,[]);console.log('PASS authoritative login groups, Admin/employee navigation, environment warning and unavailable-profile error, two-row Worksheet -> NEFT autosave, payable mapping, designation update, bank-safe sorting, failed-target recovery and Retry sync, two-session revision conflict and saved reopen');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
