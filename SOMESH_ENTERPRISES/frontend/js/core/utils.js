// Formatting and time helpers (lunch-aware timers, dates, file URLs). Used by every page.
"use strict";
// ---------------------------------------------------------- views
const me = () => S.meta.users.find(u => u.name === S.user) || {};
const isAdmin = () => !!me().admin;
const fmt = (s) => s ? new Date(s.replace(" ", "T")).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" }) : "";
// The server sends local times without a zone; this keeps due times right even if this PC's clock or zone differs.
const syncClock = (serverNow) => { if (serverNow) S.skew = new Date(serverNow.replace(" ", "T")) - Date.now(); };
const NOW = () => Date.now() + (S.skew || 0);
const pts = (v) => v ? new Date(String(v).replace(" ", "T")).getTime() : null;
function lunchWin(dayMs) {
  const L = (S.meta && S.meta.lunch) || {}; if (L.enabled === false) return null;
  const d = new Date(dayMs); const at = (hm) => { const [h, m] = (hm || "13:00").split(":").map(Number); const x = new Date(d); x.setHours(h, m, 0, 0); return x.getTime(); };
  const a = at(L.start || "13:00"), b = at(L.end || "14:00"); return b > a ? [a, b] : null;
}
function netSec(fromMs, toMs) {   // seconds between two times, lunch excluded (same rule as the server)
  if (!fromMs || toMs <= fromMs) return 0;
  let tot = (toMs - fromMs) / 1000; const d = new Date(fromMs); d.setHours(0, 0, 0, 0);
  for (let day = d.getTime(); day <= toMs; day += 86400000) { const w = lunchWin(day); if (w) tot -= Math.max(0, (Math.min(toMs, w[1]) - Math.max(fromMs, w[0])) / 1000); }
  return Math.max(0, Math.floor(tot));
}
const lunchNow = () => { const w = lunchWin(NOW()); return !!(w && NOW() >= w[0] && NOW() < w[1]); };
const clock = (sec) => { sec = Math.max(0, Math.floor(sec)); return `${Math.floor(sec / 3600)}:${String(Math.floor(sec % 3600 / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`; };
const dur = (sec) => { sec = Math.floor(sec || 0); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60); return h ? `${h} h ${String(m).padStart(2, "0")} min` : sec < 60 && sec > 0 ? `${sec} s` : `${m} min`; };
const ampm = (hm) => { const [h, m] = hm.split(":").map(Number); return `${(h % 12) || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
// live timers: data-base = seconds already counted, data-from = moment the running part started
const tick = (base, from, cls) => `<span class="${cls || "timer"}" data-tick data-base="${Math.floor(base || 0)}" data-from="${from ? esc(from) : ""}">${clock((base || 0) + (from ? netSec(pts(from), NOW()) : 0))}</span>`;
function ticker() {
  document.querySelectorAll("[data-tick]").forEach(e => { const f = e.dataset.from; e.textContent = clock(Number(e.dataset.base) + (f ? netSec(pts(f), NOW()) : 0)); });
  const L = (S.meta && S.meta.lunch) || {}, lock = !!(S.user && S.meta && !isAdmin() && lunchNow());
  const box = $("#lunch"); if (box) { box.classList.toggle("show", lock);
    if (lock) { const w = lunchWin(NOW()); $("#lunchTxt").textContent = `${ampm(L.start)} – ${ampm(L.end)} · opens again in ${Math.ceil((w[1] - NOW()) / 60000)} min`; } }
  const ln = S.user && S.meta ? lunchNow() : false; if (S.wasLunch !== undefined && ln !== S.wasLunch) { S.wasLunch = ln; load(); } else S.wasLunch = ln;
}
const isLate = (t) => (t.status === "assigned" || t.status === "in_progress") && new Date(t.due_at.replace(" ", "T")) < NOW();
function dueText(t) {
  const due = new Date(t.due_at.replace(" ", "T")), start = new Date((t.created_at || t.due_at).replace(" ", "T"));
  const ms = due - NOW(); const m = Math.round(Math.abs(ms) / 60000);
  const span = m >= 120 ? Math.round(m / 60) + " h" : m + " min";
  const used = Math.min(1, Math.max(0, (NOW() - start) / Math.max(1, due - start)));
  const cls = ms < 0 ? "over" : used >= 0.75 ? "warn" : "";
  const label = ms < 0 ? `<span class="pill p-late">Overdue by ${span}</span>` : used >= 0.75 ? `<span class="pill p-soon">Due soon · ${span} left</span>` : `<span class="muted small">Due in ${span}</span>`;
  return `<div style="display:flex;gap:10px;align-items:center">${label}<div class="prog time ${cls}" style="flex:1" title="${Math.round(used * 100)}% of the time limit used"><i style="width:${Math.round(used * 100)}%"></i></div></div>`;
}
const billBtn = (id, client) => !id ? `<span class="muted">Task from the admin</span>` : (isAdmin() ? `<button class="billlink" type="button" data-bill="${esc(id)}">${esc(id)}</button>` : esc(id)) + (client ? " · " + esc(client) : "");
const STATUS = { assigned: "To start", in_progress: "In progress", submitted: "Being checked", approved: "Approved" };
// moved here from page files because every page uses them
const canStore = () => isAdmin() || /data center/i.test(me().dept || "");
const fileUrl = (p) => withT("/files/" + p.split("/").map(encodeURIComponent).join("/"));
const kb = (n) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const dshort = (v) => { if (!v) return ""; const d = new Date(String(v).replace(" ", "T")); return isNaN(d) ? String(v) : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }); };
const trUrl = () => `/api/tracker?date=${S.trDate || today()}${S.showDemo !== false ? "&demo=1" : ""}`;
const ttUrl = () => `/api/timetable?date=${S.ttDate || today()}${S.showDemo !== false ? "&demo=1" : ""}`;
const today = () => { const d = new Date(NOW()); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const kbs = (n) => n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const fileHref = (p) => fileUrl(p);
