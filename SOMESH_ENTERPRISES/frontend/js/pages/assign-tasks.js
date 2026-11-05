// Page: Assign tasks (drag a task card onto a person or a department; list of tasks given; delete).
"use strict";
// State kept in S so it survives re-renders:
//   S.asgSel    selected task card key ("tpl:3", "draft:<id>") for click-to-give, or null
//   S.asgMulti  people / "dept:<D>" picked with Ctrl+click (or "Select several") to give one task to all of them
//   S.asgPick   "Select several" mode on (for touch and keyboard, where Ctrl+click isn't available)
//   S.asgDrafts new tasks made with "＋ New task", shown at the top until given
//   S.asgPerson / S.asgQ  person filter and search for "Tasks given so far"
const ASG_COLS = [["assigned", "To start"], ["in_progress", "Working"], ["submitted", "Waiting for approval"], ["docs", "Adding documents"], ["done", "Done"]];
const asgCol = (t) => t.status === "approved" ? (t.ended_at ? "done" : "docs") : t.status;
const asgIsOpen = (t) => asgCol(t) !== "done";
// Who a task belongs to. Before Start, a task given to one person has no assignee yet but a single owner;
// a task for "anyone in a department" has no assignee and several owners.
const asgOwner = (t) => t.assignee || ((t.owners || []).length === 1 ? t.owners[0] : "");
function asgTask(key) {   // what a task card stands for
  if (key === "new") return { title: "", hours: 4, docs: false, about: "", isNew: true };
  const [kind, id] = String(key).split(":");
  if (kind === "tpl") { const t = (S.tpls || [])[Number(id)]; return t ? { title: t.name, hours: t.hours, docs: !!t.docs, about: t.about || "" } : null; }
  if (kind === "draft") { const t = (S.asgDrafts || []).find(x => String(x.k) === id); return t ? { title: t.title, hours: t.hours, docs: t.docs, about: t.output || "", draft: t.k } : null; }
  return null;
}
const asgWhoName = (w) => w.startsWith("dept:") ? `anyone in ${w.slice(5)}` : w;
function asgPersonStats(name, tasks) {
  const mine = tasks.filter(t => asgOwner(t) === name), open = mine.filter(asgIsOpen);
  const working = mine.find(t => t.status === "in_progress"), next = mine.filter(t => t.status === "assigned").length;
  const waiting = mine.filter(t => t.status === "submitted").length, docs = mine.filter(t => asgCol(t) === "docs").length;
  const line = working ? `Working on: ${working.stage_name}` : next ? `${next} up next` : waiting ? `${waiting} waiting for approval` : docs ? "Adding documents" : "Free";
  return { open: open.length, line, busy: !!working };
}
function viewAssign() {
  const d = S.adhoc; if (!d) return hero("Assign tasks", "") + skeleton("table", 5);
  if (S.tpls === undefined && !S.asgTplLoading) {   // repeatable tasks are normally loaded by the Pipeline tab
    S.asgTplLoading = true;
    api("/api/templates").then(r => { S.tpls = r.templates || []; }).catch(() => { S.tpls = []; }).finally(() => { S.asgTplLoading = false; if (S.tab === "assign") render(); });
  }
  const users = S.meta.users, depts = [...new Set(users.map(u => u.dept))], tasks = d.tasks || [];
  const multi = S.asgMulti || [], sel = S.asgSel || null, selTask = sel ? asgTask(sel) : null;
  // LEFT: task cards
  const tcard = (key, t, extra) => `<button type="button" class="tpl asg-task${sel === key ? " sel" : ""}" draggable="true" data-asgtask="${esc(key)}" aria-pressed="${sel === key}">
      <span class="grip" aria-hidden="true">⋮⋮</span><span class="asg-tname">${esc(t.title)}</span><span class="muted small">${t.hours} h</span>${t.docs ? `<span class="docmark" title="Needs documents" aria-label="Needs documents">📄</span>` : ""}${extra || ""}</button>`;
  const drafts = (S.asgDrafts || []).map(x => `<div class="asg-draft">${tcard("draft:" + x.k, { title: x.title, hours: x.hours, docs: x.docs }, `<span class="chip asg-newchip">New</span>`)}<button type="button" class="btn ghost asg-x" data-asgdrop="${x.k}" aria-label="Remove ${esc(x.title)}">✕</button></div>`).join("");
  const tpls = S.tpls === undefined ? `<span class="muted small">Loading repeatable tasks…</span>` : (S.tpls || []).map((t, i) => tcard("tpl:" + i, { title: t.name, hours: t.hours, docs: t.docs })).join("") || `<span class="muted small">No repeatable tasks yet. Use Edit list to add some.</span>`;
  const left = `<section class="panel asg-col asg-left" aria-label="Tasks to give"><div class="asg-h"><h3>Tasks to give</h3><span style="flex:1"></span><button class="btn" type="button" id="asgTplEdit">Edit list</button></div>
    <p class="muted small asg-help">Drag a card onto a person or a department. On touch: tap a card, then tap a person.</p>
    <div class="asg-tlist"><button type="button" class="tpl asg-task asg-new" draggable="true" data-asgtask="new"><span class="asg-plus" aria-hidden="true">＋</span>New task<span class="muted small">your own title</span></button>${drafts}${tpls}</div></section>`;
  // RIGHT: people by department
  const pcard = (u) => { const s = asgPersonStats(u.name, tasks), on = multi.includes(u.name);
    return `<button type="button" class="asg-target asg-person${on ? " picked" : ""}" data-asgwho="${esc(u.name)}" aria-pressed="${on}" aria-label="${esc(u.name)}, ${esc(u.role || "")}. ${esc(s.line)}. ${s.open} open">
      ${avatar(u.name)}<span class="asg-pi"><b>${esc(u.name)}</b><small class="muted">${esc(u.role || u.dept)}</small><span class="asg-st${s.busy ? " busy" : ""}">${esc(s.line)}</span></span>
      <span class="asg-load" title="${s.open} open task${s.open === 1 ? "" : "s"}"><span class="asg-bar"><i style="width:${Math.min(100, s.open * 20)}%"></i></span><small>${s.open} open</small></span>${on ? `<span class="asg-tick" aria-hidden="true">✓</span>` : ""}</button>`; };
  const dcard = (dname) => { const w = "dept:" + dname, on = multi.includes(w), waiting = tasks.filter(t => !asgOwner(t) && t.dept === dname && asgIsOpen(t)).length;
    return `<button type="button" class="asg-target asg-deptcard${on ? " picked" : ""}" data-asgwho="${esc(w)}" aria-pressed="${on}"><b>Anyone in ${esc(dname)}</b><small class="muted">first to start takes it${waiting ? ` · ${waiting} waiting` : ""}</small>${on ? `<span class="asg-tick" aria-hidden="true">✓</span>` : ""}</button>`; };
  const right = `<section class="panel asg-col asg-right" aria-label="People"><div class="asg-h"><h3>People</h3><span style="flex:1"></span>
      ${multi.length ? `<span class="small"><b>${multi.length}</b> picked</span><button type="button" class="btn ghost" data-asgclear>Clear</button>` : ""}
      <button type="button" class="btn${S.asgPick ? " primary" : ""}" data-asgpick aria-pressed="${!!S.asgPick}">Select several</button></div>
    <p class="muted small asg-help">Ctrl+click (or turn on Select several) to pick more than one, then drop or tap a task to give it to all of them.</p>
    ${depts.map(dn => `<div class="asg-dept"><div class="asg-dh">${esc(dn)}</div>${dcard(dn)}<div class="asg-plist">${users.filter(u => u.dept === dn).map(pcard).join("")}</div></div>`).join("")}</section>`;
  const hint = selTask ? `<div class="asg-hint" role="status"><span><b>${esc(selTask.title)}</b> selected · now tap a person or “Anyone in …”${multi.length ? ` (it goes to the ${multi.length} picked too)` : ""}</span><button type="button" class="btn ghost" data-asgclear>Cancel (Esc)</button></div>`
    : multi.length ? `<div class="asg-hint" role="status"><span><b>${multi.length}</b> picked: ${esc(multi.map(asgWhoName).join(", "))} · now drop or tap a task to give it to all of them</span><button type="button" class="btn ghost" data-asgclear>Clear (Esc)</button></div>` : "";
  // BELOW: tasks given so far, as cards in status columns
  const who = (t) => asgOwner(t) || t.owners.join(", ");
  const assignees = [...new Set(tasks.map(asgOwner).filter(Boolean))];
  const chips = `<div class="asg-chips" role="group" aria-label="Filter by person"><button type="button" class="asg-chip" data-asgperson="" aria-pressed="${!S.asgPerson}"><span class="avatar asg-all" aria-hidden="true">All</span>Everyone</button>${assignees.map(n => `<button type="button" class="asg-chip" data-asgperson="${esc(n)}" aria-pressed="${S.asgPerson === n}">${avatar(n)}${esc(n)}</button>`).join("")}</div>`;
  const shown = tasks.filter(t => !S.asgPerson || asgOwner(t) === S.asgPerson);
  const pill = (t) => { const c = asgCol(t);
    return c === "done" ? `<span class="pill p-approved">Done ${esc(fmt(t.ended_at || t.decided_at))}</span>` : c === "docs" ? `<span class="pill p-docs">Approved – adding documents</span>`
      : c === "submitted" ? `<span class="pill p-submitted">With ${esc(t.validator)}</span>` : isLate(t) ? `<span class="pill p-late">Overdue · was due ${esc(fmt(t.due_at))}</span>` : `<span class="pill p-assigned">Due ${esc(fmt(t.due_at))}</span>`; };
  const gcard = (t) => `<article class="asg-gcard${isLate(t) && asgIsOpen(t) && t.status !== "submitted" ? " late" : ""}" data-asgopen="${t.id}" data-q="${esc((t.stage + " " + t.stage_name + " " + who(t) + " " + t.validator + " " + (t.bill_id || "")).toLowerCase())}">
      <div class="asg-gtop"><button type="button" class="asg-gcode" data-asgopen="${t.id}" aria-label="Open ${esc(t.stage)} ${esc(t.stage_name)}">${esc(t.stage)}</button>${t.bill_id ? `<span class="chip">${esc(t.bill_id)}</span>` : ""}</div>
      <b class="asg-gtitle">${esc(t.stage_name)}</b>
      <div class="asg-gwho">${asgOwner(t) ? avatar(asgOwner(t)) : `<span class="avatar asg-all" aria-hidden="true">Any</span>`}<span><b>${esc(asgOwner(t) || "Anyone in " + (t.dept || who(t)))}</b><small class="muted">approver ${esc(t.validator)}</small></span></div>
      <div>${pill(t)}</div>
      <div class="asg-gacts">${docsBtn("as" + t.id, `${t.stage} ${t.stage_name} · ${asgOwner(t)}`, t.files)}<span style="flex:1"></span><button class="btn bad" type="button" data-deltask="${t.id}" aria-label="Delete ${esc(t.stage)}">Delete</button></div></article>`;
  const board = `<div class="asg-board">${ASG_COLS.map(([k, l]) => { const list = shown.filter(t => asgCol(t) === k);
    return `<section class="asg-bcol asg-c-${k}" aria-label="${l}"><h4>${l} <span class="asg-n" data-asgcount="${k}">${list.length}</span></h4>${list.map(gcard).join("") || `<p class="muted small asg-none">None</p>`}</section>`; }).join("")}</div>`;
  return hero("Assign tasks", "Drag a task onto a person or a department. The person presses Start (timer runs), Done (sent to the approver), and after approval uploads the documents and ends it.") + hint +
    `<div class="asg-grid">${left}${right}</div>
    <h2>Tasks given so far</h2><div class="asg-gbar">${chips}<input class="search" id="asgq" placeholder="Search code, task, person or bill" value="${esc(S.asgQ || "")}" aria-label="Search tasks given"></div>
    ${tasks.length ? board : `<div class="emptycard">None yet. Drag a task onto someone above.</div>`}`;
}
// The one confirm dialog: change hours, approver, documents, bill and note, then give the task to every target in ONE /api/assign call.
function asgGive(key, whos) {
  const t = asgTask(key); if (!t || !whos.length) return;
  const bills = (S.adhoc && S.adhoc.bills) || [];
  const tgt = whos.map(w => w.startsWith("dept:") ? `<span class="chip">Anyone in ${esc(w.slice(5))}</span>` : `<span class="asg-tg">${avatar(w)}${esc(w)}</span>`).join("");
  dialog(`<h3 style="margin:0 0 4px">${t.isNew ? "Give a new task" : `Give “${esc(t.title)}”`}</h3>
    <div class="asg-tgts">${tgt}</div><p class="muted small" style="margin:4px 0 8px">${whos.length > 1 ? `${whos.length} copies, one each. ` : ""}They get the double beep straight away.${whos.some(w => w.startsWith("dept:")) ? " For a department, the first person to press Start takes it." : ""}</p>
    ${t.isNew ? `<label class="f" for="asgT">What needs doing</label><input class="in" id="asgT" name="title" placeholder="Task title" autocomplete="off">` : `<input type="hidden" name="title" value="${esc(t.title)}">${t.about ? `<p class="small" style="margin:0 0 8px">${esc(t.about)}</p>` : ""}`}
    <div class="row2"><span style="flex:1;min-width:120px"><label class="f" for="asgH">Time limit (hours)</label><input class="in" id="asgH" name="hours" type="number" min="0.25" step="0.25" value="${t.hours}"></span>
      <span style="flex:2;min-width:160px"><label class="f" for="asgC">Approver</label><select class="in" id="asgC" name="checker">${S.meta.users.map(x => `<option ${x.name === S.user ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></span></div>
    <label class="small" style="display:flex;gap:8px;align-items:center;margin-top:12px"><input type="checkbox" name="docs" ${t.docs ? "checked" : ""} style="accent-color:#0071e3"> Needs documents after approval</label>
    <label class="f" for="asgB">Bill (optional)</label><select class="in" id="asgB" name="bill"><option value="">No bill</option>${bills.map(b => `<option value="${esc(b.id)}">${esc(b.id)} · ${esc(b.client)}</option>`).join("")}</select>
    <label class="f" for="asgN">Note (optional)</label><input class="in" id="asgN" name="output" value="${esc(t.isNew ? "" : t.about)}" placeholder="What to deliver">`,
    async (fd) => {
      const title = String(fd.get("title") || "").trim(); if (!title) return note("Nothing to give", "Type what needs doing.");
      const row = { title, checker: fd.get("checker"), hours: fd.get("hours"), docs: fd.get("docs") === "on", bill: fd.get("bill") || "", output: String(fd.get("output") || "").trim() };
      try {
        const r = await api("/api/assign", { tasks: whos.map(w => ({ ...row, who: w })) });
        note(`${r.codes.join(", ")} given to ${whos.map(asgWhoName).join(", ")}`, title, "approved");
        if (t.draft) S.asgDrafts = (S.asgDrafts || []).filter(x => x.k !== t.draft);
        S.asgSel = null; S.asgMulti = []; S.asgPick = false;
        S.adhoc = await api("/api/adhoc"); render();
      } catch (e) { note("Couldn't give the task", e.message); }
    });
}
function asgNewDraft() {   // "＋ New task": a small form, then the task waits at the top of the list as a draggable card
  dialog(`<h3 style="margin:0 0 8px">New task</h3><p class="muted small" style="margin:0 0 6px">It appears at the top of “Tasks to give”. Then drag it onto someone, or tap a person.</p>
    <label class="f" for="nwT">What needs doing</label><input class="in" id="nwT" name="title" placeholder="Task title" autocomplete="off">
    <div class="row2"><span style="flex:1"><label class="f" for="nwH">Time limit (hours)</label><input class="in" id="nwH" name="hours" type="number" min="0.25" step="0.25" value="4"></span>
      <label class="small" style="display:flex;gap:8px;align-items:center;margin-top:30px;flex:1"><input type="checkbox" name="docs" style="accent-color:#0071e3"> Needs documents</label></div>
    <label class="f" for="nwN">Note (optional)</label><input class="in" id="nwN" name="output" placeholder="What to deliver">`,
    (fd) => { const title = String(fd.get("title") || "").trim(); if (!title) return note("Nothing added", "Type what needs doing.");
      const k = Date.now(); S.asgDrafts = [{ k, title, hours: Number(fd.get("hours")) || 4, docs: fd.get("docs") === "on", output: String(fd.get("output") || "").trim() }].concat(S.asgDrafts || []);
      S.asgSel = "draft:" + k; render(); });
}
function asgFilterGiven() {   // search filters the cards in place, so typing never loses focus
  const q = (S.asgQ || "").toLowerCase().trim();
  document.querySelectorAll(".asg-bcol").forEach(col => { let n = 0;
    col.querySelectorAll(".asg-gcard").forEach(c => { const hit = !q || c.dataset.q.includes(q); c.hidden = !hit; if (hit) n++; });
    const cnt = col.querySelector("[data-asgcount]"); if (cnt) cnt.textContent = n; });
}
function wireAssign() {
  const app = $("#app"); S.asgMulti = S.asgMulti || [];
  const clearDrag = () => { document.body.classList.remove("asg-dragging"); app.querySelectorAll(".asg-target.drop").forEach(x => x.classList.remove("drop")); };
  const targetsFor = (who) => S.asgMulti.length ? [...new Set(S.asgMulti.concat(who ? [who] : []))] : [who];
  // task cards: drag, or click to select (Enter/Space too)
  app.querySelectorAll("[data-asgtask]").forEach(el => { const key = el.dataset.asgtask, m = /^tpl:(\d+)$/.exec(key);
    if (m) { const fake = { dataset: { tpl: m[1] }, getBoundingClientRect: () => el.getBoundingClientRect() };
      el.onmouseenter = el.onfocus = () => tplTip(fake); el.onmouseleave = el.onblur = hideTip; }
    el.ondragstart = (e) => { hideTip(); e.dataTransfer.setData("text/plain", "asg:" + key); e.dataTransfer.effectAllowed = "copy"; document.body.classList.add("asg-dragging"); };
    el.ondragend = clearDrag;
    el.onclick = () => { hideTip();
      if (S.asgMulti.length) return asgGive(key, S.asgMulti.slice());   // people already picked: give straight away
      if (key === "new") return asgNewDraft();
      S.asgSel = S.asgSel === key ? null : key; render(); };
  });
  // people and department cards: drop targets, click to give / Ctrl+click to pick several
  app.querySelectorAll("[data-asgwho]").forEach(el => { const who = el.dataset.asgwho;
    el.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; el.classList.add("drop"); };
    el.ondragleave = (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("drop"); };
    el.ondrop = (e) => { e.preventDefault(); clearDrag(); const v = e.dataTransfer.getData("text/plain"); if (v.startsWith("asg:")) asgGive(v.slice(4), targetsFor(who)); };
    el.onclick = (e) => {
      if (e.ctrlKey || e.metaKey || S.asgPick) { S.asgMulti = S.asgMulti.includes(who) ? S.asgMulti.filter(x => x !== who) : S.asgMulti.concat(who); return render(); }
      if (S.asgSel) return asgGive(S.asgSel, targetsFor(who));
      note("Pick a task first", "Tap a task card on the left, then tap a person. Or drag the card onto them.", "validate");
    };
  });
  app.querySelectorAll("[data-asgclear]").forEach(b => b.onclick = () => { S.asgSel = null; S.asgMulti = []; S.asgPick = false; render(); });
  app.querySelectorAll("[data-asgpick]").forEach(b => b.onclick = () => { S.asgPick = !S.asgPick; render(); });
  app.querySelectorAll("[data-asgdrop]").forEach(b => b.onclick = () => { const k = Number(b.dataset.asgdrop); S.asgDrafts = (S.asgDrafts || []).filter(x => x.k !== k); if (S.asgSel === "draft:" + k) S.asgSel = null; render(); });
  const ed = $("#asgTplEdit"); if (ed) ed.onclick = editTemplates;
  // tasks given so far: person filter, search, open a card, refresh after Delete
  app.querySelectorAll("[data-asgperson]").forEach(b => b.onclick = () => { S.asgPerson = b.dataset.asgperson; render(); });
  const q = $("#asgq"); if (q) q.oninput = () => { S.asgQ = q.value; asgFilterGiven(); };
  asgFilterGiven();
  app.querySelectorAll(".asg-gcard").forEach(c => c.onclick = (e) => { const b = e.target.closest("button,a"); if (b && !b.matches(".asg-gcode")) return; openTask(Number(c.dataset.asgopen)); });
  app.querySelectorAll(".asg-gcard [data-deltask]").forEach(b => b.addEventListener("click", () => {   // shell.js opens deleteTask(); refresh this page once the dialog closes
    const dl = $("#dlg"); if (dl) dl.addEventListener("close", () => setTimeout(async () => { if (S.tab !== "assign") return; try { S.adhoc = await api("/api/adhoc"); render(); } catch (e) {} }, 400), { once: true }); }));
  if (!S.asgEsc) { S.asgEsc = true;   // Esc clears the selection (once, for the whole app)
    document.addEventListener("keydown", (e) => { if (e.key !== "Escape" || S.tab !== "assign" || document.querySelector("dialog[open]")) return;
      if (S.asgSel || (S.asgMulti && S.asgMulti.length) || S.asgPick) { S.asgSel = null; S.asgMulti = []; S.asgPick = false; render(); } }); }
}
