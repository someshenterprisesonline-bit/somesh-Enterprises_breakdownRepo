// Page: Automation.
"use strict";
// ---------------------------------------------------------- admin: automation
function viewAuto() {
  const d = S.autoCfg; if (!d) return hero("Automation", "") + skeleton("table", 4);
  const a = d.settings;
  const sw = (id, on, title, text) => `<label class="switch"><input type="checkbox" id="${id}" ${on ? "checked" : ""}><span><b>${title}</b><span class="muted small" style="display:block">${text}</span></span></label>`;
  return hero("Automation", "Let the app move work along on its own. Changes apply straight away.") +
    `<div class="panel">${sw("aStart", a.auto_start, "Start tasks automatically", "A new task is started straight away for the person in its team with the fewest tasks in progress, so nobody has to press Start. They get the alert “started for you”.")}
      ${sw("aEsc", a.escalate_to_admins, "Escalate overdue work to admins", "When a task passes its time limit, the admins get the red alert too, not only the person doing it and the checker.")}
      <div class="switch"><span style="width:20px"></span><span style="flex:1"><b>Repeat reminders</b><span class="muted small" style="display:block">Keep reminding people about overdue work, and checkers about work waiting for them.</span>
        <select class="in" id="aRem" style="width:auto;margin-top:8px">${[[0, "Off"], [1, "Every hour"], [2, "Every 2 hours"], [4, "Every 4 hours"], [8, "Every 8 hours"], [24, "Once a day"]].map(([v, l]) => `<option value="${v}" ${Number(a.remind_every_hours) === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${S.meta.demo_speed > 1 ? `<span class="muted small"> (demo time ×${S.meta.demo_speed}: an hour passes in ${Math.round(60 / S.meta.demo_speed * 60)} s)</span>` : ""}</span></div>
      <div class="switch"><span style="width:20px"></span><span style="flex:1"><b>Open the month's bills automatically</b><span class="muted small" style="display:block">On this day each month, open a bill for every active contract in the Contract Register (${d.active_contracts} active now). Clients that already have a bill this month are skipped.</span>
        <span class="row2" style="margin-top:8px">Day <select class="in" id="aDay" style="flex:0 0 auto;width:auto;min-width:0">${[0, ...Array.from({ length: 28 }, (_, i) => i + 1)].map(v => `<option value="${v}" ${Number(a.monthly_open_day) === v ? "selected" : ""}>${v ? v : "Off"}</option>`).join("")}</select>
        at <select class="in" id="aHour" style="flex:0 0 auto;width:auto;min-width:0">${Array.from({ length: 24 }, (_, i) => i).map(v => `<option value="${v}" ${Number(a.monthly_open_hour) === v ? "selected" : ""}>${String(v).padStart(2, "0")}:00</option>`).join("")}</select>
        ${a.last_monthly_open ? `<span class="muted small">Last run: ${esc(a.last_monthly_open)}</span>` : ""}</span></span></div>
      <div class="row2" style="margin-top:14px"><button class="btn" id="aOpenNow" type="button">Open bills for all active contracts now</button><span style="flex:1"></span><button class="btn primary" id="aSave" type="button">Save automation</button></div></div>
    <p class="muted small" style="margin-top:14px">Also automatic already: hand-off to the next team on approval, waiting for all inputs, the S04-style decision branch, overdue alerts, the Master Tracker, contract checks and Vault filing.</p>`;
}
function wireAuto() {
  $("#aSave").onclick = async () => {
    const settings = { auto_start: $("#aStart").checked, escalate_to_admins: $("#aEsc").checked, remind_every_hours: Number($("#aRem").value), monthly_open_day: Number($("#aDay").value), monthly_open_hour: Number($("#aHour").value) };
    try { await api("/api/automation", { settings }); S.autoCfg = await api("/api/automation"); render(); note("Automation saved", "The new settings are live.", "approved"); } catch (e) { note("Couldn't save", e.message); }
  };
  $("#aOpenNow").onclick = async () => { try { const r = await api("/api/automation/open-now", {}); note("Bills opened", r.bills.length ? r.bills.join(", ") : "Every active contract already has a bill this month.", "approved"); load(); } catch (e) { note("Couldn't open bills", e.message); } };
}
