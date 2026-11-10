// Page: Tracker (daily time tracker, export, lunch settings).
"use strict";
// ---------------------------------------------------------- admin: time tracker
function viewTracker() {
  trHidePreview();
  const d = S.tr; if (!d) return hero("Tracker", "") + skeleton("cards", 4) + `<div style="height:16px"></div>` + skeleton("table", 6);
  const L = d.lunch, live = d.date === today();
  const pq = (S.tq || "").toLowerCase();
  const rows = d.rows.filter(r => !pq || (r.person + " " + r.task + " " + r.dept + " " + r.code).toLowerCase().includes(pq))
    .filter(r => S.tAll || r.day_seconds > 0 || r.running_since || r.code.startsWith("TASK-"));
  const so = S.trSort || { k: "", dir: 1 };
  const key = { person: r => r.person.toLowerCase(), task: r => (r.code + " " + r.task).toLowerCase(), started: r => r.started_at || "", done: r => r.done_at || "",
                approved: r => r.approved_at || "", ended: r => r.ended_at || "", worked: r => r.day_seconds || 0, status: r => r.status }[so.k];
  if (key) rows.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * so.dir; });
  const th = (k, label, left) => `<th ${left ? 'style="text-align:left"' : ""} aria-sort="${so.k === k ? (so.dir > 0 ? "ascending" : "descending") : "none"}"><button type="button" class="sortbtn" data-sort="${k}">${label}<span class="arr">${so.k === k ? (so.dir > 0 ? "▲" : "▼") : "↕"}</span></button></th>`;
  const people = d.people.filter(p => S.tAll || p.seconds > 0 || p.running);
  const cards = people.map(p => `<div class="pcard tr-person" data-tr-person="${esc(p.person)}" role="button" tabindex="0" aria-haspopup="dialog" aria-label="Task details for ${esc(p.person)}"><div class="who">${avatar(p.person)}<div><b>${esc(p.person)}</b><div class="muted small">${esc(p.dept)}</div></div></div>
      <div>${live && p.running ? tick(p.seconds, d.server_now, "timer") : `<span class="timer">${clock(p.seconds)}</span>`}</div>
      <div class="muted small">${p.tasks} task${p.tasks === 1 ? "" : "s"} · ${p.finished} finished</div>
      ${p.running ? `<div class="small"><span class="live" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#34c759;margin-right:6px"></span>${esc(p.running)}</div>` : `<div class="muted small">Not running a task</div>`}</div>`).join("");
  const table = trTaskRows(rows, d);
  return hero("Tracker", "",
      `<div class="daypick"><input class="in" type="date" id="tDate" value="${esc(d.date)}" max="${today()}" style="width:auto">
        <details class="tr-export"><summary class="btn primary">Export</summary><div class="tr-export-menu" aria-label="Export tracker">
          <button class="btn" type="button" data-tr-export="xlsx">Export as Excel (.xlsx)</button>
          <button class="btn" type="button" data-tr-export="pdf">Export as PDF (.pdf)</button>
          <span class="muted small">All non-demo records for the selected date, as in the existing Excel export.</span>
        </div></details></div>`) +
    `<div class="pcards">${cards || `<div class="emptycard">Nobody has tracked time on ${esc(d.date)} yet.</div>`}</div>
    <div class="toolbar" style="margin-top:20px"><input class="search" id="tq" placeholder="Search person, task or department" aria-label="Search the tracker" value="${esc(S.tq || "")}">
      <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="tAll" ${S.tAll ? "checked" : ""}> Include tasks with no time</label>${demoToggle()}</div>
    <section class="tr-all-tasks${S.trTablePinned || S.trTableHover ? " is-open" : ""}" aria-label="All tracked tasks">
      <button class="tr-task-toggle" id="trTaskToggle" type="button" aria-controls="trTaskBody" aria-expanded="${!!(S.trTablePinned || S.trTableHover)}"><span>View All Tasks</span><span class="tr-task-arrow" aria-hidden="true">&#9662;</span></button>
      <div class="tr-task-body" id="trTaskBody" ${S.trTablePinned || S.trTableHover ? "" : "inert"}><div><div class="panel scroll"><table><thead><tr>${th("person", "Person", 1)}${th("task", "Task", 1)}${th("started", "Started")}${th("done", "Done")}${th("approved", "Approved")}${th("ended", "Ended")}${th("worked", "Worked")}${th("status", "Status")}<th>Docs</th></tr></thead>
      <tbody>${table || `<tr><td colspan="9" class="empty">${pq ? `Nothing matches “${esc(S.tq)}”.` : "No tracked tasks for this day."}</td></tr>`}</tbody></table></div></div></div></section>
    <h2>Lunch lock</h2><div class="panel"><div class="row2"><label class="small" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="lOn" ${L.enabled !== false ? "checked" : ""} style="width:18px;height:18px;accent-color:#0071e3"> Lock the app and pause timers</label>
      from <input class="in" type="time" id="lFrom" value="${esc(L.start)}" style="flex:0 0 auto;width:auto;min-width:0"> to <input class="in" type="time" id="lTo" value="${esc(L.end)}" style="flex:0 0 auto;width:auto;min-width:0">
      <span style="flex:1"></span><button class="btn" id="lSave" type="button">Save lunch time</button></div>
      <p class="muted small" style="margin:10px 0 0">During lunch, staff see a lock screen and can't start, finish, upload or end tasks; admins can still work. A copy of each day's tracker is also saved in Storage → 01 Master Tracker → Daily Time Tracker.</p></div>`;
}
function wireTracker() {
  trWireTaskDisclosure();
  trWirePeople();
  document.querySelectorAll("[data-tr-export]").forEach(b => b.onclick = () => trDownload(b.dataset.trExport));
  const menu = document.querySelector(".tr-export");
  if (menu) {
    menu.addEventListener("keydown", e => { if (e.key === "Escape") { menu.open = false; menu.querySelector("summary").focus(); } });
    document.addEventListener("click", trCloseExport);
  }
  trRefreshEmployee();
  const dt = $("#tDate"); if (dt) dt.onchange = async () => { trCloseEmployee(); trHidePreview(); S.trDate = dt.value; try { S.tr = await api(trUrl()); } catch (e) { note("Couldn't load", e.message); } render(); };
  const tq = $("#tq"); if (tq) tq.oninput = () => { S.tq = tq.value; render(); };
  document.querySelectorAll("[data-sort]").forEach(b => b.onclick = () => { const k = b.dataset.sort, cur = S.trSort || {};
    S.trSort = { k, dir: cur.k === k ? -cur.dir : (k === "worked" ? -1 : 1) }; render(); });
  const ta = $("#tAll"); if (ta) ta.onchange = () => { S.tAll = ta.checked; render(); };
  $("#lSave").onclick = async () => { try { const r = await api("/api/lunch", { lunch: { enabled: $("#lOn").checked, start: $("#lFrom").value, end: $("#lTo").value } });
    S.meta.lunch = r.lunch; S.tr = await api(trUrl()); render(); note("Lunch time saved", `${ampm(r.lunch.start)}–${ampm(r.lunch.end)}${r.lunch.enabled ? "" : " (lock off)"}`, "approved"); } catch (e) { note("Couldn't save", e.message); } };
}


// Both employee overlays reuse the Tracker's selected-date rows and live timer helper.
const trTime = v => v ? esc(String(v).slice(11, 16)) : "\u2013";
const trPill = st => `<span class="pill ${/Running/.test(st) ? "p-in_progress" : /Waiting for approval/.test(st) ? "p-submitted" : /documents/.test(st) ? "p-docs" : /Ended|Approved/.test(st) ? "p-approved" : "p-assigned"}">${esc(st)}</span>`;
function trWorked(r, d) {
  return d.date === today() && r.running_since ? tick(r.day_seconds, d.server_now, "timer sm") : clock(r.day_seconds);
}
function trTaskRows(rows, d, preview = false) {
  return rows.map(r => `<tr>${preview ? "" : `<td style="text-align:left"><b>${esc(r.person)}</b><div class="muted small">${esc(r.dept)}</div></td>`}
    <td style="text-align:left;white-space:normal"><b>${esc(r.code)}</b> ${esc(r.task)}${demoTag(r)}${preview ? "" : `<div class="muted small">${esc(r.type)}${r.bill ? " \u00b7 " + esc(r.bill) : ""}</div>`}</td>
    <td>${trTime(r.started_at)}</td><td>${trTime(r.done_at)}</td><td>${trTime(r.approved_at)}</td>${preview ? "" : `<td>${trTime(r.ended_at)}</td>`}
    <td><b>${trWorked(r, d)}</b></td><td>${trPill(r.status)}</td>${preview ? "" : `<td>${docsBtn("tr" + r.id, `${r.code} ${r.task} \u00b7 ${r.person}`, r.docs)}</td>`}</tr>`).join("");
}
function trEmployeeRows(person) { return (S.tr?.rows || []).filter(r => r.person === person); }
function trEmployeeTable(person, preview = false) {
  const rows = trEmployeeRows(person), cols = preview ? ["Task", "Started", "Done", "Approved", "Worked", "Status"] : ["Person", "Task", "Started", "Done", "Approved", "Ended", "Worked", "Status", "Docs"];
  return `<div class="tr-detail-scroll"><table><thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${trTaskRows(rows, S.tr, preview) || `<tr><td colspan="${cols.length}" class="empty">No tasks for this employee on this date.</td></tr>`}</tbody></table></div>`;
}
let trPreviewTimer, trPreviewCard, trPersonObserver;
function trHidePreview() {
  clearTimeout(trPreviewTimer);
  document.getElementById("trEmployeePreview")?.remove();
  trPreviewCard?.removeAttribute("aria-describedby"); trPreviewCard = null;
}
function trScheduleHide() { clearTimeout(trPreviewTimer); trPreviewTimer = setTimeout(trHidePreview, 140); }
function trShowPreview(card) {
  if (!isAdmin() || document.getElementById("trEmployeeModal")?.open) return;
  trHidePreview(); trPreviewCard = card;
  const preview = document.createElement("div"); preview.id = "trEmployeePreview"; preview.className = "tr-preview"; preview.setAttribute("role", "tooltip");
  preview.innerHTML = `<b>${esc(card.dataset.trPerson)}</b><div class="muted small">${esc(S.tr.date)}</div>${trEmployeeTable(card.dataset.trPerson, true)}`;
  document.body.append(preview); card.setAttribute("aria-describedby", preview.id);
  preview.onpointerenter = () => clearTimeout(trPreviewTimer); preview.onpointerleave = trScheduleHide;
  const box = card.getBoundingClientRect(), size = preview.getBoundingClientRect(), gap = 8;
  const left = Math.max(gap, Math.min(box.left, innerWidth - size.width - gap));
  const top = box.bottom + size.height + gap <= innerHeight ? box.bottom + gap : Math.max(gap, box.top - size.height - gap);
  preview.style.left = `${left}px`; preview.style.top = `${top}px`;
}
function trWirePeople() {
  document.querySelectorAll("[data-tr-person]").forEach(card => {
    card.onpointerenter = e => { if (e.pointerType !== "touch") trShowPreview(card); };
    card.onpointerleave = trScheduleHide;
    card.onfocus = () => trShowPreview(card); card.onblur = trScheduleHide;
    card.onclick = () => trOpenEmployee(card.dataset.trPerson);
    card.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); trOpenEmployee(card.dataset.trPerson); } else if (e.key === "Escape") trHidePreview(); };
  });
  if (!trPersonObserver) {
    trPersonObserver = new MutationObserver(() => {
      if (!S.user || !isAdmin() || S.tab !== "tracker") { trHidePreview(); trCloseEmployee(); }
    });
    trPersonObserver.observe(app, { childList: true });
    window.addEventListener("resize", trHidePreview);
    window.addEventListener("scroll", trHidePreview);
  }
}
function trCloseEmployee() { const modal = document.getElementById("trEmployeeModal"); if (modal) { modal.close(); modal.remove(); } }
function trOpenEmployee(person) {
  if (!isAdmin() || !S.tr) return;
  trHidePreview(); trCloseEmployee();
  const modal = document.createElement("dialog"); modal.id = "trEmployeeModal"; modal.className = "tr-employee-modal";
  modal.dataset.person = person; modal.dataset.date = S.tr.date; modal.setAttribute("aria-labelledby", "trEmployeeName"); document.body.append(modal);
  modal.onkeydown = e => { if (e.key === "Escape") e.stopPropagation(); };
  let outside = false;
  const isOutside = e => { const b = modal.getBoundingClientRect(); return e.clientX < b.left || e.clientX > b.right || e.clientY < b.top || e.clientY > b.bottom; };
  modal.onpointerdown = e => { outside = e.target === modal && isOutside(e); };
  modal.onclick = e => { if (outside && e.target === modal && isOutside(e)) trCloseEmployee(); };
  modal.onclose = () => { modal.remove(); const card = [...document.querySelectorAll("[data-tr-person]")].find(c => c.dataset.trPerson === person); card?.focus({ preventScroll: true }); trHidePreview(); };
  trRefreshEmployee(); modal.showModal();
}
function trRefreshEmployee() {
  const modal = document.getElementById("trEmployeeModal"); if (!modal) return;
  if (!S.user || !isAdmin() || S.tab !== "tracker" || modal.dataset.date !== S.tr?.date) return trCloseEmployee();
  const person = modal.dataset.person, p = S.tr.people.find(p => p.person === person), rows = trEmployeeRows(person);
  const scroll = modal.querySelector(".tr-detail-scroll"), position = scroll ? [scroll.scrollLeft, scroll.scrollTop] : [0, 0];
  const running = rows.filter(r => r.running_since).length;
  modal.innerHTML = `<div class="tr-employee-head"><div><h2 id="trEmployeeName">${esc(person)}</h2><p class="muted">${esc(p?.dept || "")} &middot; ${esc(S.tr.date)}</p></div><button class="btn" type="button" id="trEmployeeClose" aria-label="Close employee details">&#10005;</button></div>
    <div class="tr-employee-stats"><div><b>${p?.tasks || 0}</b><span>Total tasks</span></div><div><b>${p?.finished || 0}</b><span>Completed tasks</span></div><div><b>${running}</b><span>Running tasks</span></div><div><b>${S.tr.date === today() && p?.running ? tick(p.seconds, S.tr.server_now, "timer") : clock(p?.seconds || 0)}</b><span>Total working time</span></div></div>
    ${trEmployeeTable(person)}`;
  modal.querySelector("#trEmployeeClose").onclick = trCloseEmployee;
  modal.querySelectorAll("[data-docs]").forEach(b => b.onclick = () => { trCloseEmployee(); showDocs(b.dataset.docs); });
  const area = modal.querySelector(".tr-detail-scroll"); area.scrollLeft = position[0]; area.scrollTop = position[1];
}
function trCloseExport(e) { document.querySelectorAll(".tr-export[open]").forEach(menu => { if (!menu.contains(e.target)) menu.open = false; }); }
async function trDownload(format) {
  if (!isAdmin() || !S.tr) return;
  const date = S.tr.date, button = document.querySelector(`[data-tr-export="${format}"]`);
  document.querySelector(".tr-export")?.removeAttribute("open"); if (button) button.disabled = true;
  try {
    const url = `/api/tracker/export${format === "pdf" ? ".pdf" : ""}?date=${encodeURIComponent(date)}`;
    const response = await fetch(withT(url));
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error || "Could not export the tracker"); }
    const blob = await response.blob(), link = document.createElement("a"), objectURL = URL.createObjectURL(blob);
    link.href = objectURL; link.download = `Tracker_${date}.${format}`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(objectURL), 60000);
  } catch (e) { note("Couldn't export", e.message); }
  finally { if (button) button.disabled = false; }
}


// Main table disclosure. Pinned and temporary hover state survive normal Tracker renders.
let trTableCloseTimer, trTableSuppressHover = false;
function trSetTaskDisclosure() {
  const box = document.querySelector(".tr-all-tasks"), button = document.getElementById("trTaskToggle"), body = document.getElementById("trTaskBody");
  if (!box || !button || !body) return;
  const open = !!(S.trTablePinned || S.trTableHover);
  box.classList.toggle("is-open", open); button.setAttribute("aria-expanded", String(open)); body.inert = !open;
}
function trScheduleTaskCollapse() {
  clearTimeout(trTableCloseTimer);
  trTableCloseTimer = setTimeout(() => {
    const box = document.querySelector(".tr-all-tasks");
    if (!box) { S.trTableHover = false; trTableSuppressHover = false; return; }
    if (S.trTablePinned) return;
    if (box.matches(":hover") && matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    // Let keyboard navigation and the existing document panel finish before collapsing.
    if (box.querySelector("#trTaskBody :focus-visible") || document.querySelector("#sheet.open, #dlg[open]")) { trScheduleTaskCollapse(); return; }
    S.trTableHover = false; trSetTaskDisclosure();
  }, 300);
}
function trWireTaskDisclosure() {
  clearTimeout(trTableCloseTimer);
  const box = document.querySelector(".tr-all-tasks"), button = document.getElementById("trTaskToggle"); if (!box || !button) return;
  if (!box.matches(":hover")) trTableSuppressHover = false;
  box.onpointerenter = e => {
    if (e.pointerType === "touch" || !matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    clearTimeout(trTableCloseTimer);
    if (!trTableSuppressHover) { S.trTableHover = true; trSetTaskDisclosure(); }
  };
  box.onpointerleave = e => {
    if (e.pointerType === "touch") return;
    trTableSuppressHover = false; trScheduleTaskCollapse();
  };
  button.onclick = () => {
    clearTimeout(trTableCloseTimer);
    S.trTablePinned = !S.trTablePinned;
    if (!S.trTablePinned) { S.trTableHover = false; trTableSuppressHover = box.matches(":hover") && matchMedia("(hover: hover) and (pointer: fine)").matches; }
    trSetTaskDisclosure();
  };
  box.onfocusin = () => clearTimeout(trTableCloseTimer);
  box.onfocusout = () => { if (!S.trTablePinned) trScheduleTaskCollapse(); };
  if (S.trTableHover && !box.matches(":hover") && !S.trTablePinned) trScheduleTaskCollapse();
}
