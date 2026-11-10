// Read-only live verification: switch real profiles in Chrome and preview shared references.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='http://localhost:8080',names=['Nandha','Jagadeeshwari','Sudharsan','Rupashri'],categories=['neft','worksheet','letter'];
(async()=>{
 const show=process.argv.includes('--show'),browser=await chromium.launch({headless:!show,channel:'chrome'});let success=false;
 try{
  const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),p=await ctx.newPage(),errors=[],failed=[],results=[];let masterIds;
  p.setDefaultTimeout(20000);p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)failed.push(r.status()+' '+r.url());});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));await p.goto(base);
  for(const name of names){
   if(await p.locator('#logout').count())await p.locator('#logout').click();
   await p.locator('#uq').fill(name);await p.locator(`[data-user="${name}"]`).click();await p.locator('#xlDashboard').click();
   await p.waitForFunction(()=>XL.libraryState==='ready'&&XL.templates.length===3);
   const snapshot=await p.evaluate(()=>({user:S.user,templates:XL.templates,books:XL.books.map(b=>({id:b.id,revision:b.revision,owner:b.owner}))}));
   assert.equal(snapshot.user,name);assert.ok(snapshot.books.every(b=>b.owner===name));
   const ids=Object.fromEntries(snapshot.templates.map(t=>[t.category,t.id]));if(masterIds)assert.deepEqual(ids,masterIds);else masterIds=ids;
   const row={employee:name,templates:{},private_files:snapshot.books.length};
   for(const category of categories){
    const root=p.locator(`[data-section="${category}"]`);await root.locator('.xl-title').hover();
    await p.waitForFunction(k=>XL.panels.get(k)?.state==='ready'&&!XL.panels.get(k).busy&&XL.panels.get(k).root.classList.contains('is-open'),category);
    assert.equal(await root.locator('[data-xl="blank"]').isEnabled(),true);
    if(category==='letter'){
     assert.ok((await root.locator('.xl-word-page').innerText()).includes('[Date]'));assert.ok(await root.locator('.xl-word-image').count()>0);await root.locator('.xl-word-page').hover();
    }else{
     assert.ok((await root.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>v===''));
     const sheets=await root.locator('.xl-sheet option').allTextContents();assert.deepEqual(sheets,category==='neft'?['Office Copy','Net Banking Copy','TNOU','In']:['TNOU','In']);
     await root.locator('.xl-grid thead').hover();assert.ok(await root.evaluate(e=>e.classList.contains('xl-large')));await root.locator('.xl-grid tbody input').first().hover();
    }
    assert.ok(await root.evaluate(e=>e.classList.contains('is-open')));await root.locator('.xl-title').click();assert.ok(await p.evaluate(k=>XL.panels.get(k).pinned,category));
    row.templates[category]={shared_master:ids[category],preview:'passed',blank_creation_available:true,pinning:'passed'};
   }
   await p.waitForFunction(()=>XL.controllers.size===0&&[...XL.panels.values()].every(p=>p.state==='ready'&&!p.busy));
   assert.equal(await p.getByText('No template assigned',{exact:false}).count(),0);
   const after=await p.evaluate(()=>XL.books.map(b=>({id:b.id,revision:b.revision,owner:b.owner})));assert.deepEqual(after,snapshot.books);
   await p.mouse.move(5,5);
   for(const category of categories){const button=p.locator(`[data-section="${category}"] [data-xl="close"]`);await button.focus();await button.press('Enter');}
   await p.screenshot({path:'data/shared-templates-'+name+'.png',fullPage:true});results.push(row);console.log('PASS live '+name+': three shared blank previews, worksheet structure, header hover, pointer transfer, pinning, private saved files unchanged');
  }
  assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);assert.equal(new Set(Object.values(masterIds)).size,3);
  fs.writeFileSync('data/employee-template-live-checks.json',JSON.stringify({url:base,results,console_errors:errors,failed_api_requests:failed,shared_master_count:3},null,2));success=true;
  console.log('PASS live Chrome: switched all four profiles; exactly three shared masters, no writes or duplicate files, zero console errors/failed APIs');
  if(show){console.log('Chrome remains open on Rupashri Excel Workspace. Close the window to finish this helper.');await new Promise(resolve=>browser.on('disconnected',resolve));}
 }finally{if(!show||!success)await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
