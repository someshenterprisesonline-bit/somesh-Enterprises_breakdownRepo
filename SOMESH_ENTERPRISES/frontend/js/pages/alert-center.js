// Admin alerts use the existing recipient-scoped SSE stream and workflow endpoints.
"use strict";
const acData = () => S.alertCenter || { groups: [], counts: { unread: 0, urgent: 0, approvals: 0, updates: 0, total: 0, total_unread: 0, snoozed: 0 } };
const acGroup = id => acData().groups.find(g => g.records.some(a => a.id === Number(id)));
function acRelative(stamp) {
  const minutes = Math.max(0, Math.floor((NOW() - pts(stamp)) / 60000));
  return minutes < 1 ? "Just now" : minutes < 60 ? `${minutes}m ago` : minutes < 1440 ? `${Math.floor(minutes / 60)}h ago` : `${Math.floor(minutes / 1440)}d ago`;
}
const acTime = stamp => !stamp ? `<span class="ac-absolute">Time unavailable</span>` : `<time datetime="${esc(stamp.replace(" ", "T"))}" title="${esc(stamp)}">${acRelative(stamp)}</time><span class="ac-absolute">${esc(stamp)}</span>`;
function acCard(g, compact = false) {
  if (compact) return acIslandCard(g);
  const a = g.latest, t = g.task, expanded = S.acExpanded?.has(g.key);
  return `<article class="ac-card ac-${g.category} ${g.unread ? "is-unread" : ""}" data-ac-group="${esc(g.key)}">
    <div class="ac-card-top"><span class="ac-kind">${g.urgent ? "Urgent" : g.can_review ? "Approval" : g.priority === 2 ? "Contract / compliance" : "Update"}</span>${g.unread ? `<span class="ac-unread-dot" aria-label="Unread"></span>` : ""}<span class="ac-time">${acTime(a.ts)}</span></div>
    <details data-ac-detail="${esc(g.key)}" ${expanded ? "open" : ""}><summary><b>${esc(a.title)}</b><span class="ac-reason">${esc(g.reason)}</span><span class="muted small">${g.records.length} notification${g.records.length === 1 ? "" : "s"}${g.unread ? ` · ${g.unread} unread` : " · read"} · expand details</span></summary>
      ${t ? `<dl class="facts ac-facts"><dt>Employee</dt><dd>${esc(t.person || "Unassigned")}</dd><dt>Department</dt><dd>${esc(t.dept)}</dd><dt>Task</dt><dd>${esc(t.stage)} ${esc(t.name)}</dd><dt>Current status</dt><dd>${esc(t.status)}</dd><dt>Due</dt><dd>${esc(t.due_at || "–")}</dd></dl>` : ""}
      <ol class="ac-history">${g.records.map(event => `<li><div class="ac-history-head">${event.read ? "" : `<span class="ac-unread-dot" aria-label="Unread"></span>`}${acTime(event.ts)}</div><b>${esc(event.title)}</b><p>${esc(event.body)}</p>${event.snoozed ? `<span class="muted small">Snoozed until ${esc(event.snoozed_until)}</span>` : ""}</li>`).join("")}</ol>
    </details><p class="ac-preview">${esc(a.body)}</p>
    ${t ? `<div class="ac-person small">${esc(t.person || "Unassigned")} · ${esc(t.dept)} · ${esc(t.stage)}</div>` : ""}
    <div class="ac-actions">${t ? `<button class="btn ${g.can_review ? "ac-review" : ""}" type="button" data-ac-action="task" data-ac-id="${a.id}">${g.can_review ? "Review work" : "Open task"}</button>` : ""}${g.is_contract ? `<button class="btn" type="button" data-ac-action="contract" data-ac-id="${a.id}">Open contract</button>` : g.bill_id ? `<button class="btn" type="button" data-ac-action="bill" data-ac-id="${a.id}">Open bill</button>` : ""}
      ${g.unread ? `<button class="btn" type="button" data-ac-action="read" data-ac-id="${a.id}">Mark read</button>` : ""}
      ${!g.urgent ? `<select class="in ac-snooze" data-ac-snooze="${a.id}" aria-label="Snooze ${esc(a.title)}"><option value="">${g.snoozed ? "Snoozed" : "Snooze…"}</option>${g.records.some(r => r.snoozed) ? '<option value="0">Show now</option>' : ""}<option value="15">15 minutes</option><option value="60">1 hour</option><option value="240">4 hours</option></select>` : `<span class="muted small">Urgent alerts stay visible</span>`}</div></article>`;
}
function acSummary() {
  const c = acData().counts;
  return `<div class="ac-stat urgent"><b>${c.urgent}</b><span>Urgent issues</span></div><div class="ac-stat approvals"><b>${c.approvals}</b><span>Pending approvals</span></div><div class="ac-stat updates"><b>${c.updates}</b><span>Unread updates</span></div>`;
}
function viewAdminAlertCenter() {
  return hero("Admin Alert Center", "Your notifications, ordered by current task deadlines and approval status.", `<button class="btn" id="acReadAll" type="button">Mark all as read</button>`) +
    `<div id="acSummary" class="ac-summary">${acSummary()}</div><div class="toolbar ac-toolbar"><input class="search" id="alertSearch" aria-label="Search alerts" placeholder="Search employee, task or department" value="${esc(S.acQuery || "")}"><div class="seg" aria-label="Alert filters">${[["all", "All"], ["urgent", "Urgent"], ["approvals", "Approvals"], ["updates", "Updates"]].map(([key, label]) => `<button type="button" data-ac-filter="${key}" aria-pressed="${(S.acFilter || "all") === key}">${label}</button>`).join("")}</div><label class="small"><input type="checkbox" id="acShowSnoozed" ${S.acShowSnoozed ? "checked" : ""}> Include snoozed</label></div>
      <div id="acStatus" class="muted small" role="status"></div><div id="alertFeed" class="ac-feed">${S.alertCenter ? acFeed() : skeleton("cards", 3)}</div>`;
}
function acFeed() {
  const query = (S.acQuery || "").trim().toLowerCase(), category = S.acFilter || "all";
  const groups = acData().groups.filter(g => (S.acShowSnoozed || !g.snoozed) && (category === "all" || g.category === category) &&
    (!query || [g.client, g.task?.name, g.task?.stage, g.task?.person, g.task?.dept, ...g.records.flatMap(a => [a.title, a.body])].join(" ").toLowerCase().includes(query)));
  const limit = S.acLimit || 50;
  return groups.length ? groups.slice(0, limit).map(g => acCard(g)).join("") + (groups.length > limit ? `<button class="btn" type="button" data-ac-action="more">Show 50 more (${groups.length - limit} remaining)</button>` : "") :
    `<div class="emptycard">${query ? "No matching notifications. Try another employee, task or department." : category !== "all" ? "No notifications in this category." : "You're all caught up. No active notifications."}${acData().counts.snoozed && !S.acShowSnoozed ? '<p class="muted small">Enable “Include snoozed” to see notifications set aside for later.</p>' : ""}</div>`;
}
function acPaintCenter() {
  const feed = $("#alertFeed"); if (!feed || !isAdmin()) return;
  $("#acSummary").innerHTML = acSummary(); feed.innerHTML = acFeed(); acWireActions(feed);
  $("#acStatus").textContent = S.acError || `${acData().counts.total} notifications preserved · ${acData().counts.unread} unread · ${acData().counts.snoozed} snoozed`;
  $("#acReadAll").disabled = !acData().counts.total_unread;
  document.querySelectorAll("[data-ac-filter]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.acFilter === (S.acFilter || "all"))));
}
function wireAdminAlertCenter() {
  if (!isAdmin()) return;
  const search = $("#alertSearch");
  if (search) {
    search.oninput = () => { S.acQuery = search.value; S.acLimit = 50; acPaintCenter(); };
    document.querySelectorAll("[data-ac-filter]").forEach(button => button.onclick = () => { S.acFilter = button.dataset.acFilter; S.acLimit = 50; acPaintCenter(); });
    $("#acShowSnoozed").onchange = e => { S.acShowSnoozed = e.target.checked; acPaintCenter(); };
    $("#acReadAll").onclick = () => acRead(); acPaintCenter();
  }
}
function acWireActions(root) {
  root.onclick = async event => {
    const button = event.target.closest("[data-ac-action]"); if (!button || button.disabled) return;
    const id = Number(button.dataset.acId), g = acGroup(id);
    switch (button.dataset.acAction) {
      case "more": S.acLimit = (S.acLimit || 50) + 50; return acPaintCenter();
      case "center": closeAlertIsland(); S.tab = "alerts"; render(); return refreshAlertCenter();
      case "retry": return refreshAlertCenter(true, true);
      case "task": closeAlertIsland(); return acOpenTask(id);
      case "contract": closeAlertIsland(); return acOpenContract(id);
      case "bill": if (g?.bill_id) { closeAlertIsland(); loadBill(g.bill_id); } return;
      case "read": if (!g) return; button.disabled = true; try { await acRead(g); } finally { button.disabled = false; } return;
    }
  };
  root.onchange = async event => {
    const select = event.target.closest("[data-ac-snooze]"); if (!select || select.value === "") return;
    const g = acGroup(select.dataset.acSnooze), minutes = Number(select.value); select.disabled = true;
    try { await acUpdateGroups("/api/alerts/snooze", g.records.map(r => r.id), { minutes }); }
    catch (e) { note("Couldn't snooze", e.message); }
    finally { select.disabled = false; select.value = ""; }
  };
  if (!root.dataset.acWired) {
    root.dataset.acWired = "1";
    root.addEventListener("toggle", event => {
      const detail = event.target; if (!detail.dataset.acDetail) return;
      S.acExpanded = S.acExpanded || new Set();
      if (detail.open) S.acExpanded.add(detail.dataset.acDetail); else S.acExpanded.delete(detail.dataset.acDetail);
    }, true);
  }
}
async function acUpdateGroups(path, ids, extra = {}) {
  for (let i = 0; i < ids.length; i += 500) await api(path, { ids: ids.slice(i, i + 500), ...extra });
  await refreshAlertCenter(true, true);
}
async function acRead(group) {
  try { if (group) await acUpdateGroups("/api/alerts/read", group.records.map(r => r.id)); else { await api("/api/alerts/read", {}); await refreshAlertCenter(true, true); } }
  catch (e) { note("Couldn't mark read", e.message); }
}
async function acOpenTask(id) {
  const actor = S.user, token = S.token;
  try {
    const t = (await api(`/api/alerts/${id}/task`)).task; if (S.user !== actor || S.token !== token) return; S.acReviewTask = { id, task: t };
    sheetHtml(`<div class="code">${esc(t.stage)} · ${esc(t.dept)}</div><h2>${esc(t.stage_name)}</h2><dl class="facts"><dt>Employee</dt><dd>${esc(t.assignee || t.owners.join(", "))}</dd><dt>Status</dt><dd>${esc(STATUS[t.status] || t.status)}</dd><dt>Approver</dt><dd>${esc(t.validator)}</dd><dt>Due</dt><dd>${esc(t.due_at)}</dd><dt>Bill</dt><dd>${esc(t.bill_id || "–")}</dd></dl><h3>Submitted work</h3><div class="box ac-output">${esc(t.output_note || "No submission note.")}</div>${t.files?.length ? `<h3>Documents</h3><div class="box">${fileList(t.files)}</div>` : '<p class="muted small">No attached documents.</p>'}${t.status === "submitted" && t.validator === S.user ? `<div class="actions" style="margin-top:16px"><button type="button" class="btn good" id="acApprove">Approve</button><button type="button" class="btn bad" id="acReturn">Return for correction</button></div>` : '<p class="muted small">Approval actions are available only to the designated approver while work is submitted.</p>'}`);
    $("#sheet").querySelectorAll("[data-preview]").forEach(button => button.onclick = () => showPreview(button.dataset.preview));
    if ($("#acApprove")) $("#acApprove").onclick = () => acDecision(id, "approve");
    if ($("#acReturn")) $("#acReturn").onclick = () => acDecision(id, "reject");
  } catch (e) { note("Couldn't open task", e.message); }
}
const acDeciding = new Set();
async function acDecision(id, action) {
  const actor = S.user, token = S.token;
  try {
    const t = (await api(`/api/alerts/${id}/task`)).task;
    if (S.user !== actor || S.token !== token) return;
    if (t.status !== "submitted" || t.validator !== S.user) throw new Error("Only the designated approver can review submitted work. Refresh the notification.");
    dialog(`<h3>${action === "approve" ? "Approve" : "Return"} ${esc(t.stage_name)}?</h3><p class="muted small">${action === "approve" ? "This approves the submitted work and runs the existing hand-off workflow." : "Explain what needs fixing. The task returns to its employee."}</p><label class="f">${action === "approve" ? "Note (optional)" : "What needs correcting?"}</label><textarea class="in" name="note" rows="3" ${action === "reject" ? "required" : ""}></textarea>`, async form => {
      if (S.user !== actor || S.token !== token || acDeciding.has(t.id)) return; acDeciding.add(t.id);
      try { await api(`/api/tasks/${t.id}/${action}`, { note: form.get("note") || "" }); if (S.user !== actor || S.token !== token) return; closeSheet(); await refreshAlertCenter(true, true); await load(); }
      catch (e) { note("Couldn't review task", e.message); }
      finally { acDeciding.delete(t.id); }
    });
  } catch (e) { note("Couldn't review task", e.message); }
}
async function acOpenContract(id) {
  const actor = S.user, token = S.token;
  const g = acGroup(id); if (!g) return;
  try {
    const storage = await api("/api/storage"), contract = storage.register.find(r => (g.contract_no && r["Contract No"] === g.contract_no) || r.Client === g.client);
    if (S.user !== actor || S.token !== token) return;
    sheetHtml(`<div class="code">CONTRACT REGISTER</div><h2>${esc(g.client)}</h2>${contract ? `<dl class="facts ac-facts">${Object.entries(contract).map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value ?? "–")}</dd>`).join("")}</dl>${contract["Contract file"] ? `<a class="btn" href="${fileUrl(String(contract["Contract file"]).replace(/\\/g, "/"))}" target="_blank" rel="noopener">Open contract file</a>` : ""}` : '<p class="muted">No matching contract entry is currently available.</p>'}<button class="btn" id="acOpenRegister" type="button" style="margin-top:16px">Open Contract Register</button>`);
    $("#acOpenRegister").onclick = () => { closeSheet(); S.st = storage; S.tab = "store"; render(); };
  } catch (e) { note("Couldn't open contract", e.message); }
}

// A single controlled refresh path coalesces SSE bursts, read actions and the 30-second deadline/snooze check.
let acFlight, acController, acPoll, acTimer, acLastFetch = 0, acDirty = false;
function startAlertCenterLive() {
  stopAlertCenterLive(); if (!isAdmin()) return;
  acPoll = setInterval(() => { if (!document.hidden) scheduleAlertCenterRefresh(); }, 30000);
  scheduleAlertCenterRefresh();
}
function stopAlertCenterLive(clear = false) {
  clearInterval(acPoll); clearTimeout(acTimer); acController?.abort(); acFlight = null; acDirty = false; acLastFetch = 0;
  closeAlertIsland(false, true);
  if (clear) { S.acIslandOrder = null; S.acIslandOrderUser = null; S.acIslandExpanded = new Set(); S.alertCenter = null; S.acReviewTask = null; S.acError = ""; S.acExpanded = new Set(); S.acQuery = ""; S.acFilter = "all"; S.acShowSnoozed = false; S.seenAlertIds = new Set(); }
}
function scheduleAlertCenterRefresh() {
  if (!S.user || !isAdmin()) return;
  clearTimeout(acTimer); acTimer = setTimeout(() => refreshAlertCenter(), Math.max(150, 450 - (performance.now() - acLastFetch)));
}
async function refreshAlertCenter(paint = true, force = false) {
  if (!S.user || !isAdmin()) return;
  if (acFlight) { if (force) acDirty = true; return acFlight; }
  if (!force && S.alertCenter && performance.now() - acLastFetch < 350) { if (paint) acPaint(); return; }
  const user = S.user, token = S.token, controller = new AbortController(); acController = controller;
  let flight;
  flight = (async () => {
    try {
      const response = await fetch("/api/alerts", { headers: { "X-Session": token }, signal: controller.signal });
      if (S.user !== user || S.token !== token) return;
      if (response.status === 401) { logout(true); return; }
      if (response.status === 403) S.alertCenter = null;
      const data = await response.json(); if (!response.ok) throw new Error(data.error || "Couldn't refresh notifications");
      if (S.user !== user || S.token !== token) return;
      S.alertCenter = data; S.acError = ""; acLastFetch = performance.now();
      if (paint) acPaint();
    } catch (e) { if (e.name !== "AbortError" && S.user === user && S.token === token) { S.acError = e.message; if (paint) acPaint(); } }
    finally { if (acFlight === flight) { acFlight = null; if (acDirty) { acDirty = false; acLastFetch = 0; scheduleAlertCenterRefresh(); } } }
  })();
  acFlight = flight; return flight;
}
function acPaint() { acPaintIsland(); acPaintCenter(); }
function receiveAlertNotification(message) {
  S.seenAlertIds = S.seenAlertIds || new Set(); if (S.seenAlertIds.has(message.id)) return;
  S.seenAlertIds.add(message.id); if (S.seenAlertIds.size > 1000) S.seenAlertIds.delete(S.seenAlertIds.values().next().value);
  if (!isAdmin()) { toast(message); return; }
  beep(); scheduleAlertCenterRefresh();
  try { if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification(message.title, { body: message.body, tag: "se-" + message.id }); } catch (e) {}
}

function alertIslandHtml() {
  const c = acData().counts;
  return `<button class="ac-island" id="adminIsland" type="button" aria-controls="adminIslandPanel" aria-expanded="${!!S.acIslandOpen}" aria-label="Alerts: ${c.unread} unread, ${c.urgent} urgent"><span class="ac-island-light ${c.urgent ? "urgent" : ""}" aria-hidden="true"></span><b data-ac-unread>${c.unread}</b><span>unread</span><span class="ac-island-urgent"><b data-ac-urgent>${c.urgent}</b> urgent</span><span aria-hidden="true">&#9662;</span></button>`;
}
function acPaintIsland() {
  const button = $("#adminIsland"); if (!button || !isAdmin()) return;
  const c = acData().counts; button.querySelector("[data-ac-unread]").textContent = c.unread; button.querySelector("[data-ac-urgent]").textContent = c.urgent;
  button.querySelector(".ac-island-light").classList.toggle("urgent", !!c.urgent); button.setAttribute("aria-label", `Alerts: ${c.unread} unread, ${c.urgent} urgent`); button.setAttribute("aria-expanded", String(!!S.acIslandOpen));
  const tab = document.querySelector('[data-tab="alerts"]'); if (tab) { tab.querySelector(".n")?.remove(); if (c.unread) tab.insertAdjacentHTML("beforeend", `<span class="n">${c.unread}</span>`); }
  if (!S.acIslandOpen) return;
  const panel = $("#adminIslandPanel"); if (!panel) return;
  if (acIslandDrag || acIslandControlTap) { acIslandPaintPending = true; acPositionIsland(); return; }
  const scroll = panel.scrollTop, active = panel.contains(document.activeElement) ? document.activeElement : null;
  const focus = active ? { action: active.dataset.acAction, id: active.dataset.acId, drag: active.dataset.acDrag, expand: active.dataset.acExpand } : null;
  const top = acOrderedIslandGroups();
  panel.innerHTML = `<div class="ac-island-head"><b>Admin command center</b><button class="btn" type="button" data-ac-action="center">View all alerts</button></div>${S.acError ? `<p class="ac-error" role="status">${esc(S.acError)} <button class="btn" type="button" data-ac-action="retry">Retry</button></p>` : ""}<div class="ac-island-cards">${top.map(g => acCard(g, true)).join("") || '<p class="empty">No active notifications. You are all caught up.</p>'}</div><p class="ac-island-hint" id="acReorderHint">Drag handles or use their arrow keys to arrange this preview. Task priorities stay unchanged.</p><span class="vh" id="acReorderStatus" aria-live="polite"></span>`;
  acWireActions(panel); acWireIslandCards(panel); panel.scrollTop = scroll;
  if (focus) [...panel.querySelectorAll("button,select")].find(button =>
    focus.drag ? button.dataset.acDrag === focus.drag : focus.expand ? button.dataset.acExpand === focus.expand : focus.action && button.dataset.acAction === focus.action && button.dataset.acId === focus.id)?.focus({ preventScroll: true });
  acPositionIsland();
}

// The dock reserves header space; the preview is a separate floating surface, never a task dialog.
let acIslandCloseTimer, acIslandDrag = null, acIslandPaintPending = false, acIslandSuppressClickUntil = 0, acIslandSuppressHover = false, acIslandButtonClickUntil = 0, acIslandTouchStart = null, acIslandControlTap = null, acIslandControlClickUntil = 0;
function acIslandCard(g) {
  const a = g.latest, t = g.task, open = S.acIslandExpanded?.has(g.key), detailId = `acIslandDescription-${a.id}`;
  return `<article class="ac-card ac-island-card ac-${g.category} ${g.unread ? "is-unread" : ""}" data-ac-group="${esc(g.key)}">
    <div class="ac-island-card-head"><button class="ac-drag-handle" type="button" data-ac-drag="${esc(g.key)}" aria-label="Reorder ${esc(a.title)}" aria-describedby="acReorderHint" title="Drag to reorder, or use Up and Down arrow keys">&#8942;&#8942;</button><span class="ac-kind">${g.urgent ? "Urgent" : g.can_review ? "Approval" : g.priority === 2 ? "Contract / compliance" : "Update"}</span>${g.unread ? '<span class="ac-unread-dot" aria-label="Unread"></span>' : ""}<button class="ac-expand-alert" type="button" data-ac-expand="${esc(g.key)}" aria-expanded="${!!open}" aria-controls="${detailId}" aria-label="${open ? "Collapse" : "Expand"} alert description"><span aria-hidden="true">&#9662;</span></button></div>
    <b class="ac-island-title">${esc(a.title)}</b><p class="ac-island-excerpt">${esc(a.body)}</p><div class="ac-island-meta">${acTime(a.ts)}</div>
    <div class="ac-island-description" id="${detailId}" ${open ? "" : "hidden"}><p>${esc(g.reason)}</p>${t ? `<dl class="facts ac-facts"><dt>Employee</dt><dd>${esc(t.person || "Unassigned")}</dd><dt>Department</dt><dd>${esc(t.dept)}</dd><dt>Task</dt><dd>${esc(t.stage)} ${esc(t.name)}</dd><dt>Status</dt><dd>${esc(t.status)}</dd><dt>Due</dt><dd>${esc(t.due_at || "-")}</dd></dl>` : ""}<ol class="ac-history">${g.records.map(record => `<li><div class="ac-history-head">${acTime(record.ts)}</div><b>${esc(record.title)}</b><p>${esc(record.body)}</p></li>`).join("")}</ol></div>
    <div class="ac-actions">${t ? `<button class="btn" type="button" data-ac-action="task" data-ac-id="${a.id}">Open task</button>` : ""}${g.unread ? `<button class="btn" type="button" data-ac-action="read" data-ac-id="${a.id}">Mark read</button>` : ""}</div>
  </article>`;
}
function acOrderedIslandGroups() {
  if (S.acIslandOrderUser !== S.user) {
    S.acIslandOrderUser = S.user;
    try { const stored = JSON.parse(store.get("se_alert_island_order_" + S.user) || "[]"); S.acIslandOrder = Array.isArray(stored) ? stored.filter(key => typeof key === "string") : []; }
    catch (e) { S.acIslandOrder = []; }
  }
  const groups = acData().groups.filter(g => !g.snoozed && (g.urgent || g.can_review || g.unread)).slice(0, 5);
  const order = S.acIslandOrder || [], rank = new Map(order.map((key, i) => [key, i]));
  // Membership always comes from the current backend priority order; preferences only reorder these cards.
  return groups.map((group, i) => ({ group, rank: rank.has(group.key) ? rank.get(group.key) : order.length + i })).sort((a, b) => a.rank - b.rank).map(item => item.group);
}
function acSaveIslandOrder(panel) {
  const visible = [...panel.querySelectorAll(".ac-island-card")].map(card => card.dataset.acGroup);
  S.acIslandOrder = [...visible, ...(S.acIslandOrder || []).filter(key => !visible.includes(key))].slice(0, 200);
  S.acIslandOrderUser = S.user; store.set("se_alert_island_order_" + S.user, JSON.stringify(S.acIslandOrder));
}
function acAnimateIslandOrder(panel, change) {
  const cards = [...panel.querySelectorAll(".ac-island-card")], before = new Map(cards.map(card => [card, card.getBoundingClientRect()]));
  change();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  cards.forEach(card => { const dy = before.get(card).top - card.getBoundingClientRect().top; if (dy && !card.classList.contains("ac-is-dragging")) card.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 160, easing: "ease-out" }); });
}
function acWireIslandCards(panel) {
  panel.onpointerenter = () => clearTimeout(acIslandCloseTimer);
  panel.onpointerleave = () => acScheduleIslandClose();
  panel.onfocusout = () => acScheduleIslandClose();
  if (!panel.dataset.acIslandWired) {
    panel.dataset.acIslandWired = "1";
    panel.addEventListener("click", event => {
      if (acIslandDrag || performance.now() < acIslandSuppressClickUntil || (event.detail !== 0 && performance.now() < acIslandControlClickUntil)) { event.preventDefault(); event.stopImmediatePropagation(); return; }
      const expand = event.target.closest("[data-ac-expand]");
      if (!expand) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const key = expand.dataset.acExpand; S.acIslandExpanded = S.acIslandExpanded || new Set();
      if (S.acIslandExpanded.has(key)) S.acIslandExpanded.delete(key); else S.acIslandExpanded.add(key);
      const open = S.acIslandExpanded.has(key); expand.setAttribute("aria-expanded", String(open)); expand.setAttribute("aria-label", `${open ? "Collapse" : "Expand"} alert description`);
      document.getElementById(expand.getAttribute("aria-controls")).hidden = !open;
    }, true);
    panel.addEventListener("keydown", event => {
      const handle = event.target.closest("[data-ac-drag]"); if (!handle || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation(); clearTimeout(acIslandCloseTimer);
      const card = handle.closest(".ac-island-card"), sibling = event.key === "ArrowUp" ? card.previousElementSibling : card.nextElementSibling;
      if (!sibling) return;
      acAnimateIslandOrder(panel, () => { if (event.key === "ArrowUp") card.parentElement.insertBefore(card, sibling); else card.parentElement.insertBefore(sibling, card); });
      acSaveIslandOrder(panel); handle.focus({ preventScroll: true }); $("#acReorderStatus").textContent = "Alert order updated";
    });
  }
  panel.onpointerdown = event => {
    const handle = event.target.closest("[data-ac-drag]");
    if (!handle) {
      const control = event.target.closest("button[data-ac-action], button[data-ac-expand]");
      if (event.pointerType === "touch" && event.isPrimary !== false && control && !control.disabled && !acIslandDrag) {
        acIslandControlTap = { id: event.pointerId, control, x: event.clientX, y: event.clientY }; panel.setPointerCapture(event.pointerId);
      }
      return;
    }
    if (event.button !== 0 || acIslandDrag || event.isPrimary === false) return;
    // touch-action:none owns touch scrolling; canceling touch pointerdown can suppress the next tap.
    if (event.pointerType !== "touch") event.preventDefault();
    event.stopPropagation(); clearTimeout(acIslandCloseTimer);
    acIslandDrag = { id: event.pointerId, x: event.clientX, y: event.clientY, card: handle.closest(".ac-island-card"), moved: false };
    panel.setPointerCapture(event.pointerId);
  };
  panel.onpointermove = event => {
    const drag = acIslandDrag; if (!drag || drag.id !== event.pointerId) return;
    if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 6) return;
    if (event.pointerType !== "touch") event.preventDefault(); drag.moved = true; drag.card.classList.add("ac-is-dragging"); panel.classList.add("ac-reordering");
    const bounds = panel.getBoundingClientRect(); if (event.clientY < bounds.top + 35) panel.scrollTop -= 12; else if (event.clientY > bounds.bottom - 35) panel.scrollTop += 12;
    const candidates = [...panel.querySelectorAll(".ac-island-card")].filter(card => card !== drag.card);
    const before = candidates.find(card => event.clientY < card.getBoundingClientRect().top + card.getBoundingClientRect().height / 2);
    if (drag.card.nextElementSibling !== (before || null)) acAnimateIslandOrder(panel, () => drag.card.parentElement.insertBefore(drag.card, before || null));
  };
  panel.onpointerup = panel.onpointercancel = event => {
    const tap = acIslandControlTap;
    if (tap && tap.id === event.pointerId) {
      acIslandControlTap = null;
      if (panel.hasPointerCapture(event.pointerId)) panel.releasePointerCapture(event.pointerId);
      if (event.type !== "pointercancel" && Math.hypot(event.clientX - tap.x, event.clientY - tap.y) <= 8 && tap.control.isConnected) {
        event.preventDefault(); event.stopPropagation(); acIslandControlClickUntil = performance.now() + 500; acIslandSuppressClickUntil = 0;
        // Native and touch activation share the exact same click handlers and authorization path.
        tap.control.click();
      }
      if (acIslandPaintPending && S.acIslandOpen) { acIslandPaintPending = false; acPaintIsland(); }
      acScheduleIslandClose(); return;
    }
    const drag = acIslandDrag; if (!drag || drag.id !== event.pointerId) return;
    const moved = drag.moved; drag.card.classList.remove("ac-is-dragging"); panel.classList.remove("ac-reordering"); acIslandDrag = null;
    if (panel.hasPointerCapture(event.pointerId)) panel.releasePointerCapture(event.pointerId);
    if (moved) { acIslandSuppressClickUntil = performance.now() + 300; acSaveIslandOrder(panel); $("#acReorderStatus").textContent = "Alert order updated"; }
    if (acIslandPaintPending) { acIslandPaintPending = false; acPaintIsland(); }
    acScheduleIslandClose();
  };
}
function acPositionIsland() {
  const button = $("#adminIsland"), panel = $("#adminIslandPanel"); if (!button) return;
  document.documentElement.style.setProperty("--admin-header-height", `${button.closest("header").getBoundingClientRect().bottom}px`);
  if (!panel) return;
  const viewportWidth = document.documentElement.clientWidth, viewportHeight = window.visualViewport?.height || document.documentElement.clientHeight;
  const width = Math.min(460, viewportWidth - 24), headerBottom = button.closest("header").getBoundingClientRect().bottom;
  const top = Math.min(headerBottom + 8, viewportHeight - 112);
  panel.style.width = `${width}px`; panel.style.left = `${(viewportWidth - width) / 2}px`;
  panel.style.top = `${top}px`; panel.style.maxHeight = `${Math.max(100, Math.min(viewportHeight * .65, viewportHeight - top - 12))}px`;
}
function acScheduleIslandClose() {
  clearTimeout(acIslandCloseTimer);
  if (!S.acIslandOpen || !matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  acIslandCloseTimer = setTimeout(() => {
    const button = $("#adminIsland"), panel = $("#adminIslandPanel");
    if (acIslandDrag || button?.matches(":hover") || panel?.matches(":hover")) return;
    if (panel?.querySelector(":focus-visible, select:focus")) return;
    closeAlertIsland();
  }, 300);
}
function closeAlertIsland(focus = false, immediate = false) {
  clearTimeout(acIslandCloseTimer); S.acIslandOpen = false; acIslandSuppressHover = !!$("#adminIsland")?.matches(":hover");
  const panel = $("#adminIslandPanel");
  if (acIslandControlTap) {
    if (panel?.hasPointerCapture(acIslandControlTap.id)) panel.releasePointerCapture(acIslandControlTap.id);
    acIslandControlTap = null;
  }
  if (acIslandDrag) {
    if (panel?.hasPointerCapture(acIslandDrag.id)) panel.releasePointerCapture(acIslandDrag.id);
    acIslandDrag = null;
  }
  acIslandPaintPending = false;
  if (panel) {
    if (immediate || matchMedia("(prefers-reduced-motion: reduce)").matches) panel.remove();
    else { panel.inert = true; panel.classList.add("ac-island-closing"); setTimeout(() => panel.remove(), 180); }
  }
  $("#adminIsland")?.setAttribute("aria-expanded", "false"); if (focus) $("#adminIsland")?.focus();
}
function acOpenIsland(focus = false) {
  clearTimeout(acIslandCloseTimer);
  if (S.acIslandOpen) return;
  $("#adminIslandPanel")?.remove(); S.acIslandOpen = true; S.acIslandExpanded = new Set();
  const panel = document.createElement("section"); panel.id = "adminIslandPanel"; panel.className = "ac-island-panel"; panel.setAttribute("aria-label", "Priority notifications"); document.body.append(panel);
  acPaintIsland(); if (focus) panel.querySelector("button")?.focus(); refreshAlertCenter();
}
function wireAlertIsland() {
  const button = $("#adminIsland"); if (!button) return;
  let pointerType = "mouse";
  button.onpointerenter = event => {
    if (event.pointerType === "touch" || !matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    clearTimeout(acIslandCloseTimer); if (!acIslandSuppressHover) acOpenIsland();
  };
  button.onpointerleave = () => { acIslandSuppressHover = false; acScheduleIslandClose(); };
  button.onpointerdown = event => {
    pointerType = event.pointerType;
    if (event.pointerType === "touch" && event.isPrimary !== false) acIslandTouchStart = { id: event.pointerId, x: event.clientX, y: event.clientY };
  };
  button.onpointerup = event => {
    const start = acIslandTouchStart;
    if (event.pointerType !== "touch" || !start || start.id !== event.pointerId) return;
    acIslandTouchStart = null;
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 8) return;
    // Touch clicks may be suppressed by the browser after a drag. Handle the tap once at pointerup.
    event.preventDefault(); event.stopPropagation(); acIslandButtonClickUntil = performance.now() + 500;
    if (S.acIslandOpen) closeAlertIsland(); else { acIslandSuppressHover = false; acOpenIsland(); }
  };
  button.onpointercancel = () => { acIslandTouchStart = null; };
  button.onclick = event => {
    if (event.detail !== 0 && performance.now() < acIslandButtonClickUntil) { event.preventDefault(); return; }
    if (pointerType === "touch" || !matchMedia("(hover: hover) and (pointer: fine)").matches || event.detail === 0) {
      if (S.acIslandOpen) closeAlertIsland(); else { acIslandSuppressHover = false; acOpenIsland(event.detail === 0); }
    } else { acIslandSuppressHover = false; acOpenIsland(); }
  };
  acPositionIsland(); acPaintIsland();
}

document.addEventListener("click", event => { if (S.acIslandOpen && !event.target.closest("#adminIsland, #adminIslandPanel")) closeAlertIsland(); });
document.addEventListener("keydown", event => { if (event.key === "Escape" && S.acIslandOpen && !$("#dlg")?.open) { event.preventDefault(); event.stopImmediatePropagation(); closeAlertIsland(true); } }, true);
window.addEventListener("resize", acPositionIsland);
window.visualViewport?.addEventListener("resize", acPositionIsland);
