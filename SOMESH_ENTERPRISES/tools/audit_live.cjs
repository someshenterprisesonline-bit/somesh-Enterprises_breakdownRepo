// Read-only live smoke test. Login/logout changes sessions only; no business mutations.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://localhost:8080';
(async () => {
  const health = await (await fetch(base + '/api/health')).json();
  assert.equal(health.database, 'ok'); assert.equal(health.version, '2.0');
  const meta = await (await fetch(base + '/api/meta')).json();
  const admin = meta.users.find(u => u.admin), employee = meta.users.find(u => !u.admin);
  assert.ok(admin && employee);
  const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../backend/config.json'), 'utf8'));
  const sec = config.security || {};
  const pin = String((sec.pins || {})[admin.name] || process.env.SOMESH_ADMIN_PIN || sec.admin_pin || '');
  const browser = await chromium.launch({headless:true, channel:process.env.BROWSER_CHANNEL || 'chrome'});
  const errors = [], serverErrors = [];
  try {
    const context = await browser.newContext({reducedMotion:'reduce', viewport:{width:1440,height:1000}});
    await context.route('https://fonts.googleapis.com/**', r => r.fulfill({contentType:'text/css',body:''}));
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => {if (r.url().startsWith(base + '/api/') && r.status() >= 500) serverErrors.push([r.url(),r.status()]);});
    await page.goto(base);
    await page.locator('#uq').fill(admin.name);
    await page.locator('[data-user]').filter({hasText:admin.name}).first().click();
    await page.locator('#pin').fill(pin); await page.locator('#pinGo').click();
    await page.locator('#addEmployee').waitFor();
    assert.equal(await page.locator('[data-employee-card]').count(), meta.users.length);
    await page.locator('#manageEmployees').click();
    await page.locator('[data-edit-employee]').first().waitFor();
    await page.locator('#addEmployee').click();
    assert.equal(await page.locator('#employeeEditor [name=designation]').count(),1);
    await page.locator('#employeeEditor [data-cancel]').click();
    const names = await page.locator('[data-tab]').evaluateAll(es => es.map(e => e.dataset.tab));
    for (const name of names) {
      await page.locator(`[data-tab="${name}"]`).click();
      await page.waitForFunction(value => S.tab === value, name);
      assert.ok((await page.locator('main').innerText()).length > 0);
    }
    await page.locator('[data-tab=dash]').click(); await page.locator('#addEmployee').waitFor();
    if (await page.locator('html').getAttribute('data-theme') !== 'light') await page.locator('[data-theme-toggle]').click();
    const light = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await page.locator('[data-theme-toggle]').click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    assert.notEqual(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), light);
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({path:path.join(__dirname,'../data/audit-admin-mobile-dark.png'),fullPage:true});
    await page.locator('#logout').click();
    await page.locator('#uq').fill(employee.name);
    await page.locator('[data-user]').filter({hasText:employee.name}).first().click();
    await page.locator('#logout').waitFor();
    assert.equal(await page.locator('#addEmployee,#manageEmployees,#manageAdmins').count(),0);
    const denied = await page.evaluate(async () => {
      const statuses = [];
      for (const endpoint of ['/api/employees','/api/admins','/api/dashboard','/api/pipeline']) statuses.push((await fetch(endpoint,{headers:hdrs()})).status);
      statuses.push((await fetch('/api/employees',{method:'POST',headers:hdrs(),body:JSON.stringify({action:'add'})})).status);
      return statuses;
    });
    assert.deepEqual(denied,[403,403,403,403,403]);
    await page.reload(); await page.locator('#logout').waitFor();
    await page.locator('#logout').click();
    assert.deepEqual(errors,[]); assert.deepEqual(serverErrors,[]);
    await context.close();
    console.log('PASS live localhost: SQLite health, Admin login/cards/forms/navigation, Employee login/session refresh/API denial, mobile/dark UI, no JavaScript exceptions or server errors; no business records changed');
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exitCode=1;});
