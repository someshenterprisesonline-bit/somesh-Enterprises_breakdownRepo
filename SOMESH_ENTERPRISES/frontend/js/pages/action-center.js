// Admin operational projections; all mutations use authorized, existing workflow helpers.
"use strict";
const sacLabels = { all: "Needs Your Attention", overdue: "Overdue tasks", approvals: "Pending approvals", no_activity: "Availability checks", completed_today: "Completed on selected date", approaching: "Approaching deadline", returned: "Returned for correction" };
let sacSequence = 0, sacSearchTimer;
function sacUrl(suffix = "") {
  const f = S.sacFilters || {};
  return "/api/action-center" + suffix + "?" + new URLSearchParams({ date: f.date || today(), department: f.department || "", person: f.person || "", workload: f.workload || "all", sort: f.sort || "attention", q: f.q || "" });
}
async function sacLoad(paint = true) {
  if (!S.user || !isAdmin()) return;
  const sequence = ++sacSequence, user = S.user, token = S.token;
  try {
    const report = await api(sacUrl());
    if (sequence !== sacSequence || S.user !== user || S.token !== token) return;
    S.smartAction = report; S.sacError = "";
  } catch (e) { if (sequence === sacSequence && S.user === user) S.sacError = e.message; }
  if (paint && S.user === user && S.tab === "action") render();
}
function sacSelect(attr, options, value) { return `<select class="in" ${attr}>${options.map(([key, label]) => `<option value="${esc(key)}" ${key === (value || "") ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>`; }
function sacVisibleRows() {
  const d = S.smartAction, focus = S.sacFocus || "all";
  if (!d) return [];
  if (focus === "completed_today") return d.tasks.filter(r => r.completed_today);
  if (focus === "returned") return d.tasks.filter(r => r.returned);
  if (focus === "approvals") return d.tasks.filter(r => r.approval);
  return focus === "all" ? d.queue : d.queue.filter(r => focus === "no_activity" ? r.category === focus : r[focus]);
}
function sacWorkPreview(person) {
  const rows = (S.smartAction?.tasks || []).filter(r => r.people.includes(person) && r.pending);
  return rows.slice(0, 3).map(r => `<div><b>${esc(r.code)}</b> ${esc(r.task)} · ${esc(r.status_label)}</div>`).join("") +
    (rows.length > 3 ? `<div>${rows.length - 3} more open tasks in this scope</div>` : "");
}
function viewActionCenter() {
  const d = S.smartAction, f = S.sacFilters || {};
  const controls = `<button class="btn" id="sacRefresh" type="button">Refresh</button><details class="sac-export"><summary class="btn primary">Export</summary><div><button class="btn" type="button" data-sac-export="xlsx">Export as Excel (.xlsx)</button><button class="btn" type="button" data-sac-export="pdf">Export as PDF (.pdf)</button></div></details>`;
  let html = hero("Action Center", "A shared operational view. Review facts, then choose the next action.", controls);
  if (S.sacError) html += `<div class="sac-error" role="alert">Couldn't refresh: ${esc(S.sacError)}. Use Refresh to retry; displayed figures may be older.</div>`;
  if (!d) return html + skeleton("cards", 6);
  const metrics = [["overdue", "Overdue Tasks"], ["approvals", "Pending Approvals"], ["no_activity", "No Recorded Activity"], ["completed_today", "Completed Tasks"], ["approaching", "Approaching Deadline"], ["returned", "Returned for Correction"]];
  html += `<div class="sac-filters"><label>Date<input class="in" type="date" id="sacDate" data-sac-filter="date" value="${esc(f.date || d.date)}" max="${today()}"></label>
    <label>Department${sacSelect('data-sac-filter="department" aria-label="Department"', [["", "All departments"], ...d.departments.map(v => [v, v])], f.department)}</label>
    <label>Employee${sacSelect('data-sac-filter="person" aria-label="Employee"', [["", "All employees"], ...d.person_options.map(v => [v, v])], f.person)}</label>
    <label>Workload${sacSelect('data-sac-filter="workload" aria-label="Workload"', [["all", "All workloads"], ["open", "With open work"], ["overloaded", "Review workload"], ["no_activity", "Check availability"]], f.workload || "all")}</label>
    <label>Sort workload${sacSelect('data-sac-filter="sort" aria-label="Sort workload"', [["attention", "Needs attention first"], ["name", "Employee name"], ["time", "Tracked time"], ["pending", "Pending tasks"]], f.sort || "attention")}</label>
    <label class="sac-search-label">Search<input class="search" id="sacSearch" placeholder="Employee, task, team or bill" value="${esc(f.q || "")}"></label></div>
    <div class="sac-metrics">${metrics.map(([key, label]) => `<button class="sac-metric sac-${key}" type="button" data-sac-focus="${key}" aria-pressed="${S.sacFocus === key}" title="${key === 'no_activity' ? esc(d.activity_note) : 'Show underlying records'}"><span>${label}</span><b>${d.counts[key === "approvals" ? "approval" : key]}</b><small>${key === "no_activity" ? d.activity_expected ? "Open work · verify availability" : "Checks paused outside expected periods" : ["completed_today"].includes(key) ? esc(d.date) : "Current outstanding work"}</small></button>`).join("")}</div>
    <p class="muted small">${esc(d.scope_note)} Updated ${esc(d.server_now)} · SSE updates and a 30-second refresh.</p>
    <details class="sac-section" open><summary>${d.date === today() ? "Today's Operations Summary" : "Operations Summary · " + esc(d.date)}</summary><div class="sac-summary-body"><p><b>${d.counts.assigned_today}</b> assigned · <b>${d.counts.completed_today}</b> completed · <b>${d.counts.approval}</b> awaiting approval · <b>${d.counts.overdue}</b> overdue.</p>
    <p>${d.counts.active_people} of ${d.counts.people} displayed people have recorded activity on ${esc(d.date)}. Current follow-ups: ${d.counts.returned} corrections and ${d.counts.documents} approved tasks awaiting documents / End task.</p>
    <div class="sac-recommendations">${d.recommendations.map(r => `<button class="btn" type="button" data-sac-focus="${r.filter}">${esc(r.text)} <span aria-hidden="true">→</span></button>`).join("") || '<p class="muted">No priority follow-ups in this scope.</p>'}</div></div></details>
    <section class="sac-section" aria-label="Needs Your Attention"><div class="sac-section-head"><h2>${esc(sacLabels[S.sacFocus] || sacLabels.all)}</h2>${S.sacFocus && S.sacFocus !== "all" ? '<button class="btn" type="button" data-sac-focus="all">Show all attention items</button>' : ""}</div>
    <div class="sac-queue">${sacVisibleRows().map(sacQueueCard).join("") || '<p class="empty">No matching follow-ups. Try another filter or date.</p>'}</div></section>
    <details class="sac-section" open><summary>Employee Workload <span class="muted small">${d.people.length} people</span></summary><div class="sac-workload scroll"><table><thead><tr><th>Employee</th><th>Department</th><th>Assigned on date</th><th>Completed on date</th><th>Pending now</th><th>Overdue now</th><th>Tracked time</th><th>Workload review</th></tr></thead><tbody>${d.people.map(p => `<tr><td><button class="sac-person" type="button" data-sac-person="${esc(p.person)}">${avatar(p.person)}<b>${esc(p.person)}</b></button></td><td>${esc(p.dept)}</td><td>${p.assigned}</td><td>${p.completed}</td><td>${p.pending}</td><td class="${p.overdue ? 'sac-danger' : ''}">${p.overdue}</td><td>${clock(p.seconds)}</td><td><div class="sac-load-meter" role="img" aria-label="${esc(p.workload_reason)}"><i style="width:${Math.min(100, p.capacity_seconds ? p.remaining_seconds / p.capacity_seconds * 100 : 0)}%"></i></div><span class="${p.overloaded ? 'sac-danger' : 'muted'} small">${p.overloaded ? 'Review capacity' : 'No threshold exceeded'}</span><div class="sac-hover-note">${sacWorkPreview(p.person)}${esc(p.workload_reason)}. ${dur(p.remaining_seconds)} remaining configured limits; ${dur(p.capacity_seconds)} normal day capacity. Limits are budgets, not effort forecasts.</div></td></tr>`).join("") || '<tr><td colspan="8" class="empty">No employees in this scope.</td></tr>'}</tbody></table></div><p class="muted small sac-explanation">${esc(d.activity_note)} Workload is a planning indicator, not a performance score. Department filters task team in the queue and employee team in workload. Exports include the filtered summary, full attention queue and workload.</p></details>`;
  return html;
}
function sacQueueCard(r) {
  return `<article class="sac-item ${r.overdue ? "sac-late" : r.can_review ? "sac-review" : ""}"><div class="sac-item-main"><div class="sac-item-meta">${esc(r.person)} · ${esc(r.dept)}${r.code ? " · " + esc(r.code) : ""}</div><h3>${esc(r.task)}</h3><div class="sac-item-status"><span class="pill">${esc(r.status_label)}</span>${r.overdue ? `<b class="sac-danger">${Math.floor(r.late_seconds / 60)} working min overdue</b>` : ""}<span>Deadline: ${r.due ? esc(fmt(r.due)) : "–"}</span></div><p class="muted small">${esc(r.recommendation)}</p>${r.note ? `<details><summary class="small">Correction note</summary><p>${esc(r.note)}</p></details>` : ""}</div>
    <div class="sac-item-actions">${r.id ? `<button class="btn ${r.can_review ? "primary" : ""}" type="button" data-sac-task="${r.id}">${r.can_review ? "Review submission" : "Open task"}</button>` : ""}<button class="btn" type="button" data-sac-person="${esc(r.people?.[0] || r.person)}">Open employee Tracker</button>${r.id ? `<button class="btn" type="button" data-sac-alerts="${r.id}">Related alerts</button>` : ""}</div></article>`;
}
function wireActionCenter() {
  $("#sacRefresh").onclick = () => sacLoad();
  app.querySelectorAll("[data-sac-filter]").forEach(el => el.onchange = () => { S.sacFilters = { ...S.sacFilters, [el.dataset.sacFilter]: el.value }; sacLoad(); });
  const search = $("#sacSearch"); if (search) search.oninput = () => { S.sacFilters = { ...S.sacFilters, q: search.value }; clearTimeout(sacSearchTimer); sacSearchTimer = setTimeout(() => sacLoad(), 250); };
  app.querySelectorAll("[data-sac-focus]").forEach(b => b.onclick = () => { S.sacFocus = b.dataset.sacFocus; render(); });
  app.querySelectorAll("[data-sac-task]").forEach(b => b.onclick = () => sacOpenTask(Number(b.dataset.sacTask)));
  app.querySelectorAll("[data-sac-person]").forEach(b => b.onclick = () => sacOpenTracker(b.dataset.sacPerson));
  app.querySelectorAll("[data-sac-alerts]").forEach(b => b.onclick = () => {
    const task = S.smartAction.tasks.find(r => r.id === Number(b.dataset.sacAlerts));
    S.acQuery = ""; S.acTaskFilter = task.id; S.acFilter = "all"; S.acShowSnoozed = true; S.tab = "alerts"; render(); refreshAlertCenter();
  });
  app.querySelectorAll("[data-sac-export]").forEach(b => b.onclick = () => sacDownload(b.dataset.sacExport));
}
async function sacOpenTracker(person) {
  const user = S.user, token = S.token;
  try {
    S.trDate = S.sacFilters?.date || today(); const report = await api(trUrl());
    if (S.user !== user || S.token !== token) return;
    S.tr = report; S.tab = "tracker"; S.tq = person; render(); trOpenEmployee(person);
  } catch (e) { note("Couldn't open Tracker", e.message); }
}
async function sacOpenTask(id) {
  const user = S.user, token = S.token;
  try {
    const t = (await api(`/api/action-center/task/${id}`)).task;
    if (S.user !== user || S.token !== token) return;
    sheetHtml(`<div class="code">${esc(t.stage)} · ${esc(t.dept)}</div><h2>${esc(t.stage_name)}</h2><dl class="facts"><dt>Employee</dt><dd>${esc(t.assignee || t.owners.join(", "))}</dd><dt>Approver</dt><dd>${esc(t.validator)}</dd><dt>Status</dt><dd>${esc(STATUS[t.status] || t.status)}</dd><dt>Deadline</dt><dd>${esc(fmt(t.due_at))}</dd></dl><h3>Submission</h3><p class="sac-note">${esc(t.output_note || "No submission yet.")}</p>${t.decision_note ? `<h3>Correction note</h3><p class="sac-note">${esc(t.decision_note)}</p>` : ""}${t.files.length ? fileList(t.files) : '<p class="muted small">No attached documents.</p>'}<div class="actions">${t.status === "submitted" && t.validator === S.user ? '<button class="btn good" type="button" id="sacApprove">Approve</button><button class="btn bad" type="button" id="sacReturn">Return for correction</button>' : ""}${["assigned", "in_progress"].includes(t.status) ? '<button class="btn" type="button" id="sacReassign">Reassign task</button>' : ""}${t.bill_id ? `<button class="btn" type="button" id="sacBill">Open bill</button>` : ""}</div><p class="small muted" id="sacTaskError" role="alert"></p>`);
    $("#sheet").querySelectorAll("[data-preview]").forEach(b => b.onclick = () => showPreview(b.dataset.preview));
    const approve = $("#sacApprove"), reject = $("#sacReturn"), reassign = $("#sacReassign"), bill = $("#sacBill");
    if (approve) approve.onclick = () => sacReview(t, "approve");
    if (reject) reject.onclick = () => sacReview(t, "reject");
    if (reassign) reassign.onclick = () => sacReassign(t);
    if (bill) bill.onclick = () => loadBill(t.bill_id);
  } catch (e) { note("Couldn't open task", e.message); }
}
const sacMutating = new Set();
function sacConfirm(t, html, execute) {
  const user = S.user, token = S.token;
  dialog(html, async data => {
    if (S.user !== user || S.token !== token || sacMutating.has(t.id)) return;
    sacMutating.add(t.id);
    try { await execute(data); if (S.user !== user || S.token !== token) return; closeSheet(); await load(); }
    catch (e) { if (S.user !== user || S.token !== token) return; const error = $("#sacTaskError"); if (error) error.textContent = e.message; else note("Couldn't update task", e.message); }
    finally { sacMutating.delete(t.id); }
  });
}
function sacReview(t, action) {
  sacConfirm(t, `<h3>${action === "approve" ? "Approve" : "Return"} ${esc(t.stage_name)}?</h3><label>Review note${action === "reject" ? " (required)" : " (optional)"}<textarea class="in" name="note" ${action === "reject" ? "required" : ""}></textarea></label>`, data => api(`/api/tasks/${t.id}/${action}`, { note: data.get("note") || "" }));
}
function sacReassign(t) {
  const people = S.meta.users.filter(u => u.dept === t.dept && u.name !== t.assignee);
  sacConfirm(t, `<h3>Reassign ${esc(t.stage_name)}?</h3><p class="muted">Existing time records and the approver are retained. A running timer transfers to the selected employee. The task must still match the state shown here.</p><label>New employee${sacSelect('name="person" required', [["", "Choose employee"], ...people.map(u => [u.name, u.name])], "")}</label>`, data => api("/api/action-center/reassign", { task_id: t.id, person: data.get("person"), confirmed: true, expected: { status: t.status, assignee: t.assignee, claimed_at: t.claimed_at, owners: t.owners } }));
}
async function sacDownload(fmt) {
  app.querySelector(".sac-export")?.removeAttribute("open");
  try {
    const response = await fetch(sacUrl(`/export.${fmt}`), { headers: hdrs() });
    if (!response.ok) throw new Error((await response.json()).error || "Export failed");
    const url = URL.createObjectURL(await response.blob()), link = document.createElement("a");
    link.href = url; link.download = `Operations_Summary_${S.smartAction.date}.${fmt}`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { note("Couldn't export", e.message); }
}
