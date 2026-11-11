const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const info=JSON.parse(process.env.TEST_FIXTURE_INFO).excel;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
 try{
  const ctx=await browser.newContext({colorScheme:process.env.TEST_THEME||'dark',viewport:{width:1600,height:1000}});
  await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({token})=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user','Rupashri');},{token:info.employees.Rupashri.token});
  await page.goto(process.env.TEST_BASE_URL);await page.locator('#xlDashboard').click();
  await page.waitForFunction(()=>XL.templates.length===3);
  const work=page.locator('[data-section="worksheet"]');await work.locator('.xl-title').click();await work.locator('[data-xl="blank"]').click();
  await page.waitForFunction(()=>!XL.panels.get('worksheet').preview&&!XL.panels.get('worksheet').busy);
  for(const [a,v] of Object.entries({D9:'23250',E9:'20000',F9:'31',H9:'25'}))await work.locator(`[data-cell="${a}"]`).fill(v);
  await page.waitForFunction(()=>document.querySelector('[data-section="worksheet"] [data-cell="S9"]').value==='22772');
  assert.equal(await work.locator('[data-cell="S9"]').getAttribute('readonly'),'');
  await page.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  const bid=await page.evaluate(()=>XL.panels.get('worksheet').id);
  await page.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'formula-tnou.png')});
  await page.goto(process.env.TEST_BASE_URL+'/?excel='+bid);
  await page.waitForFunction(()=>document.querySelector('[data-section="worksheet"] [data-cell="S9"]')?.value==='22772');
  await work.locator('[data-cell="H9"]').fill('31');await page.waitForFunction(()=>document.querySelector('[data-cell="S9"]').value==='28237');
  await page.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  await work.locator('[data-xl="undo"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-section="worksheet"] [data-cell="S9"]').value==='22772');
  await page.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  await work.locator('[data-xl="redo"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-section="worksheet"] [data-cell="S9"]').value==='28237');
  await page.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  await page.evaluate(async()=>{const p=XL.panels.get('worksheet');p.sheet='In';p.offset=0;await p.loadGrid();});
  await work.locator('[data-cell="F9"]').fill('3100');await work.locator('[data-cell="E9"]').fill('25');
  await page.waitForFunction(()=>document.querySelector('[data-cell="G9"]')?.value==='2500.00');
  await page.waitForFunction(()=>!XL.panels.get('worksheet').dirty());
  await page.screenshot({path:path.join(process.env.TEST_ARTIFACT_DIR,'formula-invoice.png')});
  assert.deepEqual(errors,[]);console.log('PASS TNOU manual entry, protected results, automatic save, refresh, present-day edit, undo/redo after autosave, In invoice recalculation; screenshots captured');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
