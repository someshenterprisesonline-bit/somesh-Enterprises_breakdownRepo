// Multi-user office simulation: one Admin, Employee A and Employee B (plus a second Admin), each in its own
// browser context ("its own PC") against ONE shared test server and database.
// Run: python tests/run_browser.py --multi-user   (synthetic temporary data, never port 8080)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const BASE = process.env.TEST_BASE_URL, PIN = process.env.TEST_ADMIN_PIN;
const A = 'Reviewer', B = 'Worker One', ADMIN = 'Admin One', ADMIN2 = 'Admin Two';

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
  await page.locator('#logout').waitFor({timeout: 60000});
  await page.waitForFunction(() => S.es && S.es.readyState === EventSource.OPEN, null, {polling: 200, timeout: 60000});
  return {context, page, errors, user};
}
// Call the API as this signed-in person; returns {status, body} instead of throwing.
const call = (s, path, body) => s.page.evaluate(async ([p, b]) => {
  const r = await fetch(p, b ? {method: 'POST', headers: hdrs(), body: JSON.stringify(b)} : {headers: hdrs()});
  return {status: r.status, body: await r.json().catch(() => null)};
}, [path, body]);
const mineHas = (s, title) => s.page.waitForFunction(t => S.state && S.state.mine.some(x => x.stage_name === t), title, {timeout: 15000, polling: 200});

(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome'});
  try {
    const admin = await signIn(browser, ADMIN, true);
    const empA = await signIn(browser, A, false);
    const empB = await signIn(browser, B, false);
    const admin2 = await signIn(browser, ADMIN2, true);

    // 1. Admin assigns a private task to Employee A with an approver, time limit and required documents.
    const title = 'Private task for A ' + Date.now();
    const made = await call(admin, '/api/assign', {tasks: [{title, who: A, checker: ADMIN, hours: 1.5, output: 'Signed salary sheet', docs: true}]});
    assert.equal(made.status, 200, JSON.stringify(made.body));
    await empA.page.getByText(title).first().waitFor({timeout: 15000});  // live, no reload
    await mineHas(empA, title);
    const task = await empA.page.evaluate(t => S.state.mine.find(x => x.stage_name === t), title);
    assert.ok(task && task.id, 'task reached Employee A');
    assert.equal(task.validator, ADMIN, 'approver stored');
    assert.ok(task.due_at, 'time limit stored as a deadline');

    // 2. Employee B never receives it: not in B's state, not on B's page, and B cannot act on it.
    await empB.page.evaluate(() => refresh && refresh());
    await empB.page.waitForTimeout(800);
    const bState = await call(empB, '/api/state');
    assert.equal(bState.status, 200);
    assert.ok(!JSON.stringify(bState.body).includes(title), "Employee B's data must not contain A's private task");
    assert.equal(await empB.page.getByText(title).count(), 0, "A's task is not shown on B's screen");
    const bClaim = await call(empB, `/api/tasks/${task.id}/claim`, {});
    assert.notEqual(bClaim.status, 200, 'B cannot start A\'s task');
    const bApprove = await call(empB, `/api/tasks/${task.id}/approve`, {});
    assert.notEqual(bApprove.status, 200, 'B cannot approve A\'s task');

    // 3. Admin-only APIs are refused for employees on the server (not just hidden buttons); no session = 401.
    for (const path of ['/api/employees', '/api/admins', '/api/adhoc', '/api/pipeline', '/api/action-center', '/api/alerts', '/api/rules']) {
      const r = await call(empB, path);
      assert.equal(r.status, 403, `${path} must be admin-only, got ${r.status}`);
    }
    for (const [path, body] of [['/api/assign', {tasks: [{title: 'sneaky', who: B, checker: B, hours: 1}]}],
                                ['/api/employees', {action: 'edit', original: B, name: B, designation: 'Boss', dept: 'Management', access_role: 'admin'}]]) {
      const r = await call(empB, path, body);
      assert.equal(r.status, 403, `${path} POST must be refused for employees, got ${r.status}`);
    }
    const anon = await empB.page.evaluate(async () => (await fetch('/api/state')).status);
    assert.equal(anon, 401, 'no session token -> sign in again');
    const forged = await empB.page.evaluate(async () => (await fetch('/api/state', {headers: {'X-Session': 'forged-token'}})).status);
    assert.equal(forged, 401, 'forged session token is rejected');

    // 4. Employee A starts and submits; the Admin (approver) sees the status change live.
    const [, claim] = await Promise.all([admin.page.waitForResponse(r => r.url().includes('/api/state'), {timeout: 15000}),
      call(empA, `/api/tasks/${task.id}/claim`, {})]);
    assert.equal(claim.status, 200, JSON.stringify(claim.body));
    const adhoc = await call(admin, '/api/adhoc');
    assert.equal(adhoc.body.tasks.find(t => t.id === task.id).status, 'in_progress', 'Admin sees In progress');
    const submit = await call(empA, `/api/tasks/${task.id}/submit`, {note: 'done'});
    assert.equal(submit.status, 200, JSON.stringify(submit.body));
    await admin.page.waitForFunction(id => S.state && S.state.check.some(x => x.id === id), task.id, {timeout: 15000, polling: 200});
    assert.ok(!(await call(empB, '/api/state')).body.check.some(x => x.id === task.id), 'not in B\'s To Check');
    const approve = await call(admin, `/api/tasks/${task.id}/approve`, {note: 'ok'});
    assert.equal(approve.status, 200, JSON.stringify(approve.body));
    await empA.page.waitForFunction(id => (S.state.alerts || []).some(a => a.task_id === id && a.kind === 'approved'), task.id, {timeout: 15000, polling: 200});

    // 5. Refresh keeps saved data (it lives on the server, not in the browser).
    await empA.page.reload();
    await empA.page.locator('#logout').waitFor();
    await empA.page.waitForFunction(id => S.state && (S.state.mine.some(x => x.id === id) || S.state.alerts.some(a => a.task_id === id)), task.id, {timeout: 15000, polling: 200});

    // 6. Admin updates an employee's details -> the other Admin and the employee's own session get them live.
    const designation = 'Senior Analyst ' + Date.now() % 1000;
    const edit = await call(admin, '/api/employees', {action: 'edit', original: B, name: B, designation, dept: 'Operations', access_role: 'employee'});
    assert.equal(edit.status, 200, JSON.stringify(edit.body));
    await admin2.page.waitForFunction(([n, d]) => (S.meta.users.find(u => u.name === n) || {}).designation === d, [B, designation], {timeout: 15000, polling: 200});
    await empB.page.waitForFunction(([n, d]) => (S.meta.users.find(u => u.name === n) || {}).designation === d, [B, designation], {timeout: 15000, polling: 200});
    const meB = await call(empB, '/api/me');
    assert.equal(meB.body.admin, false, 'editing details never grants Admin access');

    const errors = [...admin.errors, ...empA.errors, ...empB.errors, ...admin2.errors];
    assert.deepEqual(errors, [], 'no page JavaScript errors');
    console.log('PASS Chrome, 4 separate sessions on one shared server: Admin assigns (approver, time limit, documents) -> Employee A sees it live; ' +
      'Employee B cannot see/start/approve it; 7 admin-only GET and 2 POST APIs refused for employees, missing/forged session 401; ' +
      'A starts and submits -> Admin sees status and To Check live, approves -> A notified; refresh keeps data; ' +
      'Admin edits employee details -> other Admin and the employee see them live without gaining Admin access');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
