// Verify Rupashri's real reference templates. Existing workbooks are never edited.
// --show leaves the verified Chrome window open for the user.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const base='http://localhost:8080',show=process.argv.includes('--show');
 const response=await fetch(base+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'Rupashri'})}),session=await response.json();assert.ok(session.token);
 const headers={'X-Session':session.token},before=await(await fetch(base+'/api/excel',{headers})).json();
 const browser=await chromium.launch({headless:!show,channel:'chrome'});let success=false;
 try{
  const ctx=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),p=await ctx.newPage(),errors=[];
  p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)errors.push(r.status()+' '+r.url());});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  await p.addInitScript(token=>localStorage.setItem('se_token',token),session.token);await p.goto(base);await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===3);
  assert.deepEqual(await p.locator('.xl-title h2').allTextContents(),['NEFT SHEET','WORKSHEET','COVERING LETTER']);
  for(const key of ['neft','worksheet','letter']){
   const section=p.locator('[data-section="'+key+'"]');await section.locator('.xl-title').click();
   await p.waitForFunction(key=>!!XL.panels.get(key).meta&&!XL.panels.get(key).busy,key);
   if(key!=='letter')assert.ok((await section.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>v===''));
   else{assert.ok((await section.locator('.xl-word-page').innerText()).includes('[Date]'));assert.ok(await section.locator('.xl-word-image').count()>=1);}
   const existing=before.books.find(b=>b.category===key&&b.origin==='blank');
   if(existing)await section.locator('.xl-file').selectOption(existing.id);
   else await section.locator('[data-xl="blank"]').click();
   await p.waitForFunction(key=>!XL.panels.get(key).preview&&!XL.panels.get(key).busy,key);
   const editable=key==='letter'?section.locator('[contenteditable="true"]').filter({hasText:'Date:'}).first():section.locator('[data-cell="B'+(key==='neft'?'3':'8')+'"]');
   await editable.fill(key==='letter'?'Date: temporary verification':'Temporary verification');p.once('dialog',d=>d.accept());await section.locator('[data-xl="reset"]').click();
   await p.waitForFunction(key=>!XL.panels.get(key).dirty()&&!XL.panels.get(key).busy,key);
   await section.locator('[data-xl="download"]').click();await p.locator('.xl-filename').fill('Verified_'+key);const event=p.waitForEvent('download');await p.locator('[data-download]').click();const dl=await event;assert.equal(dl.suggestedFilename(),'Verified_'+key+'.'+(key==='letter'?'docx':'xlsx'));await dl.saveAs(path.join('data','verified-'+key+'.'+(key==='letter'?'docx':'xlsx')));
   await section.locator('[data-xl="close"]').click();
  }
  const after=await(await fetch(base+'/api/excel',{headers})).json();for(const b of before.books)assert.equal(after.books.find(x=>x.id===b.id).revision,b.revision);
  assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));assert.deepEqual(errors,[]);
  await p.screenshot({path:'data/excel-workspace-redesign.png',fullPage:true});
  await p.locator('[data-section="worksheet"] .xl-title').click();await p.locator('[data-section="worksheet"] .xl-grid').waitFor();
  console.log('PASS live Rupashri Chrome: all 3 real sections, empty previews, blank document creation, editing/reset, original letterhead, custom XLSX/DOCX downloads, existing revisions preserved, zero console errors/failed APIs');success=true;
  if(show){console.log('Chrome remains open on Rupashri Excel Workspace. Close the browser window to end this helper.');await new Promise(resolve=>browser.on('disconnected',resolve));}
 }finally{
  if(!show||!success){await browser.close();await fetch(base+'/api/logout',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:'{}'});}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
