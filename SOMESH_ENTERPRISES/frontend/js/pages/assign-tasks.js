// Page: Assign tasks (give tasks directly, list, delete).
"use strict";
// ---------------------------------------------------------- admin: give tasks directly
function asgRow(i) {
  const people = S.meta.users, depts = [...new Set(people.map(u => u.dept))];
  const bills = (S.adhoc && S.adhoc.bills) || [];
  return `<tr data-row="${i}"><td style="width:30%"><input class="in" data-f="title" placeholder="What needs doing" aria-label="Task"></td>
    <td><select class="in" data-f="who" aria-label="Who does it"><option value="">Who does it…</option><optgroup label="Person">${people.map(u => `<option value="${esc(u.name)}">${esc(u.name)}</option>`).join("")}</optgroup>
      <optgroup label="Anyone in a department (first to start takes it)">${depts.map(d => `<option value="dept:${esc(d)}">Anyone in ${esc(d)}</option>`).join("")}</optgroup></select></td>
    <td><select class="in" data-f="checker" aria-label="Who approves"><option value="">Approver…</option>${people.map(u => `<option ${u.name === S.user ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select></td>
    <td style="width:90px"><input class="in" data-f="hours" type="number" min="0.5" step="0.5" value="4" aria-label="Hours"></td>
    <td style="white-space:nowrap"><label class="small"><input type="checkbox" data-f="docs" style="accent-color:#0071e3"> Needs docs</label></td>
    <td><select class="in" data-f="bill" aria-label="Bill (optional)"><option value="">No bill</option>${bills.map(b => `<option value="${esc(b.id)}">${esc(b.id)} · ${esc(b.client)}</option>`).join("")}</select></td></tr>`;
}
function viewAssign() {
  const d = S.adhoc; if (!d) return hero("Assign tasks", "") + skeleton("table", 5);
  const rows = d.tasks.map(t => `<div class="row" style="grid-template-columns:110px 1fr 160px 260px"><span class="t">${esc(t.stage)}</span><span><b>${esc(t.stage_name)}</b><div class="muted small">${esc((t.assignee || t.owners.join(", ")))} → checked by ${esc(t.validator)}${t.bill_id ? " · " + esc(t.bill_id) : ""}</div></span>
    <span class="small">${t.status === "approved" ? "Done " + esc(fmt(t.decided_at)) : t.status === "submitted" ? "With checker" : isLate(t) ? `<span class="pill p-late">Overdue</span>` : "Due " + esc(fmt(t.due_at))}</span><span style="display:flex;gap:6px;align-items:center;flex-wrap:wrap"><span class="pill p-${t.status === "approved" && t.adhoc && !t.ended_at ? "docs" : t.status}">${t.status === "approved" && t.adhoc ? (t.ended_at ? "Ended" : "Adding documents") : STATUS[t.status] || t.status}</span>${docsBtn("as" + t.id, `${t.stage} ${t.stage_name} · ${t.assignee || ""}`, t.files)}<button class="btn bad" type="button" data-deltask="${t.id}" style="padding:4px 12px;font-size:13px" aria-label="Delete ${esc(t.stage)}">Delete</button></span></div>`).join("");
  return hero("Assign tasks", "Give tasks directly. The person presses Start (timer runs), Done (sent to you), and after your approval uploads the documents and ends it before moving to the next task.") +
    `<div class="panel scroll"><table class="asg"><thead><tr><th style="text-align:left">Task</th><th style="text-align:left">Who</th><th style="text-align:left">Approver</th><th style="text-align:left">Hours</th><th style="text-align:left">Documents</th><th style="text-align:left">Bill</th></tr></thead><tbody id="asgBody">${[0, 1, 2].map(asgRow).join("")}</tbody></table>
     <div class="row2" style="margin-top:6px"><button class="btn" id="asgAdd" type="button">＋ Add row</button><span style="flex:1"></span><button class="btn primary" id="asgGo" type="button">Give these tasks</button></div></div>
     <h2>Tasks given so far</h2><div class="list">${rows || `<p class="empty">None yet.</p>`}</div>`;
}
function wireAssign() {
  let n = 3;
  $("#asgAdd").onclick = () => $("#asgBody").insertAdjacentHTML("beforeend", asgRow(n++));
  $("#asgGo").onclick = async () => {
    const tasks = [...document.querySelectorAll("#asgBody tr")].map(tr => Object.fromEntries([...tr.querySelectorAll("[data-f]")].map(e => [e.dataset.f, e.type === "checkbox" ? e.checked : e.value.trim()])))
      .filter(r => r.title || r.who);
    if (!tasks.length) return note("Nothing to give", "Fill in at least one row.");
    try { const r = await api("/api/assign", { tasks }); note("Tasks given", `${r.codes.length} task${r.codes.length > 1 ? "s" : ""} sent: ${r.codes.join(", ")}`, "approved"); S.adhoc = await api("/api/adhoc"); render(); }
    catch (e) { note("Couldn't give the tasks", e.message); }
  };
}
