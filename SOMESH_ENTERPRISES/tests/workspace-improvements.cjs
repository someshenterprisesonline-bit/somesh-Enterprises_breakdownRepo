const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict'),path=require('node:path');
const info=process.env.TEST_FIXTURE_INFO?JSON.parse(process.env.TEST_FIXTURE_INFO).excel:null;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const ctx=await browser.newContext({colorScheme:process.env.TEST_THEME||'dark',viewport:{width:1600,height:1000}});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  // --improvements-slow: a slow template-library refresh after each Worksheet save. It used to swallow the
  // New Blank Template click, switch the NEFT panel to the auto-created NEFT and deadlock the two panels.
  const slow=Number(process.env.TEST_SLOW_LIBRARY_MS||0);if(slow)await ctx.route(u=>new URL(u).pathname==='/api/excel',async r=>{const res=await r.fetch();await new Promise(x=>setTimeout(x,slow));await r.fulfill({response:res});});
  const p=await ctx.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));const failedRequests=[];p.on('requestfailed',r=>failedRequests.push(r.url().replace(/^https?:[/][/][^/]+/,'')+' '+(r.failure()?.errorText||'')));
  const user=info?'Rupashri':'Nandha';
  const login=info?null:await ctx.request.post(process.env.TEST_BASE_URL+'/api/login',{data:{user}});
  if(login)assert.equal(login.status(),200);
  const token=info?info.employees.Rupashri.token:(await login.json()).token;
  await p.addInitScript(({token,user})=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user',user);},{token,user});
  await p.goto(process.env.TEST_BASE_URL);await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===3);
  assert.deepEqual(await p.locator('.xl-title h2').allTextContents(),['WORKSHEET','NEFT SHEET','COVERING LETTER']);
  const work=p.locator('[data-section="worksheet"]'),neft=p.locator('[data-section="neft"]');
  await work.locator('.xl-title').click();await work.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('worksheet').preview&&!XL.panels.get('worksheet').busy);
  for(const [a,v] of Object.entries({A7:'1',B7:'Ramesh',C7:'Data Entry Operator',D7:'40000',E7:'50000',F7:'31',H7:'31'}))await work.locator(`[data-cell="${a}"]`).fill(v);
  await p.waitForFunction(()=>document.querySelector('[data-section="worksheet"] [data-cell="S7"]')?.value==='49206').catch(async e=>{console.log(await p.evaluate(()=>{const x=XL.panels.get('worksheet');return {message:x.root.querySelector('.xl-message').textContent,values:[...x.root.querySelectorAll('[data-cell]')].filter(i=>i.dataset.cell.endsWith('7')).map(i=>[i.dataset.cell,i.value]),changes:[...x.changes.values()]};}));throw e;});
  assert.equal(await work.locator('[data-cell="I7"]').getAttribute('readonly'),'');
  assert.equal(await work.locator('[data-cell="I7"]').inputValue(),'6500');
  await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  const worksheet=await p.evaluate(()=>XL.panels.get('worksheet').id);
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'workspace-row7.png')});
  await work.locator('[data-cell="S7"]').scrollIntoViewIfNeeded();
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'workspace-row7-totals.png')});
  await work.locator('[data-cell="A7"]').scrollIntoViewIfNeeded();
  await neft.locator('.xl-title').click();await neft.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('neft').preview&&!XL.panels.get('neft').busy);
  p.once('dialog',d=>d.accept());await neft.locator('[data-neft-target]').selectOption(worksheet);
  await p.waitForFunction(id=>XL.panels.get('neft').grid.neft.target===id&&!XL.panels.get('neft').busy,worksheet);
  for(const [a,v] of Object.entries({A2:'1',H2:'40000',B2:'  rAMESH  '}))await neft.locator(`[data-cell="${a}"]`).fill(v);
  await p.waitForFunction(()=>document.querySelector('[data-section="neft"] [data-cell="C2"]')?.value==='Data Entry Operator');
  await p.waitForFunction(()=>!XL.panels.get('neft').dirty());
  await p.waitForFunction(()=>!XL.panels.get('neft').busy&&!XL.panels.get('worksheet').busy);
  await work.locator('[data-cell="C7"]').fill('Accountant');
  await p.waitForFunction(()=>!XL.panels.get('worksheet').dirty()).catch(async e=>{console.log(await p.evaluate(()=>[...XL.panels].map(([k,p])=>({key:k,state:p.state,busy:p.busy,revision:p.book?.revision,msg:p.root.querySelector('.xl-message').textContent,changes:[...p.changes.values()]}))));throw e;});
  await p.waitForFunction(()=>document.querySelector('[data-section="neft"] [data-cell="C2"]')?.value==='Accountant').catch(async e=>{console.log(await p.evaluate(()=>[...XL.panels].map(([k,x])=>({key:k,id:x.id,preview:x.preview,revision:x.book?.revision,sheet:x.sheet,msg:x.root.querySelector('.xl-message').textContent,c2:x.root.querySelector('[data-cell="C2"]')?.value,neft:x.grid?.neft}))));throw e;});
  await neft.locator('[data-cell="B3"]').fill('Unknown Employee');
  await p.waitForFunction(()=>!XL.panels.get('neft').dirty());
  await p.waitForFunction(()=>document.querySelector('.neft-sync-status')?.textContent.includes('not found'));
  assert.equal(await neft.locator('[data-cell="C3"]').inputValue(),'');
  const bid=await p.evaluate(()=>XL.panels.get('neft').id);
  await p.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'workspace-designations.png')});
  await p.goto(process.env.TEST_BASE_URL+'/?excel='+bid);
  await p.waitForFunction(()=>document.querySelector('[data-section="neft"] [data-cell="C2"]')?.value==='Accountant').catch(async e=>{console.log('FAILED REQUESTS',JSON.stringify(failedRequests));console.log('PROBE',JSON.stringify(await p.evaluate(()=>({url:location.href,user:S.user,tab:S.tab,token:!!S.token,meta:!!S.meta,intro:!!document.getElementById('brandIntro'),login:!!document.querySelector('[data-user]'),app:(document.querySelector('#app')||{}).textContent?.slice(0,160),panels:XL.panels.size,lib:XL.libraryState,xlnode:!!XL.node})).catch(()=>'page not ready')));console.log(await p.evaluate(()=>[...XL.panels].map(([k,x])=>({key:k,id:x.id,preview:x.preview,revision:x.book?.revision,sheet:x.sheet,msg:x.root.querySelector('.xl-message').textContent,c2:x.root.querySelector('[data-cell="C2"]')?.value,neft:x.grid?.neft}))));throw e;});
  assert.deepEqual(await p.locator('.xl-title h2').allTextContents(),['WORKSHEET','NEFT SHEET','COVERING LETTER']);
  assert.deepEqual(errors,[]);console.log('PASS section order; exact row7 payroll/protection/autosave; normalized designation lookup; Worksheet designation update; unknown-name indication; saved reopen; Chrome screenshots');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
