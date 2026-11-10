const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync}=require('node:child_process');
const base = process.env.TEST_BASE_URL;
const output = path.resolve('data/theme-audit');
fs.mkdirSync(output, {recursive:true});
(async () => {
  const browser = await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL || 'chrome'});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    await context.route('https://fonts.googleapis.com/**',r=>r.fulfill({contentType:'text/css',body:''}));
    const cache=new Map();
    if(!process.env.THEME_CAPTURE_CURRENT) await context.route(base+'/**',async route=>{
      const u=new URL(route.request().url());
      if(u.pathname==='/'||u.pathname.startsWith('/static/')){
        const rel=u.pathname==='/'?'index.html':u.pathname.slice(8),file='SOMESH_ENTERPRISES/frontend/'+rel;
        if(!cache.has(file))cache.set(file,execFileSync('git',['show',(process.env.THEME_BASE_REF||'HEAD')+':'+file],{cwd:path.resolve('..')}));
        return route.fulfill({body:cache.get(file),contentType:rel.endsWith('.js')?'application/javascript':rel.endsWith('.css')?'text/css':rel.endsWith('.html')?'text/html':'application/octet-stream'});
      }
      return route.continue();
    });
    const page = await context.newPage();
    const label=process.env.THEME_CAPTURE_CURRENT?'comparison-after':'before';
    for (const mode of ['light','dark']) {
      await page.emulateMedia({colorScheme:mode}); await page.goto(base);
      await page.locator('[data-login-toggle=employees]').click();
      await page.waitForFunction(()=>(()=>{const e=document.querySelector('#login-employees');return e.getBoundingClientRect().height>100&&e.getBoundingClientRect().height>=e.firstElementChild.scrollHeight-1;})());
      await page.screenshot({path:path.join(output,`${label}-${mode}-login.png`),fullPage:true,animations:'disabled'});
      await page.locator('[data-login-toggle=admins]').click();
      await page.locator('[data-user="Admin One"]').click();
      await page.locator('#pin').fill(process.env.TEST_ADMIN_PIN); await page.locator('#pinGo').click();
      await page.waitForFunction(()=>S.tab==='dash'&&!!S.dash);
      await page.screenshot({path:path.join(output,`${label}-${mode}-dashboard.png`),fullPage:true,animations:'disabled'});
      await page.locator('#adminIsland').hover(); await page.locator('#adminIslandPanel').waitFor();
      await page.screenshot({path:path.join(output,`${label}-${mode}-island.png`)});
      await page.keyboard.press('Escape');
      await page.locator('[data-tab=alerts]').click(); await page.locator('.ac-card').first().waitFor();
      await page.screenshot({path:path.join(output,`${label}-${mode}-alerts.png`),fullPage:true,animations:'disabled'});
      await page.locator('#logout').click();
    }
    console.log('Captured 8 comparison screenshots in data/theme-audit');
    await context.close();
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
