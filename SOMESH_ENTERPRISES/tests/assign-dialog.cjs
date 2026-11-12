// Assign Tasks "Give" dialog: measured geometry at 5 viewports x 2 themes, drag-and-drop cleanup, and the assignment
// itself (cancel, confirm, approver/bill/docs/note saved, keyboard order, validation). Synthetic data from run_browser.py.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const base = process.env.TEST_BASE_URL, pin = process.env.TEST_ADMIN_PIN, out = process.env.TEST_ARTIFACT_DIR;
if (!base || !pin) throw new Error('Run with python tests/run_browser.py --assign-dialog');
const VIEWPORTS = [[1920, 1080], [1366, 768], [1024, 768], [768, 1024], [390, 844]];
const LONG = 'Approver With An Extremely Long Display Name That Must Never Widen The Select Control';

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_CHANNEL || process.platform === 'win32' ? { channel: process.env.BROWSER_CHANNEL || 'msedge' } : {}) });
  const errors = [], results = [];
  async function open(theme, width, height) {
    const context = await browser.newContext({ colorScheme: theme, viewport: { width, height } });
    await context.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    const page = await context.newPage(); page.setDefaultTimeout(15000);
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base);
    await page.locator('[data-login-toggle="admins"]').click();
    await page.locator('[data-user="Admin One"]').click();
    await page.locator('#pin').fill(pin); await page.locator('#pin').press('Enter');
    await page.waitForFunction(() => S.tab === 'dash');
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), theme);
    await page.waitForSelector('[data-tab="assign"]', { state: 'attached' });
    await page.evaluate(() => document.querySelector('[data-tab="assign"]').click());   // the tab strip may be collapsed at phone width
    await page.waitForFunction(() => S.tab === 'assign' && S.adhoc && document.querySelector('[data-asgwho="Worker One"]'));
    return page;
  }
  // Real mouse drag when a task card and the target are on screen together; otherwise (phone layout stacks them far
  // apart, and headless Chromium cancels a native drag that has to scroll) dispatch the browser's exact event order.
  const dropOnto = async (page, who, source = '[data-asgtask^="tpl:"]') => {
    const target = page.locator(`[data-asgwho="${who}"]`);
    await target.evaluate(e => e.scrollIntoView({ block: 'center' }));
    const pick = await page.evaluate(([src, w]) => {
      const t = document.querySelector(`[data-asgwho="${w}"]`).getBoundingClientRect(), top = document.querySelector('.tabsWrap')?.getBoundingClientRect().bottom || 0;
      const vis = (r) => r.top >= top + 4 && r.bottom <= innerHeight - 4 && r.left >= 0 && r.right <= innerWidth;
      const cards = [...document.querySelectorAll(src)]; const i = cards.findIndex(c => vis(c.getBoundingClientRect()));
      return vis(t) && i >= 0 ? i : -1;
    }, [source, who]);
    if (pick >= 0) {
      const a = await page.locator(source).nth(pick).boundingBox(), b = await target.boundingBox();
      await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2); await page.mouse.down();
      await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 12 }); await page.mouse.up();
    } else {
      const dt = await page.evaluateHandle(() => new DataTransfer()), src = page.locator(source).first();
      await src.dispatchEvent('dragstart', { dataTransfer: dt });
      for (const type of ['dragenter', 'dragover', 'drop']) await target.dispatchEvent(type, { dataTransfer: dt });
      await src.dispatchEvent('dragend', { dataTransfer: dt });
    }
    await page.locator('#dlg[open]').waitFor({ timeout: 5000 });
    return pick >= 0 ? 'mouse' : 'events';
  };
  const geometry = (page) => page.evaluate((long) => {
    const sel = document.querySelector('#asgC'); const o = document.createElement('option'); o.textContent = long; o.selected = true; sel.append(o);
    const box = (s) => { const r = document.querySelector(s).getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; };
    const d = document.querySelector('#dlg'), f = document.querySelector('#dlgForm');
    return { dlg: box('#dlg'), H: box('#asgH'), C: box('#asgC'), HL: box('label[for=asgH]'), CL: box('label[for=asgC]'), B: box('#asgB'), N: box('#asgN'),
      docs: box('#dlg input[name=docs]'), cancel: box('#dlg button[value=cancel]'), ok: box('#dlg button[value=ok]'),
      dlgOverflowX: d.scrollWidth - d.clientWidth, formOverflowX: f.scrollWidth - f.clientWidth, pageOverflowX: document.documentElement.scrollWidth - innerWidth,
      pad: parseFloat(getComputedStyle(d).paddingLeft), vw: innerWidth,
      sizing: ['#asgH', '#asgC', '#asgB', '#asgN'].map(s => getComputedStyle(document.querySelector(s)).boxSizing) };
  }, LONG);

  for (const theme of ['light', 'dark']) for (const [w, h] of VIEWPORTS) {
    const page = await open(theme, w, h), tag = `${theme} ${w}x${h}`;
    const how = await dropOnto(page, 'Worker One');
    // drag fully ended: no lifted card, no dashed outlines, no tooltip, no selection, background inert
    const drag = await page.evaluate(() => ({ over: document.querySelectorAll('.asg-over, .asg-target.drop').length,
      dragging: document.body.classList.contains('asg-dragging'), selection: String(getSelection()),
      inert: document.querySelector('#app').matches(':modal') === false && document.querySelector('#dlg').matches(':modal'),
      transform: getComputedStyle(document.querySelector('[data-asgwho="Worker One"]')).transform }));
    assert.deepEqual(drag, { over: 0, dragging: false, selection: '', inert: true, transform: 'none' }, tag + ' drag state');
    const g = await geometry(page), stacked = w <= 480, near = (a, b, tol = 1) => Math.abs(a - b) <= tol;
    const inside = (r) => r.l >= g.dlg.l + g.pad - 0.5 && r.r <= g.dlg.r - g.pad + 0.5 && r.t >= g.dlg.t && r.b <= g.dlg.b;
    assert.deepEqual(g.sizing, ['border-box', 'border-box', 'border-box', 'border-box'], tag);
    assert.ok(near(g.H.w, g.C.w), `${tag} equal widths ${g.H.w} vs ${g.C.w}`);
    assert.ok(near(g.H.h, g.C.h) && near(g.H.h, 44), `${tag} equal 44px heights ${g.H.h} vs ${g.C.h}`);
    let gap;
    if (stacked) { gap = g.CL.t - g.H.b; assert.ok(g.H.b <= g.CL.t && gap >= 12, `${tag} stacked gap ${gap}`); assert.ok(near(g.H.l, g.C.l), tag); }
    else {
      gap = g.C.l - g.H.r;
      assert.ok(g.H.r <= g.C.l && near(gap, 16), `${tag} column gap ${gap}`);
      assert.ok(near(g.HL.t, g.CL.t) && near(g.H.t, g.C.t), `${tag} labels/inputs aligned`);
      assert.ok(near(g.H.l, g.HL.l) && near(g.C.l, g.CL.l), `${tag} labels over their inputs`);
      assert.ok(near(g.H.w + g.C.w + 16, g.B.w), `${tag} row fills the dialog width`);
    }
    assert.ok(near(g.B.w, g.N.w) && near(g.B.l, g.H.l), `${tag} bill and note full width`);
    for (const k of ['H', 'C', 'B', 'N', 'docs', 'cancel', 'ok']) assert.ok(inside(g[k]), `${tag} ${k} inside modal ${JSON.stringify(g[k])}`);
    assert.ok(g.dlg.l >= 0 && g.dlg.r <= g.vw, `${tag} modal inside viewport`);
    assert.deepEqual([g.dlgOverflowX, g.formOverflowX, g.pageOverflowX], [0, 0, 0], `${tag} no horizontal overflow`);
    // vertical rhythm between rows: 12-16px
    for (const [a, b] of [[Math.max(g.H.b, g.C.b), g.docs.t], [g.docs.b, g.B.t - (g.CL.b - g.CL.t) - 6]]) { const v = b - a; assert.ok(v >= 11.5 && v <= 17, `${tag} row spacing ${v}`); }
    results.push(`${tag}: H ${g.H.w.toFixed(1)}x${g.H.h} | C ${g.C.w.toFixed(1)}x${g.C.h} | gap ${gap.toFixed(1)} | modal ${g.dlg.w.toFixed(0)}px | overflow 0 | drop via ${how}`);
    if (out) await page.screenshot({ path: path.join(out, `assign-dialog-${theme}-${w}x${h}.png`) });
    await page.locator('#dlg button[value=cancel]').click();
    await page.context().close();
  }

  // ---- functionality (light, 1366x768) ----
  const page = await open('light', 1366, 768);
  const tasks = () => page.evaluate(async () => (await api('/api/adhoc')).tasks);
  const before = (await tasks()).length;
  // Cancel creates nothing (also Escape)
  await dropOnto(page, 'Worker Two'); await page.locator('#dlg button[value=cancel]').click();
  await dropOnto(page, 'Worker Two'); await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#dlg[open]'));
  assert.equal((await tasks()).length, before, 'cancel/escape must not create a task');
  // Keyboard order: hours -> approver -> docs -> bill -> note -> Cancel -> Confirm
  await dropOnto(page, 'Worker Two');
  await page.locator('#asgH').focus();
  const order = [];
  for (let i = 0; i < 7; i++) { order.push(await page.evaluate(() => { const e = document.activeElement; return e.id || e.name || e.value; })); await page.keyboard.press('Tab'); }
  assert.deepEqual(order, ['asgH', 'asgC', 'docs', 'asgB', 'asgN', 'cancel', 'ok'], 'tab order');
  // Validation: a non-positive time limit is blocked by the browser, the dialog stays open
  await page.locator('#asgH').fill('0'); await page.locator('#dlg button[value=ok]').click();
  assert.equal(await page.locator('#dlg[open]').count(), 1, 'invalid hours keep the dialog open');
  assert.equal(await page.locator('#asgH').evaluate(e => e.validity.rangeUnderflow), true);
  // Fill everything with the keyboard and confirm
  await page.locator('#asgH').fill('2.5');
  await page.locator('#asgC').selectOption('Reviewer');
  const docs = page.locator('#dlg input[name=docs]'), was = await docs.isChecked();   // some templates default to "needs documents"
  await docs.focus(); await page.keyboard.press('Space'); assert.equal(await docs.isChecked(), !was, 'Space toggles the checkbox');
  if (was) await page.keyboard.press('Space');
  assert.equal(await docs.isChecked(), true);
  const bill = await page.locator('#asgB option').nth(1).getAttribute('value'); assert.ok(bill, 'fixture bill present');
  await page.locator('#asgB').selectOption(bill);
  await page.locator('#asgN').fill('Synthetic test note');
  await page.locator('#asgN').press('Enter');
  await page.waitForFunction(() => !document.querySelector('#dlg[open]'));
  await page.waitForFunction(n => S.adhoc && S.adhoc.tasks.length > n, before);
  const after = await tasks(); assert.equal(after.length, before + 1, 'exactly one task created');
  const t = after[0];
  assert.deepEqual(t.owners, ['Worker Two'], 'right employee'); assert.equal(t.validator, 'Reviewer', 'approver saved');
  assert.equal(t.bill_id, bill, 'bill saved'); assert.equal(t.expected_output, 'Synthetic test note', 'note saved');
  assert.equal(t.sla_hours, 2.5, 'time limit saved'); assert.equal(t.needs_docs, true, 'documents flag saved');
  results.push(`assignment: ${t.stage} -> ${t.owners} approver ${t.validator} bill ${t.bill_id} hours 2.5 docs on`);
  // New task with an empty title is refused with a message, nothing created
  await dropOnto(page, 'Worker One', '[data-asgtask="new"]');
  await page.locator('#dlg button[value=ok]').click();
  await page.waitForFunction(() => !document.querySelector('#dlg[open]'));
  assert.equal((await tasks()).length, before + 1, 'empty title creates nothing');
  await page.context().close();

  assert.deepEqual(errors, [], 'no page errors');
  console.log(results.join('\n'));
  console.log('Assign dialog checks passed');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
