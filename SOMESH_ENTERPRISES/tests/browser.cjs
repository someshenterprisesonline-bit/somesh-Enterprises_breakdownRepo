// Synthetic integration fixtures are created by run_browser.py; no installed app credentials.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const base = process.env.TEST_BASE_URL, pin = process.env.TEST_ADMIN_PIN;
const info = JSON.parse(process.env.TEST_FIXTURE_INFO || '{}');
if (!base || !pin) throw new Error('Run with python tests/run_browser.py');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_CHANNEL || process.platform === 'win32' ? { channel: process.env.BROWSER_CHANNEL || 'msedge' } : {}) });
  const errors = [];
  async function pageFor(options = {}) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce', ...options });
    await context.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', error => errors.push(error.message));
    return page;
  }
  async function selectAdmin(page) {
    await page.goto(base);
    await page.locator('[data-login-toggle="admins"]').click();
    await page.locator('[data-user="Admin One"]').click();
    await page.locator('#pin').waitFor();
  }
  async function login(page, click = false) {
    await selectAdmin(page);
    await page.locator('#pin').fill(pin);
    if (click) await page.locator('#pinGo').click(); else await page.locator('#pin').press('Enter');
    await page.waitForFunction(() => S.tab === 'dash' && !!S.dash && !!S.alertCenter);
    assert.equal(await page.locator('#dlg[open]').count(), 0);
  }
  async function tab(page, name) {
    await page.locator(`[data-tab="${name}"]`).click();
    await page.waitForFunction(value => S.tab === value, name);
  }
  const p = await pageFor();
  await p.goto(base);
  assert.equal(await p.locator('.login-group.is-open').count(), 0);
  assert.equal(await p.getByText('Monthly Cycle · pick your name to see your tasks and alerts.', { exact: true }).count(), 0);
  await p.locator('[data-login-toggle="admins"]').click();
  assert.equal(await p.locator('.login-group.is-open').count(), 1);
  assert.equal(await p.locator('.login-group.is-open [data-user]').count(), 2);
  await p.locator('[data-login-toggle="employees"]').click();
  assert.equal(await p.locator('.login-group.is-open').count(), 1);
  assert.equal(await p.locator('.login-group.is-open [data-user]').count(), 3);
  await p.locator('#uq').fill('Worker One');
  assert.equal(await p.locator('.login-group.is-open [data-user]').count(), 1);
  await p.locator('#uq').fill('');
  await login(p);
  console.log('PASS collapsed login groups, exclusive expansion, search, Enter login and Dashboard');

  const mouseLogin = await pageFor(); await login(mouseLogin, true);
  await mouseLogin.reload();
  await mouseLogin.waitForFunction(() => S.tab === 'dash' && !!S.dash);
  await mouseLogin.context().close();
  const retry = await pageFor(); await selectAdmin(retry);
  await retry.locator('#pin').fill('incorrect-test-value'); await retry.locator('#pin').press('Enter');
  await retry.getByText('Incorrect PIN. Please try again.', { exact: true }).waitFor();
  assert.equal(await retry.locator('#dlg[open]').count(), 1);
  let attempts = 0;
  await retry.route('**/api/login', async route => { attempts++; await new Promise(r => setTimeout(r, 350)); await route.continue(); });
  await retry.locator('#pin').fill(pin);
  await retry.locator('#pin').press('Enter'); await retry.keyboard.press('Enter'); await retry.keyboard.press('Enter');
  await retry.waitForFunction(() => !!S.dash); assert.equal(attempts, 1);
  await retry.context().close();
  const cancel = await pageFor(); let cancelledRequests = 0;
  cancel.on('request', r => { if (r.url().endsWith('/api/login')) cancelledRequests++; });
  await selectAdmin(cancel); await cancel.locator('#pinCancel').click();
  assert.equal(await cancel.locator('#dlg[open]').count(), 0); assert.equal(cancelledRequests, 0);
  await cancel.context().close();
  const unavailable = await pageFor(); await selectAdmin(unavailable);
  await unavailable.route('**/api/login', route => route.abort('connectionfailed'));
  await unavailable.locator('#pin').fill(pin); await unavailable.locator('#pinGo').click();
  await unavailable.getByText('Could not connect to the server. Please try again.', { exact: true }).waitFor();
  await unavailable.context().close();
  await p.bringToFront();
  console.log('PASS mouse login, refresh session, wrong PIN, one request for repeated Enter, Cancel and connection error');

  await p.locator('#manageAdmins').click(); await p.locator('#adminManagerRows [data-admin-user]').first().waitFor();
  await p.locator('#adminSearch').fill('Worker One');
  assert.equal(await p.locator('#adminManagerRows tbody tr').count(), 1);
  for (const label of ['Make Admin', 'Revoke Admin']) {
    await p.locator('[data-admin-user="Worker One"]').filter({ hasText: label }).click();
    await p.locator('[name="confirmation_pin"]').fill(pin);
    await p.locator('#dlgForm button.primary').click();
    await p.locator('[data-admin-user="Worker One"]').filter({ hasText: label === 'Make Admin' ? 'Revoke Admin' : 'Make Admin' }).waitFor();
  }
  await p.locator('#adminManagerClose').click();
  console.log('PASS searched role management, confirmation, promotion and revocation');

  await tab(p, 'tracker'); await p.locator('[data-tr-person="Worker One"]').waitFor();
  const card = p.locator('[data-tr-person="Worker One"]'), toggle = p.locator('#trTaskToggle');
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  await card.hover(); await p.locator('#trEmployeePreview').waitFor();
  assert.ok((await p.locator('#trEmployeePreview').innerText()).includes('Review evidence'));
  assert.ok(!(await p.locator('#trEmployeePreview').innerText()).includes('Running payroll'));
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  await card.click(); await p.locator('#trEmployeeModal[open]').waitFor();
  assert.deepEqual(await p.locator('#trEmployeeModal th').allTextContents(), ['Person', 'Task', 'Started', 'Done', 'Approved', 'Ended', 'Worked', 'Status', 'Docs']);
  await p.keyboard.press('Escape'); await p.locator('#trEmployeeModal').waitFor({ state: 'detached' });
  await p.locator('[data-tr-person="Worker Two"]').click();
  assert.equal(await p.locator('#trEmployeeName').innerText(), 'Worker Two');
  assert.ok((await p.locator('#trEmployeeModal').innerText()).includes('Running payroll'));
  await p.locator('#trEmployeeClose').click(); await p.mouse.move(4, 880);
  await p.locator('#trEmployeePreview').waitFor({ state: 'detached' });
  await toggle.hover(); await p.waitForFunction(() => S.trTableHover);
  await p.locator('#trTaskBody tbody tr').first().hover();
  await p.mouse.move(4, 880); await p.waitForTimeout(380);
  assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
  await toggle.click(); await p.mouse.move(4, 880); await p.waitForTimeout(380);
  assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
  await p.locator('#tq').fill('Running payroll');
  assert.equal(await p.locator('#trTaskBody tbody tr').count(), 1);
  await p.locator('[data-sort="worked"]').click(); await p.locator('#tq').fill('');
  const timer = p.locator('[data-tr-person="Worker Two"] .timer').first(), beforeTime = await timer.innerText();
  await p.waitForFunction(previous => document.querySelector('[data-tr-person="Worker Two"] .timer').textContent !== previous, beforeTime);
  for (const format of ['xlsx', 'pdf']) {
    await p.locator('.tr-export summary').click();
    const download = p.waitForEvent('download'); await p.locator(`[data-tr-export="${format}"]`).click();
    const file = await download; assert.match(file.suggestedFilename(), new RegExp(`Tracker_.*\\.${format}$`));
    await file.saveAs(path.join(process.env.TEST_ARTIFACT_DIR, `browser.${format}`));
    assert.equal(await file.failure(), null);
  }
  await p.locator('#tDate').fill('2000-01-01'); await p.locator('#tDate').dispatchEvent('change');
  await p.waitForFunction(() => S.tr?.date === '2000-01-01');
  assert.equal(await p.locator('[data-tr-person]').count(), 0);
  const selectedDate = await p.evaluate(() => today());
  await p.locator('#tDate').fill(selectedDate); await p.locator('#tDate').dispatchEvent('change');
  await p.waitForFunction(() => S.tr?.date === today());
  console.log('PASS employee-scoped previews/modal, hover dismissal, collapsed/pinned table, sorting/search, live timer, Excel/PDF downloads and date');

  const island = p.locator('#adminIsland'), panel = p.locator('#adminIslandPanel');
  const islandBox = await island.boundingBox(); assert.ok(Math.abs(islandBox.x + islandBox.width / 2 - 640) < 1);
  let taskRequests = 0;
  p.on('request', r => { if (/\/api\/alerts\/\d+\/task/.test(r.url())) taskRequests++; });
  await island.hover(); await panel.waitFor();
  await panel.locator('.ac-island-title').first().click(); assert.equal(taskRequests, 0);
  const expand = panel.locator('[data-ac-expand]');
  await expand.nth(0).click(); await expand.nth(1).click();
  assert.equal(await expand.nth(0).getAttribute('aria-expanded'), 'true');
  assert.equal(await expand.nth(1).getAttribute('aria-expanded'), 'true');
  await expand.nth(0).click(); await expand.nth(1).click();
  const order = () => panel.locator('.ac-island-card').evaluateAll(es => es.map(e => e.dataset.acGroup));
  const oldOrder = await order(), handle = await panel.locator('[data-ac-drag]').first().boundingBox();
  const target = await panel.locator('.ac-island-card').nth(1).boundingBox();
  await p.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2); await p.mouse.down();
  await p.mouse.move(handle.x + 8, target.y + target.height * .8, { steps: 14 }); await p.mouse.up();
  await p.waitForTimeout(350); assert.notDeepEqual(await order(), oldOrder); assert.equal(taskRequests, 0);
  const savedOrder = await order();
  await p.mouse.move(4, 880); await panel.waitFor({ state: 'detached' });
  await island.hover(); await panel.waitFor(); assert.deepEqual(await order(), savedOrder);
  await p.mouse.move(4, 880); await p.waitForTimeout(120); await panel.hover(); await p.waitForTimeout(350);
  assert.equal(await panel.count(), 1);
  const scrollBefore = await p.evaluate(() => scrollY);
  await panel.evaluate(el => el.scrollTop = el.scrollHeight); await p.mouse.wheel(0, 1500); await p.waitForTimeout(120);
  assert.equal(await p.evaluate(() => scrollY), scrollBefore);
  assert.ok(await panel.evaluate(el => el.scrollWidth <= el.clientWidth));
  await panel.evaluate(el => el.scrollTop = 0);
  const pendingKey = await p.evaluate(id => acData().groups.find(g => g.task?.id === id && g.can_review).key, info.review);
  const pending = panel.locator(`[data-ac-group="${pendingKey}"]`);
  await pending.getByRole('button', { name: 'Mark read', exact: true }).click();
  await p.waitForFunction(key => !acData().groups.find(g => g.key === key).unread, pendingKey);
  assert.equal(taskRequests, 0);
  await pending.getByRole('button', { name: 'Open task', exact: true }).click();
  await p.locator('#sheet.open h2').filter({ hasText: 'Review evidence' }).waitFor(); assert.equal(taskRequests, 1);
  await p.locator('#shX').click();
  await island.hover(); await panel.waitFor(); await p.keyboard.press('Escape'); await panel.waitFor({ state: 'detached' });
  await p.mouse.move(4, 880); await island.hover(); await panel.waitFor();
  await panel.getByRole('button', { name: 'View all alerts', exact: true }).click();
  await p.locator('#alertSearch').waitFor();
  await p.reload(); await p.waitForFunction(() => !!S.alertCenter);
  assert.equal(await p.evaluate(key => !!acData().groups.find(g => g.key === key).unread, pendingKey), false);
  const oldCount = await p.evaluate(() => acData().counts.unread);
  await p.evaluate(() => api('/api/assign', { tasks: [{ title: 'Live assignment', who: 'Admin One', checker: 'Admin One', hours: 2, output: 'Evidence' }] }));
  await p.waitForFunction(count => acData().counts.unread > count, oldCount);
  await island.hover(); await panel.waitFor(); await p.mouse.click(4, 880); await panel.waitFor({ state: 'detached' });
  console.log('PASS centered island, hover, drag/order persistence, independent descriptions, read persistence, explicit task click, Escape, Alerts navigation and live counts');

  for (const name of ['dash', 'pipe', 'over', 'log', 'assign', 'check', 'mine']) {
    await tab(p, name); assert.ok((await p.locator('main').innerText()).length > 0);
  }
  await tab(p, 'auto'); await p.locator('[data-stage="S02"]').waitFor();
  await p.locator('[data-stage="S02"]').click(); await p.locator('#auStageAdd').click();
  assert.equal(await p.locator('[data-cv="0"]').inputValue(), 'S02');
  await p.locator('[data-rb="name"]').fill('Synthetic browser rule');
  await p.locator('[data-rb="trigger"]').selectOption('task_submitted');
  await p.locator('#rbTestBtn').click(); await p.locator('#rbTest').getByText(/Would have fired/).waitFor();
  await p.locator('#rbSave').click(); await p.locator('#sheet.open').waitFor({ state: 'hidden' });
  await p.locator('[data-av="settings"]').click(); await p.locator('#aSave').click();
  await p.getByText('Automation saved', { exact: true }).waitFor();
  await p.locator('#moreTabs').click(); await p.locator('[data-opt="admin"]').check(); await p.locator('#shX').click();
  await tab(p, 'admin'); await p.locator('#client').fill('Browser synthetic client');
  await p.evaluate(() => render()); // SSE-style redraw must preserve an in-progress draft.
  assert.equal(await p.locator('#client').inputValue(), 'Browser synthetic client');
  const billResponse = p.waitForResponse(r => r.url().endsWith('/api/bills') && r.request().method() === 'POST');
  await p.locator('#newBill').click(); assert.equal((await billResponse).status(), 200);
  await p.locator('#simOut').filter({ hasText: /opened/ }).waitFor();
  console.log('PASS Dashboard, Pipeline, Overview, Activity, Assign, approvals/tasks, workflow model, stage rule builder, dry run, save and Automation Settings');

  const mobile = await pageFor({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await login(mobile);
  const mi = mobile.locator('#adminIsland'), mp = mobile.locator('#adminIslandPanel');
  await mi.tap(); await mp.waitFor();
  const mb = await mi.boundingBox(), pb = await mp.boundingBox();
  assert.ok(Math.abs(mb.x + mb.width / 2 - 195) < 1);
  assert.ok(pb.width <= 366 && pb.y + pb.height <= 844 && pb.height <= 844 * .65 + 1);
  assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  const mobileOrder = () => mp.locator('.ac-island-card').evaluateAll(es => es.map(el => el.dataset.acGroup));
  const oldMobileOrder = await mobileOrder(), mh = await mp.locator('[data-ac-drag]').first().boundingBox();
  const mt = await mp.locator('.ac-island-card').nth(1).boundingBox(), cdp = await mobile.context().newCDPSession(mobile);
  const x = mh.x + mh.width / 2, y = mh.y + mh.height / 2, end = mt.y + mt.height * .8;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y, id: 1 }] });
  for (let i = 1; i <= 12; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y + (end - y) * i / 12, id: 1 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); await cdp.detach();
  await mobile.waitForTimeout(350); assert.notDeepEqual(await mobileOrder(), oldMobileOrder);
  await mp.locator('[data-ac-expand]').first().tap();
  assert.equal(await mp.locator('[data-ac-expand]').first().getAttribute('aria-expanded'), 'true');
  assert.equal(await mobile.locator('#sheet.open,#dlg[open]').count(), 0);
  await mp.getByRole('button', { name: 'Open task', exact: true }).first().tap();
  await mobile.locator('#sheet.open').waitFor(); await mobile.locator('#shX').tap();
  await mi.tap(); await mp.waitFor();
  await mi.tap(); await mp.waitFor({ state: 'detached' });
  await tab(mobile, 'tracker'); await mobile.locator('#trTaskToggle').tap();
  assert.equal(await mobile.locator('#trTaskToggle').getAttribute('aria-expanded'), 'true');
  await mobile.locator('#trTaskToggle').tap();
  assert.equal(await mobile.locator('#trTaskToggle').getAttribute('aria-expanded'), 'false');
  assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await mobile.locator('[data-tr-person="Worker One"]').tap(); await mobile.locator('#trEmployeeModal[open]').waitFor();
  assert.ok((await mobile.locator('#trEmployeeModal').boundingBox()).width <= 390);
  await mobile.context().close();
  console.log('PASS 390px mobile island bounds/tap/touch drag/description/explicit task click, Tracker tap toggle and employee modal without page overflow');

  const motion = await pageFor({ reducedMotion: 'no-preference' });
  await motion.goto(base, { waitUntil: 'domcontentloaded' });
  await motion.locator('#brandIntro').waitFor(); await motion.waitForTimeout(1400);
  assert.equal(await motion.locator('.intro-rest span').count(), 'OMESH ENTERPRISES'.length);
  await motion.locator('#skipIntro').click(); await motion.locator('#brandIntro').waitFor({ state: 'detached' });
  assert.equal(await motion.locator('.login-group.is-open').count(), 0);
  await motion.context().close();
  assert.deepEqual(errors, []);
  console.log('PASS animated intro/letter sequence, Skip Intro and no browser JavaScript exceptions');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
