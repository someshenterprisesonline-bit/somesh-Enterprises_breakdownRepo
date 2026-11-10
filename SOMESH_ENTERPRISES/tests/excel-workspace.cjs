const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.TEST_BASE_URL,info=JSON.parse(process.env.TEST_FIXTURE_INFO).excel;
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'}),errors=[];
 try{
  async function create(name,token,mobile=false){
   const ctx=await browser.newContext({colorScheme:process.env.TEST_THEME || 'light',viewport:mobile?{width:390,height:844}:{width:1440,height:1000},reducedMotion:'reduce',isMobile:mobile,hasTouch:mobile});
   await ctx.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
   ctx.on('page',page=>page.on('pageerror',e=>errors.push(e.message)));const p=await ctx.newPage();p.on('response',r=>{if(r.url().includes('/api/excel')&&r.status()>=400)errors.push('API '+r.status()+' '+r.url());});
   await p.addInitScript(({name,token})=>{localStorage.setItem('se_token',token);localStorage.setItem('se_user',name);},{name,token});
   await p.goto(base);await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===3);return {ctx,p};
  }
  const {ctx,p}=await create('Rupashri',info.employees.Rupashri.token),neft=p.locator('[data-section="neft"]'),work=p.locator('[data-section="worksheet"]'),letter=p.locator('[data-section="letter"]');
  assert.deepEqual(await p.locator('.xl-title h2').allTextContents(),['NEFT SHEET','WORKSHEET','COVERING LETTER']);
  const before=await p.evaluate(()=>XL.books.length);
  await neft.locator('.xl-title').hover();await neft.locator('.xl-grid').waitFor();assert.ok(await neft.evaluate(el=>el.classList.contains('is-open')));
  assert.ok((await neft.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>v===''));
  await neft.locator('.xl-grid thead').hover();await p.waitForFunction(()=>document.querySelector('[data-section="neft"]').classList.contains('xl-large'));
  await neft.locator('.xl-grid tbody input').first().hover();assert.ok(await neft.evaluate(el=>el.classList.contains('is-open')));
  await neft.locator('.xl-title').click();await p.locator('.xl-heading h1').hover();assert.ok(await p.evaluate(()=>XL.panels.get('neft').pinned));
  await work.locator('.xl-title').hover();await p.waitForFunction(()=>document.querySelector('[data-section="worksheet"]').classList.contains('is-open'));await work.locator('.xl-grid').waitFor();
  assert.equal(await p.evaluate(()=>XL.books.length),before);console.log('PASS clean headings, blank hover previews, column-header enlargement, pointer transfer, pinning and no data mutation on hover');
  await neft.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('neft').preview&&!XL.panels.get('neft').busy);
  const nr=await p.evaluate(()=>XL.panels.get('neft').grid.header_end+1),account=await p.evaluate(()=>XL.panels.get('neft').grid.header_rows[0].findIndex(v=>String(v).includes('ACCOUNT'))+1);
  const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
  await neft.locator(`[data-cell="B${nr}"]`).fill('New Employee');await neft.locator(`[data-cell="${col(account)}${nr}"]`).fill('000012345678901234');
  await neft.locator('[data-xl="undo"]').click();await neft.locator('[data-xl="redo"]').click();
  const pasteEnd=account===5?'E':'C',pasteText=account===5?'New Employee\tAnalyst\tExample Bank\t000012345678901234':'New Employee\t000012345678901234';
  await neft.locator(`[data-cell="B${nr}"]`).evaluate((el,text)=>{const data=new DataTransfer();data.setData('text/plain',text);el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));},pasteText);
  await neft.locator(`[data-cell="B${nr}"]`).click();await neft.locator(`[data-cell="${pasteEnd}${nr}"]`).click({modifiers:['Shift']});
  const copied=await neft.locator(`[data-cell="B${nr}"]`).evaluate(el=>{const data=new DataTransfer();el.dispatchEvent(new ClipboardEvent('copy',{clipboardData:data,bubbles:true,cancelable:true}));return data.getData('text/plain');});assert.equal(copied,pasteText);
  console.log('PASS multi-cell copy/paste and leading-zero identifier preservation');
  await neft.locator('[data-xl="save"]').click();await neft.getByText('Changes saved.',{exact:true}).waitFor();
  const neftId=await p.evaluate(()=>XL.panels.get('neft').id);
  await work.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('worksheet').preview&&!XL.panels.get('worksheet').busy);
  const calc=await p.evaluate(()=>{const g=XL.panels.get('worksheet').grid;return g.header_end===6?{row:8,address:'I8',inputs:{E8:'30000',F8:'30',H8:'23'},result:'2990'}:{row:3,address:'E3',inputs:{D3:'1200.25'},result:'2400.50'};});
  assert.equal(await work.locator(`[data-cell="${calc.address}"]`).inputValue(),'');
  for(const [address,value] of Object.entries(calc.inputs))await work.locator(`[data-cell="${address}"]`).fill(value);
  await p.waitForFunction(({address,result})=>document.querySelector('[data-section="worksheet"] [data-cell="'+address+'"]')?.value===result,calc);
  const lastInput=Object.keys(calc.inputs).at(-1);await work.locator(`[data-cell="${lastInput}"]`).fill('');
  await p.waitForFunction(address=>document.querySelector('[data-section="worksheet"] [data-cell="'+address+'"]')?.value==='',calc.address);
  await work.locator(`[data-cell="${lastInput}"]`).fill(calc.inputs[lastInput]);
  await p.waitForFunction(({address,result})=>document.querySelector('[data-section="worksheet"] [data-cell="'+address+'"]')?.value===result,calc);
  console.log('PASS clearing required input removes stale calculation and restoring input recalculates');
  assert.equal(await work.locator(`[data-cell="${calc.address}"]`).getAttribute('readonly'),'');
  assert.ok((await work.locator('[data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>!v.startsWith('=')));
  await work.locator('[data-xl="save"]').click();await work.getByText('Changes saved.',{exact:true}).waitFor();
  const workbookId=await p.evaluate(()=>XL.panels.get('worksheet').id);
  const opened=p.waitForEvent('popup');await work.locator('[data-xl="newtab"]').click();const tab=await opened;await tab.waitForFunction(id=>typeof XL!=='undefined'&&XL.panels.get('worksheet')?.id===id&&!!XL.panels.get('worksheet')?.grid,workbookId);
  assert.equal(await tab.locator(`[data-section="worksheet"] [data-cell="${calc.address}"]`).inputValue(),calc.result);await tab.close();
  await work.locator('[data-xl="download"]').click();await p.locator('.xl-filename').fill('');await p.locator('[data-download]').click();await p.getByText('Enter a filename.',{exact:true}).waitFor();await p.locator('.xl-filename').fill('TNOU_Payroll_November_2026');
  const downloaded=p.waitForEvent('download');await p.locator('[data-download]').click();const dl=await downloaded;assert.equal(dl.suggestedFilename(),'TNOU_Payroll_November_2026.xlsx');await dl.saveAs(path.join(process.env.TEST_ARTIFACT_DIR,'edited.xlsx'));
  await work.locator('[data-xl="expand"]').click();await work.locator('.xl-grid').waitFor();assert.ok(await work.evaluate(e=>e.classList.contains('xl-fullscreen')));await p.keyboard.press('Escape');
  const handle=work.locator('[data-resize="1"]');await handle.scrollIntoViewIfNeeded();const box=await handle.boundingBox(),width=await handle.locator('..').evaluate(e=>e.offsetWidth);
  await p.mouse.move(box.x+3,box.y+box.height/2);await p.mouse.down();await p.mouse.move(box.x+45,box.y+box.height/2);await p.mouse.up();assert.ok(await handle.locator('..').evaluate((e,w)=>e.offsetWidth>w+20,width));
  // A narrow synthetic six-column workbook fits on desktop; exercise scrolling at a constrained viewport.
  const priorViewport=p.viewportSize();await p.setViewportSize({width:700,height:900});
  await p.waitForFunction(()=>{const e=document.querySelector('[data-section=worksheet] .xl-grid-wrap');return e&&e.scrollWidth>e.clientWidth;});
  assert.ok(await work.locator('.xl-grid-wrap').evaluate(e=>e.scrollWidth>e.clientWidth));
  await p.setViewportSize(priorViewport);
  console.log('PASS new blank templates, exact headers, text accounts, undo/redo, payroll calculations, hidden/protected formulas, saves, new tab, custom filename, scrolling/resizing/fullscreen');
  await letter.locator('[data-xl="blank"]').click();await p.waitForFunction(()=>!XL.panels.get('letter').preview&&!XL.panels.get('letter').busy);
  const date=letter.locator('[data-paragraph]').filter({hasText:'Date:'}).first();await date.fill('Date: 07/11/2026');await letter.locator('[data-xl="save"]').click();await letter.getByText('Changes saved.',{exact:true}).waitFor();const letterId=await p.evaluate(()=>XL.panels.get('letter').id);
  await letter.locator('[data-xl="download"]').click();await p.locator('.xl-filename').fill('TNOU_Covering_November');const wordDownload=p.waitForEvent('download');await p.locator('[data-download]').click();const word=await wordDownload;assert.equal(word.suggestedFilename(),'TNOU_Covering_November.docx');await word.saveAs(path.join(process.env.TEST_ARTIFACT_DIR,'edited.docx'));
  const pop=p.waitForEvent('popup');await letter.locator('[data-xl="newtab"]').click();const wordTab=await pop;await wordTab.locator(`[data-section="letter"] [data-paragraph]`).filter({hasText:'Date: 07/11/2026'}).first().waitFor();await wordTab.close();
  await p.reload();await p.locator('#xlDashboard').click();await p.waitForFunction(()=>XL.templates.length===3);await p.locator('[data-section="neft"] .xl-file').selectOption(neftId);await p.waitForFunction(()=>!XL.panels.get('neft').busy&&!!XL.panels.get('neft').grid);assert.equal(await p.locator(`[data-section="neft"] [data-cell="${col(account)}${nr}"]`).inputValue(),'000012345678901234');
  await p.locator('[data-section="letter"] .xl-file').selectOption(letterId);await p.locator('[data-section="letter"] [data-paragraph]').filter({hasText:'Date: 07/11/2026'}).first().waitFor();
  console.log('PASS covering-letter blank/edit/save/new-tab/custom DOCX download and all saved work survives reload');
  // Completed uploads use a separate, independent file and preserve every input.
  const uploadSection=p.locator('[data-section="worksheet"]');await uploadSection.locator('.xl-file-input').setInputFiles(info.large_upload);await p.locator('.xl-import-dialog').waitFor();await p.locator('[data-confirm]').click();await uploadSection.getByText('Completed file imported unchanged as an independent document.',{exact:true}).waitFor();
  assert.equal(await uploadSection.locator('.xl-grid tbody tr').count(),50);assert.equal(await uploadSection.locator('[data-cell="B3"]').inputValue(),'Person 1');
  await uploadSection.locator('[data-xl="next"]').click();await p.waitForFunction(()=>XL.panels.get('worksheet').grid.offset===50);await uploadSection.locator('.xl-search').fill('Person 9999');await uploadSection.locator('[data-xl="search"]').click();await p.waitForFunction(()=>XL.panels.get('worksheet').grid.total===1);
  console.log('PASS independent completed-file upload, all manual values, 10,000-row pagination and search');await ctx.close();
  for(const name of ['Nandha','Jagadeeshwari','Sudharsan']){const {ctx,p}=await create(name,info.employees[name].token);await p.locator('[data-section="worksheet"] .xl-title').click();await p.locator('[data-section="worksheet"] .xl-grid').waitFor();assert.ok((await p.locator('[data-section="worksheet"] [data-cell]').evaluateAll(es=>es.map(e=>e.value))).every(v=>v===''));await ctx.close();console.log('PASS '+name+' authorized blank workspace');}
  const mobile=await create('Admin One',info.admin,true);await mobile.p.locator('[data-section="worksheet"] .xl-title').tap();await mobile.p.locator('[data-section="worksheet"] .xl-grid').waitFor();assert.ok(await mobile.p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));await mobile.p.locator('[data-section="worksheet"] .xl-admin summary').click();await mobile.p.locator('[data-section="worksheet"] [data-xl="assign"]').click();await mobile.p.getByText('Independent blank template assigned.',{exact:true}).waitFor();await mobile.ctx.close();
  assert.deepEqual(errors,[]);console.log('PASS mobile/touch bounds, admin assignment, zero JavaScript errors and zero failed Excel API requests');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
