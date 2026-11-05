// Pages: Activity and Alerts.
"use strict";
// ---------------------------------------------------------- Activity: cards with person / type / day filters
// Filter choices live in S so they survive re-renders: S.actPerson ("" = everyone), S.actType ("all"), S.actDay ("all"), S.actLimit (cards shown).
const ACT_TYPES = [["all", "All"], ["started", "Started"], ["submitted", "Submitted"], ["approved", "Approved"], ["back", "Sent back"], ["overdue", "Overdue"], ["files", "Files"], ["other", "Other"]];
const ACT_DAYS = [["today", "Today"], ["yesterday", "Yesterday"], ["7", "Last 7 days"], ["all", "All"]];
const ACT_PAGE = 60;
// Known event kinds map straight to a type; other kinds fall back to the wording of the text.
const ACT_KIND = { started: "started", claimed: "started", submitted: "submitted", approved: "approved", complete: "approved",
  rejected: "back", sent_back: "back", reject: "back", overdue: "overdue", vault: "files", upload: "files", uploaded: "files", files: "files", assigned: "other", waiting: "other" };
function actType(e) {   // derive a type from the event kind and its wording
  const k = String(e.kind || "").toLowerCase(); if (ACT_KIND[k]) return ACT_KIND[k];
  const s = (k + " " + (e.text || "")).toLowerCase();
  if (/sent back|reject|rework/.test(s)) return "back";
  if (/overdue|past (the )?limit|\blate\b/.test(s)) return "overdue";
  if (/\bapproved?\b|\bapprove\b/.test(s) && !/for approval|to approve/.test(s)) return "approved";
  if (/submit|for approval|for checking|to approve|\bdone\b/.test(s)) return "submitted";
  if (/upload|attach|file|document|vault/.test(s)) return "files";
  if (/start|claim|picked up|began/.test(s)) return "started";
  return "other";
}
const actDayKey = (ts) => String(ts || "").slice(0, 10);
const actShift = (ymd, n) => { const d = new Date(ymd + "T00:00"); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const actTime = (ts) => { const m = /(\d{2}):(\d{2})/.exec(String(ts).slice(11)); if (!m) return ""; const h = +m[1]; return `${h % 12 || 12}:${m[2]} ${h < 12 ? "AM" : "PM"}`; };
function actDayLabel(k, t0) {
  if (k === t0) return "Today"; if (k === actShift(t0, -1)) return "Yesterday";
  const d = new Date(k + "T00:00"); if (isNaN(d)) return k;
  return `${d.toLocaleDateString("en-GB", { weekday: "short" })}, ${d.getDate()} ${d.toLocaleDateString("en-GB", { month: "short" })}`;
}
const actMentions = (e, name) => e.actor === name || String(e.text || "").toLowerCase().includes(name.toLowerCase());
function actText(e) {   // event text with the bill ID and TASK- code turned into links
  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), bill = e.bill_id ? String(e.bill_id) : "", pats = [];
  if (bill) pats.push(reEsc(bill)); if (e.task_id) pats.push("TASK-\\d+");
  const bLink = `<button type="button" class="billlink" data-actbill="${esc(bill)}">${esc(bill)}</button>`;
  if (!pats.length) return esc(e.text);
  let billShown = false;
  const html = String(e.text).split(new RegExp(`(${pats.join("|")})`)).map((p, i) => i % 2 === 0 ? esc(p)
    : p === bill ? (billShown ? esc(p) : (billShown = true, bLink)) : `<button type="button" class="billlink" data-acttask="${esc(String(e.task_id))}">${esc(p)}</button>`).join("");
  return html + (bill && !billShown ? ` <span class="muted">·</span> ${bLink}` : "");
}
function viewLog() {
  const qtxt = (S.lq || "").toLowerCase(), person = S.actPerson || "", type = S.actType || "all", day = S.actDay || "all", limit = S.actLimit || ACT_PAGE;
  const t0 = today(), y0 = actShift(t0, -1), w0 = actShift(t0, -6);
  const inDay = (k) => day === "all" || (day === "today" ? k === t0 : day === "yesterday" ? k === y0 : k >= w0 && k <= t0);
  // everything except the type filter (so the type buttons can show counts)
  const base = (S.pipe ? S.pipe.events : []).filter(e => (S.showDemo !== false || !String(e.bill_id || "").startsWith("DEMO-"))
    && (!qtxt || (e.text + " " + e.actor + " " + (e.bill_id || "")).toLowerCase().includes(qtxt))
    && (!person || actMentions(e, person)) && inDay(actDayKey(e.ts))).map(e => ({ ...e, _t: actType(e) }));
  const counts = base.reduce((c, e) => (c[e._t] = (c[e._t] || 0) + 1, c), { all: base.length });
  const ev = type === "all" ? base : base.filter(e => e._t === type);
  // repeated identical events in a row collapse into one card with "× N"
  const cards = []; ev.forEach(e => { const last = cards[cards.length - 1]; if (last && last.text === e.text) last._n++; else cards.push({ ...e, _n: 1 }); });
  const shown = cards.slice(0, limit), label = Object.fromEntries(ACT_TYPES);
  let lastDay = null;
  const list = shown.map(e => { const k = actDayKey(e.ts), demo = String(e.bill_id || "").startsWith("DEMO-");
    const head = k !== lastDay ? `<h3 class="act-day">${esc(actDayLabel(k, t0))}</h3>` : ""; lastDay = k;
    return head + `<article class="act-card"><div class="act-head">${e.actor ? `${avatar(e.actor)}<b>${esc(e.actor)}</b>` : `<b class="muted">System</b>`}
      <span class="act-type t-${e._t}"><span class="act-dot" aria-hidden="true"></span>${label[e._t]}</span>${demo ? demoTag({ demo: true }) : ""}</div>
      <time class="act-time" datetime="${esc(String(e.ts).replace(" ", "T"))}">${actTime(e.ts)}${e._n > 1 ? `<span class="act-n" title="Happened ${e._n} times in a row">× ${e._n}</span>` : ""}</time>
      <div class="act-text">${actText(e)}</div></article>`; }).join("");
  const dayWords = { today: " today", yesterday: " yesterday", "7": " in the last 7 days", all: "" }[day];
  const empty = `<div class="emptycard act-empty"><b>No ${type === "all" ? "" : label[type].toLowerCase() + " "}activity${person ? " for " + esc(person) : ""}${dayWords}${qtxt ? ` matching “${esc(S.lq)}”` : ""}.</b><div class="small" style="margin-top:4px">Try another person, type or day${person || type !== "all" || day !== "all" || qtxt ? ` · <button type="button" class="billlink" data-actreset>clear filters</button>` : ""}</div></div>`;
  const users = (S.meta && S.meta.users) || [], depts = [...new Set(users.map(u => u.dept))];
  const chip = (name, lbl) => `<button type="button" class="act-chip" data-actp="${esc(name)}" aria-pressed="${person === name}">${name ? avatar(name) : `<span class="avatar act-all" aria-hidden="true">All</span>`}<span>${esc(lbl)}</span></button>`;
  const people = `<div class="act-people" role="group" aria-label="Filter by person">${chip("", "Everyone")}${depts.map(d => `<span class="act-dept">${esc(d)}</span>${users.filter(u => u.dept === d).map(u => chip(u.name, u.name)).join("")}`).join("")}</div>`;
  const seg = (items, cur, attr, cnt) => `<div class="seg act-seg">${items.map(([k, l]) => `<button type="button" ${attr}="${k}" aria-pressed="${cur === k}">${l}${cnt ? ` <span class="act-c">${cnt[k] || 0}</span>` : ""}</button>`).join("")}</div>`;
  return hero("Activity", "Every start, submit, approval and hand-off.") +
    `<div class="act-bar">${people}
      <div class="act-row">${seg(ACT_TYPES, type, "data-actt", counts)}${seg(ACT_DAYS, day, "data-actd")}
        <input class="search" id="lq" placeholder="Search by bill, person or stage" value="${esc(S.lq || "")}" aria-label="Search activity">${demoToggle()}</div></div>
    <div class="act-list">${list || empty}</div>
    ${cards.length > limit ? `<div class="act-more"><button type="button" class="btn" data-actmore>Show more <span class="muted">(${cards.length - limit} left)</span></button></div>` : ""}`;
}
// One listener for the Activity filters and links (no changes needed in shell.js).
document.addEventListener("click", (ev) => {
  const el = ev.target.closest && ev.target.closest("[data-actp],[data-actt],[data-actd],[data-actmore],[data-actreset],[data-actbill],[data-acttask]");
  if (!el || !el.closest("#app")) return;
  const d = el.dataset;
  if (d.actbill !== undefined) return loadBill(d.actbill);
  if (d.acttask !== undefined) return openTask(Number(d.acttask) || d.acttask);
  if (d.actmore !== undefined) S.actLimit = (S.actLimit || ACT_PAGE) + ACT_PAGE;
  else { S.actLimit = ACT_PAGE;
    if (d.actp !== undefined) S.actPerson = d.actp; else if (d.actt) S.actType = d.actt; else if (d.actd) S.actDay = d.actd;
    else if (d.actreset !== undefined) { S.actPerson = ""; S.actType = "all"; S.actDay = "all"; S.lq = ""; } }
  render();
});
function viewAlerts() {
  const a = S.state ? S.state.alerts : [];
  return hero("Alerts", "Your last 40 alerts.") + `<div class="list">${a.map(x => `<div class="row ${x.read ? "" : "unread"}"><span class="t">${esc(fmt(x.ts))}</span><span><b>${esc(x.title)}</b><div class="muted small">${esc(x.body)}</div></span></div>`).join("") || `<p class="empty">No alerts yet.</p>`}</div>`;
}
