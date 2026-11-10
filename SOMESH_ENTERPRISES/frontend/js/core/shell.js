// App shell: sign-in, tabs (incl. optional tabs), header, render() which draws the current page and wires its buttons.
"use strict";
const APP_VERSION = "v2.0";   // shown under the title on the sign-in screen
// ---------------------------------------------------------- admin: optional tabs (hidden until added, remembered per admin on this PC)
const OPTIONAL_TABS = [["guide", "Walkthrough", "How the process works, step by step"], ["store", "Storage", "Master Tracker, Contract Register, Vault"],
                       ["admin", "New bill", "Open bills, and the demo controls"], ["input", "Workflow input", "Load or change the workflow from Excel / Google Sheets"]];
const shownTabs = () => { try { return JSON.parse(store.get("se_tabs_" + S.user) || "[]"); } catch (e) { return []; } };
function tabMenu() {
  const on = shownTabs();
  sheetHtml(`<h2 style="margin:0 0 4px">Tabs</h2><p class="muted small">Add the tabs you need. They are remembered for you on this computer.</p>
    <div class="panel" style="padding:6px 18px">${OPTIONAL_TABS.map(([k, l, d]) => `<label class="switch"><input type="checkbox" data-opt="${k}" ${on.includes(k) ? "checked" : ""}><span><b>${l}</b><span class="muted small" style="display:block">${d}</span></span></label>`).join("")}</div>`);
  $("#sheet").querySelectorAll("[data-opt]").forEach(c => c.onchange = () => {
    const now = shownTabs().filter(k => k !== c.dataset.opt); if (c.checked) now.push(c.dataset.opt);
    store.set("se_tabs_" + S.user, JSON.stringify(now)); if (!c.checked && S.tab === c.dataset.opt) S.tab = "mine"; render();
  });
}
// ---------------------------------------------------------- shell
function logout(expired) {
  if (!expired && S.token) fetch("/api/logout", { method: "POST", headers: hdrs(), body: "{}" }).catch(() => {});
  stopAlertCenterLive(true);
  S.smartAction = null; S.sacFilters = {}; S.sacFocus = "all"; S.sacError = ""; sacSequence++; clearTimeout(sacSearchTimer);
  $("#employeeEditor")?.close(); S.manageEmployees = false; S.employeeSearch = ""; S.billDraft = null; S.billOpenStatus = null; S.openingBills = false;
  closeAdminManagement(); S.adminManagement = null; S.trTableHover = false; S.trTablePinned = false; S.loginGroup = null; S.uq = "";
  S.user = null; S.token = null; S.state = null; S.pipe = null; store.set("se_user", ""); store.set("se_token", ""); if (S.es) S.es.close(); closeSheet(); render();
  api("/api/meta").then(meta => { S.meta = meta; if (!S.user) render(); }).catch(() => {});
}
async function finishSignIn(r) {
  S.token = r.token; S.user = r.user; store.set("se_token", r.token); store.set("se_user", r.user); S.tab = r.admin ? "dash" : "mine"; connect(); await load(); askNotify();
}
async function signIn(name) {
  try { S.meta = await api("/api/meta"); } catch (e) { note("Could not sign in", e.message); return; }
  const u = S.meta.users.find(x => x.name === name) || {};
  if (!u.admin) return fetch("/api/login", { method: "POST", headers: hdrs(), body: JSON.stringify({ user: name }) }).then(r => r.json()).then(r => r.ok ? finishSignIn(r) : note("Couldn't sign in", r.error));
  const d = $("#dlg"), f = $("#dlgForm");
  f.innerHTML = `<div style="text-align:center">${avatar(name)}<h3 style="margin:10px 0 2px">${esc(name)}</h3><p class="muted small">Admin sign-in. Enter your PIN.</p>
    <input class="in" id="pin" name="pin" type="password" inputmode="numeric" autocomplete="current-password" aria-label="PIN" style="max-width:200px;text-align:center;font-size:22px;letter-spacing:.3em" required>
    <p class="small" id="pinErr" role="alert" style="color:var(--red);min-height:18px;margin:8px 0 0"></p></div>
    <div class="actions" style="margin-top:10px;justify-content:center"><button class="btn" id="pinCancel" type="button">Cancel</button><button class="btn primary" id="pinGo" type="submit" value="go">Sign in</button></div>`;
  const pin = $("#pin"), submit = $("#pinGo"), error = $("#pinErr");
  let submitting = false, closed = false, controller;
  $("#pinCancel").onclick = () => d.close("cancel");
  f.onsubmit = async e => {
    e.preventDefault();
    if (submitting) return;
    submitting = true; submit.disabled = true; submit.textContent = "Signing in..."; pin.readOnly = true;
    f.setAttribute("aria-busy", "true"); error.textContent = "";
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/login", { method: "POST", headers: hdrs(), signal: controller.signal, body: JSON.stringify({ user: name, pin: pin.value }) });
      const result = await response.json().catch(() => null);
      if (closed || !d.open) return;
      if (!response.ok || !result || !result.ok || !result.token) {
        error.textContent = response.status >= 500 ? "The server is unavailable. Please try again." : result?.error === "Wrong PIN" ? "Incorrect PIN. Please try again." : result?.error || "Could not sign in. Please try again.";
        pin.readOnly = false; pin.focus(); pin.select(); return;
      }
      f.onsubmit = null; pin.value = ""; d.close("signed-in");
      await finishSignIn(result);
    } catch (e) {
      if (!closed && d.open) {
        error.textContent = e.name === "AbortError" ? "The server took too long to respond. Please try again." : "Could not connect to the server. Please try again.";
        pin.readOnly = false; pin.focus(); pin.select();
      }
    } finally {
      clearTimeout(timeout); submitting = false;
      if (!closed && d.open) { submit.disabled = false; submit.textContent = "Sign in"; pin.readOnly = false; }
      f.removeAttribute("aria-busy");
    }
  };
  d.onclose = () => { closed = true; controller?.abort(); f.onsubmit = null; pin.value = ""; f.removeAttribute("aria-busy"); };
  d.returnValue = ""; d.showModal(); setTimeout(() => { if (d.open) pin.focus(); }, 50);
}
function render() {
  const app = $("#app");
  xlPreserve();
  if (XL.user && XL.user !== S.user) xlResetSession();
  if (!S.meta) { app.innerHTML = `<main>${skeleton("cards")}</main>`; return; }
  if (!S.user) {
    app.innerHTML = loginMarkup();
    wireLogin();
    return;
  }
  const st = S.state || { mine: [], check: [], unread: 0 };
  const alertUnread = isAdmin() ? acData().counts.unread : st.unread;
  const tabs = [["mine", "My tasks", st.mine.length]];
  if (isAdmin() || st.check.length || S.tab === "check") tabs.push(["check", "To check", st.check.length]);
  if (isAdmin()) tabs.push(["action", "Action Center"], ["tracker", "Tracker"], ["over", "Overview"], ["dash", "Dashboard"], ["pipe", "Pipeline"], ["log", "Activity"], ["alerts", "Alerts", alertUnread], ["assign", "Assign tasks"], ["auto", "Automation"]);
  if (isAdmin()) OPTIONAL_TABS.forEach(([k, l]) => { if (shownTabs().includes(k) || S.tab === k) tabs.push([k, l]); });
  else if (canStore()) tabs.push(["store", "Storage"]);
  if (xlEligible()) tabs.push(["excel", "Excel Workspace"]);
  if (!tabs.some(t => t[0] === S.tab)) S.tab = "mine";
  const body = { excel: viewExcel, action: viewActionCenter, mine: viewMine, check: viewCheck, pipe: viewPipe, log: viewLog, alerts: viewAlerts, guide: viewGuide, admin: viewAdmin, input: viewInput, store: viewStore, over: viewOverview, assign: viewAssign, auto: viewAuto, tracker: viewTracker, dash: viewDash }[S.tab]();
  const ae = document.activeElement, keep = ae && ["client", "sacSearch", "loc", "pq", "lq", "tq", "ttq", "dFrom", "dTo", "alertSearch"].includes(ae.id) ? { id: ae.id, v: ae.value, s: ae.selectionStart } : null;
  const focus = null;
  app.innerHTML = `<header>${isAdmin() ? `<div class="ac-island-dock">${alertIslandHtml()}</div>` : ""}<div class="bar"><div class="brand"><div class="logo">S</div><div><b style="display:flex;align-items:center;gap:8px">${APP}<i id="dot" class="dot ${S.es && S.es.readyState === 1 ? "on" : ""}" title="Live connection"></i></b></div></div>
      ${isAdmin() ? `<button class="btn ghost" id="manageAdmins" type="button">Manage Admins</button>` : ""}
      <button class="btn" id="snd" type="button" aria-pressed="${S.sound}" title="Alert sound" aria-label="Alert sound">${S.sound ? "🔊" : "🔇"}</button>
      ${!isAdmin() ? `<button class="btn" id="help" type="button" title="How it works" aria-label="How it works">?</button>` : ""}${isAdmin() ? "" : `<button class="btn bell" id="bell" type="button" aria-label="Alerts${st.unread ? `, ${st.unread} unread` : ""}">🔔${st.unread ? `<b>${st.unread}</b>` : ""}</button>`}
      <div class="me">${avatar(S.user)}<b class="small">${esc(S.user)}</b><button class="btn ghost" id="logout" type="button">Switch</button></div></div>
    ${tabs.length > 1 ? `<div class="tabsWrap"><div class="seg" role="tablist">${tabs.map(([k, l, n]) => `<button role="tab" aria-selected="${S.tab === k}" data-tab="${k}">${l}${n ? `<span class="n">${n}</span>` : ""}</button>`).join("")}${isAdmin() ? `<button type="button" id="moreTabs" title="Add or remove tabs" aria-label="Add or remove tabs" style="font-size:15px">＋</button>` : ""}</div></div>` : ""}${isAdmin() && lunchNow() ? `<div class="lunchbar">Lunch break: staff are locked and timers are paused until ${ampm((S.meta.lunch || {}).end || "14:00")}</div>` : ""}</header>
    <main>${isAdmin() && S.tab === "dash" ? employeeSection() : ""}${body}${["mine", "dash"].includes(S.tab) ? xlDashboard() : ""}</main>`;
  if (keep) { const l = $("#" + keep.id); if (l) { l.value = keep.v; l.focus(); try { l.setSelectionRange(keep.s, keep.s); } catch (e) {} } }
  app.querySelectorAll("[data-bill]").forEach(b => b.onclick = () => loadBill(b.dataset.bill));
  const pq = $("#pq"); if (pq) pq.oninput = () => { S.pq = pq.value; render(); };
  const lq = $("#lq"); if (lq) lq.oninput = () => { S.lq = lq.value; render(); };
  app.querySelectorAll("[data-pf]").forEach(b => b.onclick = () => { S.pf = b.dataset.pf; render(); });
  const csv = $("#csv"); if (csv) csv.onclick = exportCsv;
  app.querySelectorAll("[data-pv]").forEach(b => b.onclick = async () => { S.pv = b.dataset.pv; render(); if (S.pv === "time") { try { S.tt = await api(ttUrl()); } catch (e) {} render(); } });
  app.querySelectorAll("[data-demo]").forEach(c => c.onchange = async () => { S.showDemo = c.checked; render(); await load(); });
  const ttD = $("#ttDate"); if (ttD) ttD.onchange = async () => { S.ttDate = ttD.value; try { S.tt = await api(ttUrl()); } catch (e) { note("Couldn't load", e.message); } render(); };
  const ttq = $("#ttq"); if (ttq) ttq.oninput = () => { S.ttq = ttq.value; render(); };
  hideTip(); app.querySelectorAll("[data-tip]").forEach(el => { el.onmouseenter = el.onfocus = () => showTip(el); el.onmouseleave = el.onblur = hideTip; });
  const ttd = $("#ttd"); if (ttd) ttd.onchange = () => { S.ttd = ttd.value; render(); };
  const ttB = $("#ttBusy"); if (ttB) ttB.onchange = () => { S.ttBusy = ttB.checked; render(); };
  app.querySelectorAll("[data-ttc]").forEach(b => b.onclick = () => { store.set("se_tt_compact", b.dataset.ttc); render(); });
  app.querySelectorAll("[data-tab]").forEach(b => b.onclick = async () => { S.tab = b.dataset.tab; render(); if (S.tab === "alerts") { if (isAdmin()) refreshAlertCenter(); else api("/api/alerts/read", {}).then(load); } if (S.tab === "input") { try { S.wf = await api("/api/workflow"); } catch (e) {} } if (S.tab === "store") { try { S.st = await api("/api/storage"); } catch (e) {} } if (S.tab === "assign") { try { S.adhoc = await api("/api/adhoc"); } catch (e) {} } if (S.tab === "auto") await loadAuto(); if (S.tab === "action") await sacLoad(false); if (S.tab === "tracker") { try { S.tr = await api(trUrl()); } catch (e) {} } if (S.tab === "pipe") { try { S.tt = await api(ttUrl()); if (!S.tpls) S.tpls = (await api("/api/templates")).templates; } catch (e) {} } if (S.tab === "dash") { render(); try { S.dash = await api(dashUrl()); } catch (e) {} } render(); });
  $("#logout").onclick = () => logout();
  wireEmployees();
  const manage = $("#manageAdmins"); if (manage) manage.onclick = openAdminManagement;
  $("#snd").onclick = () => { S.sound = !S.sound; store.set("se_sound", S.sound ? "on" : "off"); unlockAudio(); if (S.sound) beep(); render(); };
  const bell = $("#bell"); if (bell) bell.onclick = () => { if (isAdmin()) { S.tab = "alerts"; render(); refreshAlertCenter(); return; }
    api("/api/alerts/read", {}).then(load); sheetHtml(`<h2 style="margin:0 0 14px">Alerts</h2>${viewAlerts().replace(/^<div class="hero">[\s\S]*?<\/div><\/div>/, "")}`); };
  const hb = $("#help"); if (hb) hb.onclick = () => sheetHtml(viewGuide());
  const mt = $("#moreTabs"); if (mt) mt.onclick = tabMenu;
  app.querySelectorAll("[data-docs]").forEach(b => b.onclick = () => showDocs(b.dataset.docs));
  app.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act, Number(b.dataset.id)));
  if (S.tab === "action") wireActionCenter();
  if (S.tab === "admin") wireAdmin();
  if (S.tab === "input" && isAdmin() && S.wf) wireInput();
  if (S.tab === "store" && S.st) wireStore();
  if (S.tab === "assign" && S.adhoc) wireAssign();   // pages are wired only once their data has loaded
  if (S.tab === "tracker" && S.tr) wireTracker();
  if (S.tab === "auto" && S.autoCfg) wireAuto();
  if (S.tab === "pipe" && isAdmin()) { wirePalette(); const hd = app.querySelector("header"); if (hd) document.documentElement.style.setProperty("--hdr", hd.offsetHeight + "px"); }
  if (S.tab === "dash") wireDash();
  wireExcel();
  wireAlertIsland();
  if (S.tab === "alerts" && isAdmin()) wireAdminAlertCenter();
  app.querySelectorAll("[data-deltask]").forEach(b => b.onclick = () => { const t = ((S.adhoc || {}).tasks || []).find(x => x.id === Number(b.dataset.deltask)); if (t) deleteTask(t); });
  app.querySelectorAll("[data-preview]").forEach(b => b.onclick = () => showPreview(b.dataset.preview));
  app.querySelectorAll("[data-attach]").forEach(i => i.onchange = () => attachFiles(Number(i.dataset.attach), [...i.files]));
  app.querySelectorAll("[data-unattach]").forEach(b => b.onclick = async () => { try { await api(`/api/tasks/${b.dataset.unattach}/unupload`, { name: b.dataset.name }); load(); } catch (e) { note("Couldn't remove", e.message); } });
}
function askNotify() { try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch (e) {} }
