// Shared-host live sync across separate browser sessions (separate contexts = separate "office PCs").
// Run: python tests/run_browser.py --lan   (synthetic temporary data, never port 8080)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const BASE = process.env.TEST_BASE_URL, PIN = process.env.TEST_ADMIN_PIN, INFO = JSON.parse(process.env.TEST_FIXTURE_INFO);

async function signIn(browser, user, admin) {
  const context = await browser.newContext({reducedMotion: 'reduce'}), page = await context.newPage(), errors = [];
  page.on('pageerror', e => errors.push(user + ': ' + e.message));
  await page.goto(BASE);
  if (admin) {
    await page.locator('[data-login-toggle="admins"]').click();
    await page.locator(`[data-user="${user}"]`).click();
    await page.locator('#pin').fill(PIN); await page.locator('#pinGo').click();
  } else {
    await page.locator('#uq').fill(user); await page.locator(`[data-user="${user}"]`).click();
  }
  await page.locator('#logout').waitFor();
  await page.waitForFunction(() => S.es && S.es.readyState === EventSource.OPEN, null, {polling: 200});
  return {context, page, errors};
}

(async () => {
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const admin = await signIn(browser, 'Admin One', true);
    const worker = await signIn(browser, 'Reviewer', false);
    const admin2 = await signIn(browser, 'Admin Two', true);

    // 1. Admin assigns a task -> the employee's open page shows it without a reload.
    const title = 'LAN sync task ' + Date.now();
    await admin.page.evaluate(t => api('/api/assign', {tasks: [{title: t, who: 'Reviewer', checker: 'Admin One', hours: 1}]}), title);
    await worker.page.getByText(title).first().waitFor({timeout: 10000});
    const tid = await (await worker.page.waitForFunction(t => (S.state.mine.find(x => x.stage_name === t) || {}).id, title, {timeout: 10000, polling: 200})).jsonValue();

    // 2. Employee starts it -> the other admin's session refreshes its data by itself.
    const [, claim] = await Promise.all([admin2.page.waitForResponse(r => r.url().includes('/api/state'), {timeout: 10000}),
      worker.page.evaluate(id => api(`/api/tasks/${id}/claim`, {}).then(() => 'ok', e => e.message), tid)]);
    assert.equal(claim, 'ok');

    // 3. Admin configuration changes reach the other admin (automation/templates are admin-only pushes).
    const [, saveTemplates] = await Promise.all([admin2.page.waitForResponse(r => r.url().includes('/api/state'), {timeout: 10000}),
      admin.page.evaluate(async () => { try { const t = (await api('/api/templates')).templates; await api('/api/templates', {templates: t}); return 'ok'; } catch (e) { return e.message; } })]);
    assert.equal(saveTemplates, 'ok');

    // 4. Outage: the stream answers 503 (EventSource gives up for good on HTTP errors), then the server is back
    //    -> the page retries with back-off, reconnects by itself and catches up on what it missed.
    await worker.page.route('**/stream*', r => r.fulfill({status: 503, body: ''}));
    await worker.page.evaluate(() => { S.es.close(); connect(); });
    await worker.page.waitForFunction(() => S.es.readyState === EventSource.CLOSED, null, {timeout: 10000, polling: 200});
    const title2 = 'After reconnect ' + Date.now();
    await admin.page.evaluate(t => api('/api/assign', {tasks: [{title: t, who: 'Reviewer', checker: 'Admin One', hours: 1}]}), title2);
    await worker.page.unroute('**/stream*');
    await worker.page.waitForFunction(() => S.es.readyState === EventSource.OPEN, null, {timeout: 20000, polling: 200});
    await worker.page.getByText(title2).first().waitFor({timeout: 10000});
    await worker.page.waitForFunction(t => S.state.mine.some(x => x.stage_name === t), title2, {timeout: 10000, polling: 200});
    assert.equal(await worker.page.evaluate(t => S.state.mine.filter(x => x.stage_name === t).length, title2), 1, 'no duplicate task after reconnect');
    assert.equal(await worker.page.evaluate(() => S.retry), 0, 'back-off reset once connected');

    // 5. Excel Workspace: the same employee on two PCs. A save on one updates the other's library/version live.
    const [name, book] = Object.entries(INFO.lan.employees)[0];
    const pcA = await signIn(browser, name, false);
    await pcA.page.evaluate(() => { S.tab = 'excel'; render(); });
    await pcA.page.waitForFunction(() => XL.libraryState === 'ready', null, {timeout: 15000, polling: 200});
    const before = await pcA.page.evaluate(id => (XL.books.find(b => b.id === id) || {}).revision, book.id);
    assert.ok(before >= 1, 'employee document is listed');
    const saved = await (await fetch(BASE + '/api/excel/save', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session': book.token},
      body: JSON.stringify({id: book.id, revision: before, changes: [{sheet: 'Payroll', address: 'D3', value: '777'}]})})).json();
    assert.equal(saved.ok, true, JSON.stringify(saved));
    await pcA.page.waitForFunction(([id, rev]) => (XL.books.find(b => b.id === id) || {}).revision === rev, [book.id, saved.revision], {timeout: 15000, polling: 200});
    // A save from the stale revision is rejected, not silently merged.
    const stale = await fetch(BASE + '/api/excel/save', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session': book.token},
      body: JSON.stringify({id: book.id, revision: before, changes: [{sheet: 'Payroll', address: 'D3', value: '1'}]})});
    assert.equal(stale.status, 400);

    // 6. Cross-site POSTs are refused even with a valid session.
    const cross = await fetch(BASE + '/api/templates', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session': INFO.lan.admin, Origin: 'http://evil.example'}, body: '{}'});
    assert.equal(cross.status, 403);

    const errors = [admin, worker, admin2, pcA].flatMap(s => s.errors);
    assert.deepEqual(errors, []);
    console.log('PASS Chrome, 4 separate sessions: task assignment and start sync live, admin config sync, stream reconnects after an outage and catches up without duplicates, Excel version syncs across two sessions of one employee, stale Excel save rejected, cross-site POST blocked; no page errors');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
