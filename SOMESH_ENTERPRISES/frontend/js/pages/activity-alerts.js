// Pages: Activity and Alerts.
"use strict";
function viewLog() {
  const qtxt = (S.lq || "").toLowerCase(); const ev = (S.pipe ? S.pipe.events : []).filter(e => (S.showDemo !== false || !String(e.bill_id || "").startsWith("DEMO-")) && (!qtxt || (e.text + " " + e.actor + " " + (e.bill_id || "")).toLowerCase().includes(qtxt)));
  return hero("Activity", "Every start, submit, approval and hand-off.") + `<div class="toolbar"><input class="search" id="lq" placeholder="Search by bill, person or stage" value="${esc(S.lq || "")}" aria-label="Search activity"></div><div class="list">${ev.map(e => `<div class="row"><span class="t">${esc(e.ts)}</span><span>${esc(e.text)}</span></div>`).join("") || `<p class="empty">No activity yet.</p>`}</div>`;
}
function viewAlerts() {
  if (isAdmin()) return viewAdminAlertCenter();
  const a = S.state ? S.state.alerts : [];
  return hero("Alerts", "Your last 40 alerts.") + `<div class="list">${a.map(x => `<div class="row ${x.read ? "" : "unread"}"><span class="t">${esc(fmt(x.ts))}</span><span><b>${esc(x.title)}</b><div class="muted small">${esc(x.body)}</div></span></div>`).join("") || `<p class="empty">No alerts yet.</p>`}</div>`;
}
