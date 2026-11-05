// Pages: Activity and Alerts.
"use strict";
function viewLog() {
  const qtxt = (S.lq || "").toLowerCase(); const ev = (S.pipe ? S.pipe.events : []).filter(e => (S.showDemo !== false || !String(e.bill_id || "").startsWith("DEMO-")) && !qtxt || (e.text + " " + e.actor + " " + (e.bill_id || "")).toLowerCase().includes(qtxt));
  return hero("Activity", "Every start, submit, approval and hand-off.") + `<div class="toolbar"><input class="search" id="lq" placeholder="Search by bill, person or stage" value="${esc(S.lq || "")}" aria-label="Search activity"></div><div class="list">${ev.map(e => `<div class="row"><span class="t">${esc(e.ts)}</span><span>${esc(e.text)}</span></div>`).join("") || `<p class="empty">No activity yet.</p>`}</div>`;
}
// ---------------------------------------------------------- Alerts: cards with type / person / day filters
// Used by the Alerts tab (admins) and inside the bell's side panel (staff, no person filter).
// Filter choices live in S: S.alType ("all"), S.alPerson ("" = everyone), S.alDay ("all"); S.alOpen = expanded "× N" groups.
const AL_TYPES = [["all", "All"], ["unread", "Unread"], ["check", "To check"], ["new", "New task"], ["approved", "Approved"], ["back", "Sent back"], ["overdue", "Overdue"], ["other", "Contract / other"]];
const AL_DAYS = [["today", "Today"], ["yesterday", "Yesterday"], ["7", "Last 7 days"], ["all", "All"]];
function alType(x) {   // -> [filter bucket, card label]
  const t = String(x.title || "");
  if (/^contract/i.test(t)) return ["other", "Contract check"];   // contract checks arrive with kind "rejected"
  return { validate: ["check", "Please check"], new_task: ["new", "New task"], approved: ["approved", "Approved"], complete: ["approved", "Completed"],
    rejected: ["back", "Sent back"], overdue: ["overdue", "Overdue"] }[x.kind] || ["other", /contract/i.test(t + " " + x.body) ? "Contract check" : "Notice"];
}
const alDay = (ts) => String(ts || "").slice(0, 10);
const alShift = (ymd, n) => { const d = new Date(ymd + "T00:00"); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const alTime = (ts) => { const m = /(\d{2}):(\d{2})/.exec(String(ts).slice(11)); if (!m) return ""; const h = +m[1]; return `${h % 12 || 12}:${m[2]} ${h < 12 ? "AM" : "PM"}`; };
function alDayLabel(k, t0) {
  if (k === t0) return "Today"; if (k === alShift(t0, -1)) return "Yesterday";
  const d = new Date(k + "T00:00"); if (isNaN(d)) return k;
  return `${d.toLocaleDateString("en-GB", { weekday: "short" })}, ${d.getDate()} ${d.toLocaleDateString("en-GB", { month: "short" })}`;
}
const alBill = (x) => x.bill_id || ((/\b[A-Z]{2,}-\d{4}-\d{3}\b/.exec(String(x.title) + " " + String(x.body)) || [])[0]) || "";   // contract checks name the bill only in the text
function alertsBody(inSheet) {
  const all = (S.state && S.state.alerts) || [], type = S.alType || "all", person = inSheet ? "" : (S.alPerson || ""), day = S.alDay || "all";
  const t0 = today(), y0 = alShift(t0, -1), w0 = alShift(t0, -6), open = S.alOpen || {};
  const inDay = (k) => day === "all" || (day === "today" ? k === t0 : day === "yesterday" ? k === y0 : k >= w0 && k <= t0);
  const base = all.filter(x => inDay(alDay(x.ts)) && (!person || (x.title + " " + x.body).toLowerCase().includes(person.toLowerCase())))
    .map(x => { const [b, l] = alType(x); return { ...x, _b: b, _l: l }; });
  const counts = base.reduce((c, x) => (c[x._b] = (c[x._b] || 0) + 1, c), { all: base.length, unread: base.filter(x => !x.read).length });
  const list = type === "all" ? base : type === "unread" ? base.filter(x => !x.read) : base.filter(x => x._b === type);
  // identical alerts (same title and body) collapse into one card at the newest one
  const groups = [], byKey = {};
  list.forEach(x => { const k = x.title + "\u0000" + x.body; if (byKey[k]) byKey[k].items.push(x); else groups.push(byKey[k] = { key: k, items: [x] }); });
  let lastDay = null;
  const cards = groups.map((g, gi) => { const x = g.items[0], n = g.items.length, unread = g.items.some(i => !i.read), k = alDay(x.ts);
    const head = k !== lastDay ? `<h3 class="al-day">${esc(alDayLabel(k, t0))}</h3>` : ""; lastDay = k;
    const gid = "g" + x.id, expanded = n > 1 && open[gid];
    const acts = `<button type="button" class="btn al-btn" data-alopen="${x.id}">Open</button>${x.kind === "validate" ? `<button type="button" class="btn primary al-btn" data-algo="check">Go to To check</button>` : ""}`;
    return head + `<article class="al-card al-${x._b}${unread ? " unread" : ""}">
      <div class="al-top"><span class="al-type">${unread ? `<span class="al-dot" title="Unread"></span><span class="vh">Unread · </span>` : ""}${esc(x._l)}</span>
        <time class="al-time" datetime="${esc(String(x.ts).replace(" ", "T"))}">${n > 1 ? `<span class="al-n">× ${n}</span> · latest ` : ""}${alTime(x.ts)}</time></div>
      <b class="al-title">${esc(x.title)}</b><div class="al-body">${esc(x.body)}</div>
      ${n > 1 ? `<button type="button" class="billlink al-more" data-algroup="${gid}" aria-expanded="${!!expanded}">${expanded ? "Hide" : "Show all " + n}</button>` : ""}
      ${expanded ? `<ul class="al-list">${g.items.map(i => `<li><span>${esc(alDayLabel(alDay(i.ts), t0))} · ${alTime(i.ts)}</span>${i.read ? "" : `<span class="al-dot" title="Unread"></span>`}</li>`).join("")}</ul>` : ""}
      <div class="al-acts">${acts}</div></article>`; }).join("");
  const filtered = type !== "all" || person || day !== "all";
  const empty = `<div class="emptycard al-empty"><div class="al-ok" aria-hidden="true">✓</div><b>You're all caught up.</b>${filtered ? `<div class="small">No alerts match these filters · <button type="button" class="billlink" data-alreset>clear filters</button></div>` : ""}</div>`;
  const seg = (items, cur, attr, cnt) => `<div class="seg al-seg">${items.map(([k, l]) => `<button type="button" ${attr}="${k}" aria-pressed="${cur === k}">${l}${cnt ? ` <span class="al-c">${cnt[k] || 0}</span>` : ""}</button>`).join("")}</div>`;
  const users = (S.meta && S.meta.users) || [], depts = [...new Set(users.map(u => u.dept))];
  const chip = (name, lbl) => `<button type="button" class="al-chip" data-alp="${esc(name)}" aria-pressed="${person === name}">${name ? avatar(name) : `<span class="avatar al-all" aria-hidden="true">All</span>`}<span>${esc(lbl)}</span></button>`;
  const people = inSheet ? "" : `<div class="al-people" role="group" aria-label="Filter by person">${chip("", "Everyone")}${depts.map(d => `<span class="al-dept">${esc(d)}</span>${users.filter(u => u.dept === d).map(u => chip(u.name, u.name)).join("")}`).join("")}</div>`;
  const unreadAll = all.filter(x => !x.read).length;
  return `<div class="al-wrap"${inSheet ? " data-al-sheet" : ""}>
    <div class="al-markrow"><span class="muted small">${unreadAll ? `${unreadAll} unread` : "No unread alerts"}</span><button type="button" class="btn al-btn" data-almark ${unreadAll ? "" : "disabled"}>Mark all as read</button></div>
    <div class="al-bar">${people}<div class="al-row">${seg(AL_TYPES, type, "data-alt", counts)}${seg(AL_DAYS, day, "data-ald")}</div></div>
    <div class="al-cards">${cards || empty}</div></div>`;
}
function viewAlerts() { return hero("Alerts", "Your last 40 alerts, newest first.") + alertsBody(false); }
function alertsSheet() {   // the bell's side panel (staff)
  const sh = $("#sheet"), top = sh && sh.classList.contains("open") ? sh.scrollTop : 0;
  sheetHtml(`<h2 style="margin:0 0 14px">Alerts</h2>${alertsBody(true)}`); if (top) $("#sheet").scrollTop = top;
}
// One listener for the alert filters and buttons, on the Alerts tab and in the bell panel.
document.addEventListener("click", async (ev) => {
  const el = ev.target.closest && ev.target.closest("[data-alt],[data-ald],[data-alp],[data-algroup],[data-alreset],[data-almark],[data-alopen],[data-algo]");
  if (!el) return; const inSheet = !!el.closest("#sheet"); if (!inSheet && !el.closest("#app")) return;
  const d = el.dataset, redraw = () => inSheet ? alertsSheet() : render();
  const go = (tab) => { if (inSheet) closeSheet(); S.tab = tab; render(); };
  if (d.almark !== undefined) { el.disabled = true; try { await api("/api/alerts/read", {}); await load(); } catch (e) { note("Couldn't mark as read", e.message); } return redraw(); }
  if (d.algo) return go(d.algo);
  if (d.alopen) { const x = ((S.state && S.state.alerts) || []).find(a => String(a.id) === d.alopen); if (!x) return;
    const bill = alBill(x);
    if (isAdmin() && bill) { if (inSheet) closeSheet(); return loadBill(bill); }
    if (isAdmin() && x.task_id && /TASK-\d+/.test(x.title + " " + x.body)) { if (inSheet) closeSheet(); return openTask(x.task_id); }
    return go(x.kind === "validate" ? "check" : "mine"); }
  if (d.algroup) { S.alOpen = S.alOpen || {}; S.alOpen[d.algroup] = !S.alOpen[d.algroup]; return redraw(); }
  if (d.alt) S.alType = d.alt; else if (d.ald) S.alDay = d.ald; else if (d.alp !== undefined) S.alPerson = d.alp;
  else if (d.alreset !== undefined) { S.alType = "all"; S.alDay = "all"; S.alPerson = ""; }
  redraw();
});
