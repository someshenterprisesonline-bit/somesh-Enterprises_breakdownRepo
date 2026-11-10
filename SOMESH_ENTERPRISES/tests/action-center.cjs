const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.TEST_BASE_URL, pin = process.env.TEST_ADMIN_PIN;
const info = JSON.parse(process.env.TEST_FIXTURE_INFO || '{}');
if (!base || !pin) throw new Error('Use python tests/run_browser.py --action-center');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge' });
  const errors = [];
  async function pageFor(mobile = false) {
    const ctx = await browser.newContext({colorScheme:process.env.TEST_THEME || 'light', viewport: mobile ? { width: 390, height: 844 } : { width: 1280, height: 900 }, reducedMotion: 'reduce', isMobile: mobile, hasTouch: mobile });
    await ctx.route('https://fonts.googleapis.com/**', r => r.fulfill({ contentType: 'text/css', body: '' }));
    const page = await ctx.newPage(); page.setDefaultTimeout(15000); page.on('pageerror', e => errors.push(e.message));
    await page.goto(base); await page.locator('[data-login-toggle="admins"]').click();
    await page.locator('[data-user="Admin One"]').click(); await page.locator('#pin').fill(pin); await page.locator('#pin').press('Enter');
    await page.waitForFunction(() => !!S.dash); return page;
  }
  async function action(page) {
    await page.locator('[data-tab="action"]').click(); await page.locator('.sac-metric').first().waitFor();
    await page.waitForFunction(() => !!S.smartAction && !S.sacError);
  }
  const p = await pageFor(); await action(p);
  assert.equal(await p.locator('.sac-metric').count(), 6);
  assert.equal(await p.locator('[data-sac-focus="overdue"] b').first().innerText(), '1');
  assert.equal(await p.locator('[data-sac-focus="approvals"] b').first().innerText(), '1');
  assert.equal(await p.locator('.sac-workload tbody tr').count(), 5);
  await p.locator('.sac-metric[data-sac-focus="overdue"]').click();
  assert.equal(await p.locator('.sac-queue .sac-item').count(), 1);
  assert.ok((await p.locator('.sac-queue').innerText()).includes('Overdue evidence'));
  await p.locator('[data-sac-focus="all"]').click();
  await p.locator('[data-sac-filter="department"]').selectOption('Payroll');
  await p.waitForFunction(() => S.smartAction.people.length === 1 && S.smartAction.people[0].dept === 'Payroll');
  assert.equal(await p.locator('.sac-workload tbody tr').count(), 1);
  await p.locator('[data-sac-filter="department"]').selectOption('');
  await p.waitForFunction(() => S.smartAction.people.length === 5);
  await p.locator('[data-sac-filter="sort"]').selectOption('name');
  await p.waitForFunction(() => S.smartAction.people[0].person === 'Admin One');
  await p.locator('#sacSearch').fill('Review evidence');
  await p.waitForFunction(() => S.smartAction.tasks.length === 1);
  await p.locator('#sacSearch').fill(''); await p.waitForFunction(() => S.smartAction.tasks.length > 1);
  console.log('PASS six counts, underlying-record links, department/search/sort filters and workload');

  const review = p.locator(`[data-sac-task="${info.review}"]`);
  await review.click(); await p.locator('#sacApprove').waitFor();
  assert.ok((await p.locator('#sheet').innerText()).includes('Review evidence'));
  let approvalRequests = 0;
  p.on('request', r => { if (/\/api\/tasks\/\d+\/(approve|reject)$/.test(r.url())) approvalRequests++; });
  await p.locator('#sacApprove').click(); await p.locator('#dlg[open]').waitFor();
  assert.equal(approvalRequests, 0);
  await p.locator('#dlgForm button[value="cancel"]').click(); assert.equal(approvalRequests, 0);
  await p.locator('#sacReturn').click(); await p.locator('#dlgForm textarea').fill('Recheck synthetic totals');
  await p.locator('#dlgForm button[value="ok"]').click();
  await p.waitForFunction(() => S.smartAction.counts.returned === 1);
  assert.equal(approvalRequests, 1);
  await p.locator(`[data-sac-task="${info.review}"]`).click();
  await p.waitForFunction(() => document.querySelector('#sheet.open')?.textContent.includes('Recheck synthetic totals'));
  assert.equal(await p.locator('#sacApprove').count(), 0);
  await p.locator('#shX').click();
  const staff = await p.request.post(base + '/api/login', { data: { user: 'Worker One' } });
  const staffToken = (await staff.json()).token;
  assert.equal((await p.request.post(base + `/api/tasks/${info.review}/submit`, { headers: { 'X-Session': staffToken }, data: { note: 'Corrected totals' } })).status(), 200);
  await p.waitForFunction(() => S.smartAction.counts.approval === 1);
  await p.locator(`[data-sac-task="${info.review}"]`).click(); await p.locator('#sacApprove').click();
  await p.locator('#dlgForm button[value="ok"]').click(); await p.waitForFunction(() => S.smartAction.counts.documents === 1);
  console.log('PASS review sheet, Cancel, explicit confirmed return and approve through original endpoints, SSE queue refresh');

  await p.locator(`[data-sac-task="${info.overdue}"]`).click(); await p.locator('#sacReassign').click();
  await p.locator('#dlgForm select[name="person"]').selectOption('Reviewer');
  const mutation = p.waitForResponse(r => r.url().endsWith('/api/action-center/reassign') && r.request().method() === 'POST');
  await p.locator('#dlgForm button[value="ok"]').click(); assert.equal((await mutation).status(), 200);
  await p.waitForFunction(id => S.smartAction.tasks.find(t => t.id === id).person === 'Reviewer', info.overdue);
  await p.locator(`[data-sac-alerts="${info.overdue}"]`).click(); await p.locator('#acClearTask').waitFor();
  assert.ok(await p.evaluate(id => acData().groups.filter(g => g.task?.id === id).length > 0, info.overdue));
  assert.equal(await p.locator('#alertFeed article').count(), await p.evaluate(id => acData().groups.filter(g => g.task?.id === id).length, info.overdue));
  await p.locator('#acClearTask').click(); await action(p);
  await p.locator('.sac-workload [data-sac-person="Worker One"]').click();
  await p.locator('#trEmployeeModal[open]').waitFor(); assert.equal(await p.locator('#trEmployeeName').innerText(), 'Worker One');
  await p.keyboard.press('Escape'); await action(p);
  for (const fmt of ['xlsx', 'pdf']) {
    await p.locator('.sac-export summary').click(); const download = p.waitForEvent('download');
    await p.locator(`[data-sac-export="${fmt}"]`).click(); const file = await download;
    assert.ok(file.suggestedFilename().endsWith('.' + fmt)); assert.equal(await file.failure(), null);
  }
  await p.locator('#sacDate').fill('2000-01-01'); await p.locator('#sacDate').dispatchEvent('change');
  await p.waitForFunction(() => S.smartAction.date === '2000-01-01');
  assert.equal(await p.locator('[data-sac-focus="completed_today"] b').innerText(), '0');
  assert.equal(await p.evaluate(() => S.smartAction.activity_expected), false);
  console.log('PASS confirmed reassignment, related recipient-scoped alerts, employee Tracker modal, downloads and selected-date counts');

  const mobile = await pageFor(true); await action(mobile);
  assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await mobile.locator('.sac-section').first().locator('summary').tap();
  assert.equal(await mobile.locator('.sac-section').first().getAttribute('open'), null);
  await mobile.locator('#adminIsland').tap(); await mobile.locator('#adminIslandPanel').waitFor();
  assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await mobile.locator('#adminIsland').tap();
  await mobile.locator('.sac-metric[data-sac-focus="overdue"]').tap();
  await mobile.locator(`[data-sac-task="${info.overdue}"]`).tap(); await mobile.locator('#sheet.open').waitFor();
  assert.ok((await mobile.locator('#sheet').boundingBox()).width <= 390);
  await mobile.context().close();
  const token = await p.evaluate(() => S.token);
  assert.equal((await p.request.get(base + '/api/action-center', { headers: { 'X-Session': staffToken } })).status(), 403);
  await p.locator('#logout').click(); assert.equal(await p.locator('[data-tab="action"]').count(), 0);
  assert.equal(await p.evaluate(() => S.smartAction), null);
  assert.deepEqual(errors, []);
  await browser.close();
  console.log('PASS 390px layout/tap/expand, Dynamic Island coexistence, staff denial, logout cleanup and zero JavaScript exceptions');
})().catch(e => { console.error(e); process.exit(1); });
