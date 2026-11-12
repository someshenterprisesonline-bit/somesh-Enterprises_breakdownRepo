// NEFT SHEET bank fields in the real Excel Workspace UI: IFSC Code (exactly 11 characters) and ACCOUNT NUMBER
// (exact text), plus the VALIDATION ERROR dialog (centered, blurred backdrop, light/dark, keyboard, focus return).
// Run: python tests/run_browser.py --bank   (synthetic temporary data, never port 8080)
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const info = JSON.parse(process.env.TEST_FIXTURE_INFO).neft, base = process.env.TEST_BASE_URL, out = process.env.TEST_ARTIFACT_DIR;
const ACC = {a10: '1234567890', a16: '1234567890123456', a20: '12345678901234567890', a30: '123456789012345678901234567890', zero: '000012345678901234'};
const results = [];
const pass = (name, expected, actual) => { results.push([name, expected, actual]); };

async function session(browser, theme, viewport) {
  const context = await browser.newContext({viewport, colorScheme: theme, reducedMotion: 'no-preference'});
  await context.route('https://fonts.googleapis.com/**', r => r.fulfill({contentType: 'text/css', body: ''}));
  const p = await context.newPage(), errors = [];
  p.on('pageerror', e => errors.push(e.message));
  p.on('response', r => { if (r.url().includes('/api/') && r.status() >= 500) errors.push(r.status() + ' ' + r.url()); });
  await p.addInitScript(({token, theme}) => { localStorage.setItem('se_token', token); localStorage.setItem('se_user', 'Nandha'); localStorage.setItem('se_theme_user_Nandha', theme); }, {token: info.token, theme});
  await p.goto(base); await p.locator('#xlDashboard').click(); await p.waitForFunction(() => XL.templates.length === 2);
  return {context, p, errors};
}
const neft = p => p.locator('[data-section="neft"]');
const cell = (p, a) => neft(p).locator(`[data-cell="${a}"]`);
const idle = p => p.waitForFunction(() => { const n = XL.panels.get('neft'); return n && !n.busy && !XL.validationOpen; }, null, {timeout: 20000});
const saved = p => p.waitForFunction(() => { const n = XL.panels.get('neft'); return !n.busy && !n.dirty(); }, null, {timeout: 20000});
const dialogOpen = p => p.locator('dialog.xl-validation[open]');
async function serverValue(p, address) {
  return p.evaluate(async a => { const n = XL.panels.get('neft'), r = await n.request('/api/excel/sheet?' + new URLSearchParams({id: n.id, sheet: n.sheet, limit: 100}));
    return r.rows.flatMap(x => x.cells).find(c => c.address === a)?.value; }, address);
}
async function expectDialog(p, {length, text, focus, shot}, close = 'click') {
  const d = dialogOpen(p); await d.waitFor({timeout: 5000});
  await p.waitForTimeout(260);  // let the scale-in animation finish before measuring
  const m = await p.evaluate(() => {
    const d = document.querySelector('dialog.xl-validation[open]'), r = d.getBoundingClientRect(), cs = getComputedStyle(d), bd = getComputedStyle(d, '::backdrop');
    const h = d.querySelector('h2'), hit = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
    const lum = c => { const v = c.match(/[\d.]+/g).slice(0, 3).map(x => x / 255).map(x => x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4); return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]; };
    const [a, b] = [lum(getComputedStyle(h).color), lum(cs.backgroundColor)].sort((x, y) => y - x);
    return {dx: Math.abs(r.left + r.width / 2 - innerWidth / 2), dy: Math.abs(r.top + r.height / 2 - innerHeight / 2), inside: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight,
      modal: d.matches(':modal'), role: d.getAttribute('role'), labelled: !!document.getElementById(d.getAttribute('aria-labelledby')), blur: bd.backdropFilter || bd.webkitBackdropFilter || '',
      heading: h.textContent, text: d.textContent, focused: document.activeElement === d.querySelector('.xl-validation-ok'), onTop: d.contains(hit), contrast: (a + .05) / (b + .05), bg: cs.backgroundColor};
  });
  assert.ok(m.dx <= 2 && m.dy <= 2 && m.inside, 'dialog centered in the viewport ' + JSON.stringify(m));
  assert.ok(m.modal && m.onTop && m.role === 'alertdialog' && m.labelled && m.focused, 'modal, on top, accessible, OK focused ' + JSON.stringify(m));
  assert.match(m.blur, /blur\(12px\)/, 'backdrop blur');
  assert.ok(m.contrast >= 7, 'heading contrast ' + m.contrast);
  assert.equal(m.heading, 'VALIDATION ERROR');
  assert.ok(m.text.includes(text), m.text);
  if (length !== undefined) assert.ok(m.text.includes(`You entered ${length} character`), m.text);
  if (shot) await p.screenshot({path: shot});
  // background is inert: a click on the page behind does nothing while the dialog is open
  const before = await p.evaluate(() => S.tab); await p.mouse.click(5, 5); assert.equal(await p.evaluate(() => S.tab), before); assert.equal(await d.count(), 1);
  if (close === 'escape') await p.keyboard.press('Escape'); else if (close === 'enter') await p.keyboard.press('Enter'); else await d.locator('.xl-validation-ok').click();
  await p.waitForFunction(() => !document.querySelector('dialog.xl-validation'));
  if (focus) await p.waitForFunction(a => document.activeElement?.dataset?.cell === a, focus, {timeout: 5000});
  return m;
}

async function run(browser, theme, viewport, full) {
  const {context, p, errors} = await session(browser, theme, viewport);
  try {
    const tag = `${theme} ${viewport.width}x${viewport.height}`;
    await neft(p).locator('[data-xl="blank"]').click(); await p.waitForFunction(() => !XL.panels.get('neft').preview && !XL.panels.get('neft').busy);
    // Fill three valid rows by paste (valid paste is applied and autosaved).
    const rows = [[1, 'Person A', 'Guard', 'Bank', ACC.a30, 'Branch', 'SBIN0000001', 1000, 'r1'], [2, 'Person B', 'Guard', 'Bank', ACC.zero, 'Branch', 'SBIN0000002', 1001, 'r2'], [3, 'Person C', 'Guard', 'Bank', ACC.a16, 'Branch', 'SBIN0000003', 1002, 'r3']];
    await cell(p, 'A2').evaluate((el, text) => { const d = new DataTransfer(); d.setData('text/plain', text); el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true, cancelable: true})); }, rows.map(r => r.join('\t')).join('\n'));
    await saved(p);
    assert.equal(await serverValue(p, 'E2'), ACC.a30); assert.equal(await serverValue(p, 'E3'), ACC.zero);

    // IFSC 5 / 10 / 12 / 15 characters -> dialog on commit (Tab), focus returns to the cell, nothing saved.
    const closers = ['click', 'enter', 'escape', 'click'];
    for (const [i, n] of [5, 10, 12, 15].entries()) {
      const value = ('HDFC0' + '9'.repeat(20)).slice(0, n);
      await cell(p, 'G2').fill(value); await cell(p, 'G2').press('Tab');
      const m = await expectDialog(p, {length: n, text: 'IFSC Code must contain exactly 11 characters. Please check the entered IFSC Code.', focus: 'G2', shot: i === 0 ? path.join(out, `bank-dialog-${theme}-${viewport.width}.png`) : null}, closers[i]);
      if (i === 0) { pass(`Dialog position/blur/contrast (${tag})`, 'centered ±2px, blur(12px), contrast ≥7', `dx ${m.dx.toFixed(1)} dy ${m.dy.toFixed(1)}, ${m.blur}, contrast ${m.contrast.toFixed(1)}, bg ${m.bg}`); }
      pass(`IFSC ${n} characters (${tag})`, 'popup, focus back on G2', `popup "You entered ${n} characters", closed with ${closers[i]}`);
    }
    await idle(p); await p.waitForTimeout(1300);  // autosave ran meanwhile: the invalid IFSC stayed in the draft only
    assert.equal(await serverValue(p, 'G2'), 'SBIN0000001', 'invalid IFSC never saved');

    // Typing an 11-character code slowly never interrupts (autosave fires mid-typing) and then saves.
    await cell(p, 'G2').fill(''); await cell(p, 'G2').focus();
    await p.keyboard.type('SBIN', {delay: 30}); await p.waitForTimeout(1300);
    assert.equal(await dialogOpen(p).count(), 0, 'no popup while still typing');
    await p.keyboard.type('0004321', {delay: 30}); await cell(p, 'G2').press('Tab');
    await p.waitForTimeout(250); assert.equal(await dialogOpen(p).count(), 0, 'valid 11 characters: no popup');
    await saved(p); assert.equal(await serverValue(p, 'G2'), 'SBIN0004321');
    pass(`IFSC 11 characters (${tag})`, 'accepted, saved, no popup while typing', 'saved SBIN0004321; no dialog during a 1.3 s pause mid-typing');

    if (full) {
      // Invalid IFSC during autosave: the unrelated valid edit is saved, the invalid one stays in the draft.
      await cell(p, 'G3').fill('SBIN01'); await cell(p, 'I3').click();
      await expectDialog(p, {length: 6, text: 'exactly 11 characters', focus: 'G3'});
      await cell(p, 'I2').fill('remark saved'); await cell(p, 'I2').press('Tab'); await p.waitForTimeout(1500); await idle(p);
      assert.equal(await serverValue(p, 'I2'), 'remark saved'); assert.equal(await serverValue(p, 'G3'), 'SBIN0000002');
      assert.ok(await p.evaluate(() => XL.panels.get('neft').changes.has('NEFT!G3')), 'invalid IFSC kept in the draft');
      pass('Invalid IFSC during autosave', 'rejected, unrelated valid edit saved', 'I2 saved; G3 kept in draft, server unchanged');
      // Explicit Save Changes with the invalid IFSC still in the draft -> dialog, nothing lost.
      await neft(p).locator('[data-xl="save"]').click();
      await expectDialog(p, {length: 6, text: 'exactly 11 characters', focus: 'G3'}, 'enter');
      await cell(p, 'G3').fill('SBIN0000002'); await cell(p, 'G3').press('Tab'); await saved(p);

      // Empty IFSC while the row has an account number: autosave holds it, Save Changes shows "required".
      await cell(p, 'G4').fill(''); await cell(p, 'G4').press('Tab'); await p.waitForTimeout(1500); await idle(p);
      assert.equal(await dialogOpen(p).count(), 0, 'no popup for an empty cell on autosave');
      assert.equal(await serverValue(p, 'G4'), 'SBIN0000003');
      await neft(p).locator('[data-xl="save"]').click();
      await expectDialog(p, {text: 'IFSC Code is required when an account number is entered.', focus: 'G4'});
      await cell(p, 'G4').fill('SBIN0000003'); await cell(p, 'G4').press('Tab'); await saved(p);
      pass('Empty required IFSC', 'validation error, nothing saved', 'held back by autosave; Save Changes -> "IFSC Code is required" dialog; server kept old value');

      // Pasted invalid IFSC (multi-cell paste) -> rejected, nothing changes.
      await cell(p, 'F2').evaluate(el => { const d = new DataTransfer(); d.setData('text/plain', 'New branch\tSBIN12'); el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true, cancelable: true})); });
      await expectDialog(p, {length: 6, text: 'Paste cancelled: nothing was changed.', focus: 'G2'});
      assert.equal(await cell(p, 'F2').inputValue(), 'Branch'); assert.equal(await cell(p, 'G2').inputValue(), 'SBIN0004321');
      pass('Pasted invalid IFSC', 'rejected', 'paste cancelled, F2/G2 unchanged');

      // Backend rejection (an out-of-date page skipping the browser check) -> same dialog, not a server/database error.
      await p.evaluate(() => { window.__realCheck = xlBankProblem; xlBankProblem = () => null; });
      await cell(p, 'G3').fill('SBIN0'); await cell(p, 'G3').press('Tab');
      await neft(p).locator('[data-xl="save"]').click();
      const m = await expectDialog(p, {text: 'IFSC Code must contain exactly 11 characters.', focus: 'G3'});
      assert.ok(m.text.includes('You entered 5 characters') && !/unavailable|Server error|database/i.test(m.text), m.text);
      assert.ok(await p.evaluate(() => XL.panels.get('neft').changes.has('NEFT!G3')), 'draft kept after server rejection');
      await p.evaluate(() => { xlBankProblem = window.__realCheck; });
      await cell(p, 'G3').fill('SBIN0000002'); await cell(p, 'G3').press('Tab'); await saved(p);
      pass('Backend rejection', 'VALIDATION ERROR dialog, not database-unavailable', 'server 400 -> dialog "You entered 5 characters", focus G3, draft kept');

      // Account numbers: 10/16/20/30 digits and leading zero, typed and pasted, exact after save and reload.
      await cell(p, 'E4').fill(ACC.a10); await cell(p, 'E4').press('Tab'); await saved(p);
      await cell(p, 'E4').fill(''); await cell(p, 'E4').focus(); await p.keyboard.insertText(ACC.a20); await cell(p, 'E4').press('Tab'); await saved(p);
      assert.equal(await serverValue(p, 'E4'), ACC.a20);
      await cell(p, 'E4').fill('ABC123'); await cell(p, 'E4').press('Tab');
      await expectDialog(p, {text: 'Account Number must contain digits only', focus: 'E4'});
      await cell(p, 'E4').fill(ACC.a20); await cell(p, 'E4').press('Tab'); await saved(p);
      const docId = await p.evaluate(() => XL.panels.get('neft').id);
      await p.reload(); await p.locator('#xlDashboard').click(); await p.waitForFunction(() => XL.templates.length === 2); await neft(p).locator('.xl-file').selectOption(docId); await neft(p).locator('.xl-grid').waitFor(); await idle(p);
      const shown = {E2: await cell(p, 'E2').inputValue(), E3: await cell(p, 'E3').inputValue(), E4: await cell(p, 'E4').inputValue()};
      assert.deepEqual(shown, {E2: ACC.a30, E3: ACC.zero, E4: ACC.a20});
      const style = await p.evaluate(() => ['E2', 'G2', 'B2'].map(a => { const cs = getComputedStyle(document.querySelector(`[data-section="neft"] [data-cell="${a}"]`)); return cs.fontSize + ' ' + cs.textAlign; }));
      assert.equal(new Set(style).size, 1, 'account cells styled like the other NEFT columns ' + style);
      const fits = await cell(p, 'E2').evaluate(el => el.scrollWidth <= el.clientWidth);
      assert.ok(fits, 'the full 30-digit account number is visible without scrolling the cell');
      if (await p.locator('#skipIntro').isVisible().catch(() => false)) await p.locator('#skipIntro').click();
      await p.waitForFunction(() => !document.querySelector('#skipIntro'), null, {timeout: 15000}).catch(() => {});
      await cell(p, 'E2').scrollIntoViewIfNeeded(); await cell(p, 'E2').click();
      await p.screenshot({path: path.join(out, `bank-accounts-${theme}.png`)});
      const sci = await p.evaluate(() => [...document.querySelectorAll('[data-section="neft"] [data-cell^="E"]')].some(i => /e\+/i.test(i.value)));
      assert.equal(sci, false, 'no scientific notation anywhere in the ACCOUNT NUMBER column');
      pass('Account numbers 10/16/20/30 digits, leading zero, pasted', 'identical digits after save and reload, text, no E+', JSON.stringify(shown));
    }
    assert.deepEqual(errors, [], 'no page errors or 5xx');
  } finally { await context.close(); }
}

(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome'});
  try {
    await run(browser, 'light', {width: 1440, height: 900}, true);
    await run(browser, 'dark', {width: 1440, height: 900}, true);
    await run(browser, 'dark', {width: 768, height: 1024}, false);
    await run(browser, 'light', {width: 390, height: 844}, false);
    for (const [name, expected, actual] of results) console.log(`PASS | ${name} | expected: ${expected} | actual: ${actual}`);
    console.log(`PASS bank fields: ${results.length} checks in Chrome (light/dark, 1440/768/390 px); screenshots bank-dialog-*.png`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
