// Starts from a shared library ONLY. No pre-assigned employee document copies.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const base=process.env.TEST_BASE_URL,info=JSON.parse(process.env.TEST_FIXTURE_INFO).excel;
const names=['Nandha','Jagadeeshwari','Sudharsan','Rupashri'],categories=['neft','worksheet','letter'];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'}),errors=[],badResponses=[];
 try{
  async function context(mobile=false,faults=false){
   const ctx=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},reducedMotion:'reduce',isMobile:mobile,hasTouch:mobile});
   await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
   ctx.on('page',page=>{
    page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));
    if(!faults)page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400)badResponses.push(r.status()+' '+r.url());});
   });return ctx;
  }
  async function signIn(p,name){
   if(await p.locator('#logout').count())await p.locator('#logout').click();
   await p.locator('#uq').fill(name);await p.locator(`[data-user="${name}"]`).click();
   await p.locator('#xlDashboard').waitFor();await p.locator('#xlDashboard').click();
  }
  async function ready(p){await p.waitForFunction(()=>XL.libraryState==='ready'&&XL.templates.length===3);}
  async function sectionReady(p,category){await p.waitForFunction(k=>XL.panels.get(k)?.state==='ready'&&!XL.panels.get(k)?.busy&&XL.panels.get(k).root.classList.contains('is-open'),category).catch(async e=>{console.log('SECTION DEBUG',category,await p.evaluate(()=>[...XL.panels].map(([key,x])=>({key,state:x.state,open:x.open,busy:x.busy,message:x.root.querySelector('.xl-message').textContent,hover:x.root.matches(':hover'),rect:x.root.getBoundingClientRect().toJSON()}))));throw e;});}
  const created={};
  for(const name of names){
   const ctx=await context(),p=await ctx.newPage();await p.goto(base);await signIn(p,name);await ready(p);
   assert.equal(await p.evaluate(()=>XL.books.length),0);
   assert.deepEqual(await p.evaluate(()=>Object.fromEntries(XL.templates.map(t=>[t.category,t.id]))),info.masters);
   assert.deepEqual(await p.locator('.xl-title h2').allTextContents(),['WORKSHEET','NEFT SHEET','COVERING LETTER']);
   created[name]={};
   for(const category of categories){
    const root=p.locator(`[data-section="${category}"]`);await root.locator('.xl-title').hover();await sectionReady(p,category);
    assert.ok(await root.evaluate(e=>e.classList.contains('is-open')));
    if(category!=='letter'){
     const autoLinked=category==='worksheet'&&await p.evaluate(()=>!XL.panels.get('worksheet').preview&&!!XL.panels.get('neft').grid?.neft?.target);
     if(autoLinked)assert.ok((await root.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).some(v=>v===name+' neft saved in new tab'));
     else assert.ok((await root.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>v===''));
     await root.locator('.xl-grid thead').hover();assert.ok(await root.evaluate(e=>e.classList.contains('xl-large')));
     await root.locator('.xl-grid tbody input').first().hover();assert.ok(await root.evaluate(e=>e.classList.contains('is-open')));
    }else{
     const text=await root.locator('.xl-word-page').innerText();assert.ok(text.includes('[Date]'));assert.ok(!text.includes('12,29,773'));
     await root.locator('.xl-word-page').hover();assert.ok(await root.evaluate(e=>e.classList.contains('is-open')));
    }
    await root.locator('.xl-title').click();await p.locator('.xl-heading h1').hover();await p.waitForTimeout(300);assert.ok(await root.evaluate(e=>e.classList.contains('is-open')));
    await root.locator('[data-xl="blank"]').click();await p.waitForFunction(k=>!XL.panels.get(k).preview&&XL.panels.get(k).state==='ready'&&!XL.panels.get(k).busy,category);
    const bid=await p.evaluate(k=>XL.panels.get(k).id,category);created[name][category]=bid;
    let field;
    if(category==='letter')field=root.locator('[contenteditable="true"]').filter({hasText:'Date:'}).first();
    else{
     const row=await p.evaluate(k=>{const g=XL.panels.get(k).grid;return (g.rows.find(r=>r.cells.some(c=>c.formula))||g.rows[0]).number;},category);
     field=root.locator(`[data-cell="B${row}"]`);
    }
    const marker=name+' '+category;await field.fill(marker);await root.locator('[data-xl="save"]').click();await root.getByText('Changes saved.',{exact:true}).waitFor();
    const popup=p.waitForEvent('popup');await root.locator('[data-xl="newtab"]').click();const tab=await popup;
    await tab.waitForFunction(({category,bid})=>typeof XL!=='undefined'&&XL.panels.get(category)?.id===bid&&XL.panels.get(category)?.state==='ready',{category,bid});
    const tabRoot=tab.locator(`[data-section="${category}"]`);
    const tabField=category==='letter'?tabRoot.locator('[contenteditable="true"]').filter({hasText:marker}).first():tabRoot.locator('[data-cell]');
    let editor;
    if(category==='letter')editor=tabField;
    else{
     const address=await tab.evaluate(({category,marker})=>XL.panels.get(category).grid.rows.flatMap(r=>r.cells).find(c=>c.value===marker).address,{category,marker});editor=tabRoot.locator(`[data-cell="${address}"]`);
    }
    await editor.fill(marker+' saved in new tab');await tabRoot.locator('[data-xl="save"]').click();await tabRoot.getByText('Changes saved.',{exact:true}).waitFor();await tab.close();
    await p.locator('.xl-heading [data-xl="refresh"]').click();await sectionReady(p,category);
    await p.waitForFunction(({category,marker})=>{const panel=XL.panels.get(category);return panel.format==='docx'?panel.root.innerText.includes(marker):panel.grid?.rows.some(r=>r.cells.some(c=>c.value===marker));},{category,marker:marker+' saved in new tab'});
    await root.locator('[data-xl="download"]').click();await p.locator('.xl-filename').fill(name+'_'+category+'_November');const event=p.waitForEvent('download');await p.locator('[data-download]').click();const dl=await event,ext=category==='letter'?'docx':'xlsx';
    assert.equal(dl.suggestedFilename(),name+'_'+category+'_November.'+ext);await dl.saveAs(path.join(process.env.TEST_ARTIFACT_DIR,name+'-'+category+'.'+ext));
    await root.locator('[data-xl="close"]').focus();await root.locator('[data-xl="close"]').press('Enter');
   }
   // Reopen every saved file after a real reload.
   await p.reload();await p.locator('#xlDashboard').click();await ready(p);
   for(const category of categories){const root=p.locator(`[data-section="${category}"]`);await root.locator('.xl-file').selectOption(created[name][category]);await sectionReady(p,category);assert.ok((await root.innerText()).includes('saved in new tab')||await root.locator('[data-cell]').evaluateAll(es=>es.some(e=>e.value.includes('saved in new tab'))));await root.locator('[data-xl="close"]').focus();await root.locator('[data-xl="close"]').press('Enter');}
   // Upload one independent completed file into each section; verify exact bytes.
   const token=await p.evaluate(()=>S.token);
   for(const category of categories){
    const root=p.locator(`[data-section="${category}"]`),file=category==='letter'?info.letter_upload:info.completed_upload;
    await root.locator('.xl-file-input').setInputFiles(file);await p.locator('.xl-import-dialog').waitFor();await p.locator('[data-confirm]').click();await root.getByText('Completed file imported unchanged as an independent document.',{exact:true}).waitFor();
    const bid=await p.evaluate(k=>XL.panels.get(k).id,category),response=await ctx.request.get(base+'/api/excel/download?id='+bid,{headers:{'X-Session':token}});assert.equal(response.status(),200);assert.ok((await response.body()).equals(fs.readFileSync(file)));
    if(category!=='letter'){assert.equal(await root.locator('[data-cell="B3"]').inputValue(),'Person 1');assert.ok(await p.evaluate(k=>XL.panels.get(k).grid.rows[0].cells.some(c=>c.formula),category));}
    await root.locator('[data-xl="close"]').focus();await root.locator('[data-xl="close"]').press('Enter');
   }
   const listing=await p.evaluate(()=>({books:XL.books,templates:XL.templates,loading:[...XL.panels.values()].some(p=>p.state==='loading')}));assert.ok(listing.books.every(b=>b.owner===name));assert.equal(listing.templates.length,3);assert.equal(listing.loading,false);
   for(const [owner,books] of Object.entries(created))if(owner!==name)for(const bid of Object.values(books)){const r=await ctx.request.get(base+'/api/excel/download?id='+bid,{headers:{'X-Session':token}});assert.equal(r.status(),403);}
   await ctx.close();console.log('PASS '+name+': all three shared previews, heading/header hover, pin, blank creation, edit/save, new-tab save, custom download, reload, exact-byte completed uploads and private-file isolation');
  }
  assert.equal(new Set(Object.values(created).flatMap(Object.values)).size,12);
  // Fault injection is separated from the zero-failed-request normal journeys.
  {
   const ctx=await context(false,true),p=await ctx.newPage();let fail=true;
   const handler=r=>fail?r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Injected library outage'})}):r.continue();await ctx.route('**/api/excel',handler);
   await p.goto(base);await signIn(p,'Sudharsan');await p.waitForFunction(()=>XL.libraryState==='error');
   assert.equal(await p.getByText('No template assigned',{exact:false}).count(),0);assert.ok((await p.locator('.xl-status').innerText()).includes('Injected library outage'));assert.equal(await p.locator('[data-load-state="loading"]').count(),0);
   fail=false;await p.locator('[data-xl="retrylibrary"]').click();await ready(p);await p.locator('[data-section="neft"] .xl-title').click();await sectionReady(p,'neft');await ctx.close();
   console.log('PASS catalog failure reports an error rather than a missing assignment; Retry restores previews');
  }
  {
   const ctx=await context(false,true),p=await ctx.newPage();await p.goto(base);await signIn(p,'Sudharsan');await ready(p);await p.evaluate(()=>XL.requestTimeout=350);
   let release;const handler=async r=>{await new Promise(resolve=>release=resolve);await r.abort().catch(()=>{});};await ctx.route('**/api/excel/metadata?**',handler);
   await p.locator('[data-section="neft"] .xl-title').click();await p.waitForFunction(()=>XL.panels.get('neft').state==='error'&&!XL.panels.get('neft').busy);
   assert.ok((await p.locator('[data-section="neft"] .xl-message').innerText()).includes('timed out'));assert.equal(await p.locator('[data-section="neft"]').getAttribute('aria-busy'),'false');
   await ctx.unroute('**/api/excel/metadata?**',handler);release();await p.evaluate(()=>XL.requestTimeout=20000);await p.locator('[data-section="neft"] [data-xl="retry"]').click();await sectionReady(p,'neft');await ctx.close();
   console.log('PASS a stalled preview times out, leaves loading state and retries successfully');
  }
  for(const target of ['catalog','preview']){
   const ctx=await context(false,true),p=await ctx.newPage();await p.goto(base);
   if(target==='preview'){await signIn(p,'Nandha');await ready(p);}else{await p.locator('#uq').fill('Nandha');await p.locator('[data-user="Nandha"]').click();await p.locator('#xlDashboard').waitFor();}
   const old=await p.evaluate(()=>S.token);let release,held=false;
   const pattern=target==='catalog'?'**/api/excel':'**/api/excel/metadata?**';
   const handler=async r=>{if(r.request().headers()['x-session']!==old){await r.continue();return;}held=true;await new Promise(resolve=>release=resolve);await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({books:[],templates:[{id:'STALE_OLD_PROFILE',category:'neft',name:'STALE'}]})}).catch(()=>{});};await ctx.route(pattern,handler);
   if(target==='catalog')await p.locator('#xlDashboard').click();else await p.locator('[data-section="neft"] .xl-title').click();
   await p.waitForFunction(()=>XL.controllers.size>0);assert.ok(held);
   await signIn(p,'Jagadeeshwari');await ready(p);release();await ctx.unroute(pattern,handler);
   await p.waitForFunction(()=>XL.controllers.size===0);assert.equal(await p.evaluate(()=>XL.user),'Jagadeeshwari');assert.deepEqual(await p.evaluate(()=>Object.fromEntries(XL.templates.map(t=>[t.category,t.id]))),info.masters);
   for(const category of categories){await p.locator(`[data-section="${category}"] .xl-title`).click();await sectionReady(p,category);}
   assert.equal(await p.getByText('STALE',{exact:false}).count(),0);await ctx.close();console.log('PASS switching profiles during a pending '+target+' request cancels/ignores the old response');
  }
  {
   const ctx=await context(true),p=await ctx.newPage();await p.goto(base);await signIn(p,'Sudharsan');await ready(p);
   for(const category of categories){await p.locator(`[data-section="${category}"] .xl-title`).tap();await sectionReady(p,category);assert.ok(await p.locator(`[data-section="${category}"]`).evaluate(e=>e.classList.contains('is-open')));await p.locator(`[data-section="${category}"] [data-xl="close"]`).tap();}
   assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));await ctx.close();console.log('PASS Sudharsan touch expansion for all three sections and viewport bounds');
  }
  assert.deepEqual(errors,[]);assert.deepEqual(badResponses,[]);console.log('PASS no console exceptions or failed API requests in all normal employee journeys');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
