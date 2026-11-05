// Page: Pipeline (Timetable view + Bills x stages view) and the hover popups.
"use strict";
function optionalStages() {
  const nexts = new Set(S.meta.stages.flatMap(s => s.next || [])), br = new Set(S.meta.stages.flatMap(s => Object.values((s.branch || {}).options || {}).flat()));
  return new Set([...br].filter(c => !nexts.has(c)));
}
function billProgress(b) {
  const opt = optionalStages(), stages = S.pipe.stages.filter(s => !opt.has(s.code) || b.cells[s.code]);
  const done = stages.filter(s => (b.cells[s.code] || {}).status === "approved").length;
  return { done, total: stages.length, pct: Math.round(done / Math.max(1, stages.length) * 100), late: Object.values(b.cells).some(c => c.late),
           now: Object.entries(b.cells).filter(([, c]) => c.status !== "approved").map(([k]) => k) };
}
const hasDemo = () => !!(S.pipe && S.pipe.bills.some(b => b.demo));
const pBills = () => (S.pipe ? S.pipe.bills : []).filter(b => S.showDemo !== false || !b.demo);
const demoToggle = () => hasDemo() || (S.tt && S.tt.has_demo) || (S.tr && S.tr.has_demo) ? `<label class="small" style="display:flex;gap:6px;align-items:center;white-space:nowrap"><input type="checkbox" data-demo ${S.showDemo !== false ? "checked" : ""} style="accent-color:#0071e3"> Show demo data</label>` : "";
const demoTag = (b) => b && b.demo ? ` <span class="chip" style="background:#fff1e0;color:#c25e00">Demo</span>` : "";
function pipeFiltered() {
  const p = S.pipe; const qtxt = (S.pq || "").toLowerCase(), f = S.pf || "all";
  return pBills().filter(b => (!qtxt || (b.id + " " + b.client).toLowerCase().includes(qtxt)) &&
    (f === "all" || (f === "open" && b.status !== "complete") || (f === "complete" && b.status === "complete") || (f === "late" && billProgress(b).late)));
}
function exportCsv() {
  const p = S.pipe, rows = [["Bill", "Client", "Status", "Progress %", ...p.stages.map(s => s.code)]];
  pipeFiltered().forEach(b => rows.push([b.id, b.client, b.status, billProgress(b).pct, ...p.stages.map(s => b.cells[s.code] ? (STATUS[b.cells[s.code].status] || b.cells[s.code].status) + (b.cells[s.code].late ? " (late)" : "") : "")]));
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv" }));
  a.download = `Pipeline_${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(a); a.click(); a.remove();
}
function viewPipe() {
  const views = `<div class="seg" style="margin-bottom:16px">${[["time", "Timetable"], ["bills", "Bills × stages"]].map(([k, l]) => `<button type="button" data-pv="${k}" aria-selected="${(S.pv || "time") === k}">${l}</button>`).join("")}</div>`;
  return (S.pv || "time") === "time" ? viewTimetable(views) : viewBills(views);
}
// ---------- timetable: a row per employee, hours across the top, a block per task they worked on
function showTip(el) {
  const b = (S.tips || {})[el.dataset.tip]; if (!b) return;
  let pop = $("#ttPop"); if (!pop) { pop = document.createElement("div"); pop.id = "ttPop"; pop.setAttribute("role", "tooltip"); document.body.appendChild(pop); }
  const t = (v) => esc(String(v).slice(11, 16)), fin = b.status === "Done";
  pop.innerHTML = `<div class="hd">${fin ? `<span class="done">✓ Finished</span>` : `<span class="pill ${b.running ? "p-in_progress" : /approval/.test(b.status) ? "p-submitted" : /documents/.test(b.status) ? "p-docs" : /Sent back/.test(b.status) ? "p-late" : "p-assigned"}">${esc(b.status)}</span>`}${b.demo ? `<span class="chip" style="background:#fff1e0;color:#c25e00">Demo</span>` : ""}</div>
    <div style="font-weight:700;font-size:15px">${esc(b.task)}</div><div class="muted small">${esc(b.code)}${b.bill ? " · " + esc(b.bill) : " · task from the admin"}</div>
    <dl><dt>Person</dt><dd>${esc(b.person)}</dd><dt>${fin ? "Worked" : "Timer"}</dt><dd>${t(b.start)} – ${b.running ? "now" : t(b.end)}</dd><dt>Time</dt><dd>${clock(b.seconds)}${b.running ? " and counting" : ""}</dd></dl>
    ${b.bill ? `<div class="muted small" style="margin-top:8px">Click to open the bill</div>` : /^TASK-/.test(b.code) ? `<div class="muted small" style="margin-top:8px">Click for details, documents or delete</div>` : ""}`;
  const r = el.getBoundingClientRect(); pop.classList.add("show");
  const w = pop.offsetWidth, h = pop.offsetHeight;
  pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  pop.style.top = (r.top - h - 10 > 8 ? r.top - h - 10 : r.bottom + 10) + "px";
}
function hideTip() { const pop = $("#ttPop"); if (pop) pop.classList.remove("show"); }
function lanesOf(blocks) {   // overlapping blocks (two tasks at once) go on separate lines
  const ends = [];
  blocks.slice().sort((a, b) => pts(a.start) - pts(b.start)).forEach(b => {
    let i = ends.findIndex(e => e <= pts(b.start)); if (i < 0) { i = ends.length; ends.push(0); }
    ends[i] = pts(b.end); b.lane = i; });
  return Math.max(1, ends.length);
}
function viewTimetable(views) {
  const d = S.tt; if (!d) return hero("Pipeline", "") + views + `<p class="empty">Loading…</p>`;
  const H = d.end_hour - d.start_hour, day0 = pts(d.date + " 00:00:00");
  const pos = (v) => Math.max(0, Math.min(100, ((pts(v) - day0) / 3600000 - d.start_hour) / H * 100));
  const qtxt = (S.ttq || "").toLowerCase(), dept = S.ttd || "";
  const depts = [...new Set(d.people.map(p => p.dept))];
  const people = d.people.filter(p => (!qtxt || (p.name + " " + p.dept + " " + p.blocks.map(b => b.task).join(" ")).toLowerCase().includes(qtxt)) && (!dept || p.dept === dept)
    && (!S.ttBusy || p.blocks.length || p.now || p.queued.length || p.waiting.length || p.docs.length));
  const hours = Array.from({ length: H + 1 }, (_, i) => d.start_hour + i);
  const hourLbl = (h) => `${(h % 12) || 12}${h < 12 || h === 24 ? " AM" : " PM"}`;
  const head = `<div class="tt-row tt-head"><div class="tt-who"><b>${esc(new Date(day0).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }))}</b></div>
    <div class="tt-track" style="--h:${H}">${hours.map((h, i) => `<span class="tt-h" style="left:${i / H * 100}%">${i < H ? hourLbl(h) : ""}</span>`).join("")}</div></div>`;
  const lunch = d.lunch ? `<div class="tt-lunch" style="left:${pos(d.lunch[0])}%;width:${pos(d.lunch[1]) - pos(d.lunch[0])}%" title="Lunch break"></div>` : "";
  const nowLine = d.today ? `<div class="tt-now" style="left:${pos(d.server_now)}%"></div>` : "";
  const cls = (st) => /Running/.test(st) ? "b-run" : /approval/.test(st) ? "b-wait" : /documents/.test(st) ? "b-docs" : /Sent back/.test(st) ? "b-back" : "b-done";
  const status = (p) => p.now ? `<span class="pill p-in_progress">● ${esc(p.now.task)}</span>` : p.docs.length ? `<span class="pill p-docs">Add documents: ${esc(p.docs[0].task)}</span>`
    : p.waiting.length ? `<span class="pill p-submitted">Waiting approval: ${esc(p.waiting[0].task)}</span>` : p.queued.length ? `<span class="pill p-assigned">${p.queued.length} up next</span>` : `<span class="muted small">Free</span>`;
  const rows = people.map(p => `<div class="tt-row" data-person="${esc(p.name)}"><div class="tt-who" title="${S.selTpl != null ? "Click to give the selected task" : "Drop a repeatable task here"}">${avatar(p.name)}<div style="min-width:0"><b>${esc(p.name)}</b><div class="muted small">${esc(p.dept)}</div><div style="margin-top:4px">${status(p)}</div></div>
      <div class="tt-tot">${d.today && p.now ? tick(p.seconds, d.server_now, "timer sm") : `<span class="timer sm">${clock(p.seconds)}</span>`}</div></div>
    <div class="tt-track" style="--h:${H};min-height:${Math.max(64, 26 + lanesOf(p.blocks) * 34)}px">${lunch}${nowLine}${p.blocks.map(b => { const l = pos(b.start), w = Math.max(0.6, pos(b.end) - l);
      const k = "tb" + (S.tipN = (S.tipN || 0) + 1); S.tips = S.tips || {}; S.tips[k] = { ...b, person: p.name };
      return `<div class="tt-b ${cls(b.status)} ${b.demo ? "b-demo" : ""}" style="left:${l}%;width:max(14px, ${w}%);top:${10 + b.lane * 34}px" ${b.bill ? `data-bill="${esc(b.bill)}"` : /^TASK-/.test(b.code) ? `data-task="${b.task_id}"` : ""} data-tip="${k}" tabindex="0" aria-label="${esc(b.task + ", " + b.status)}"><span>${b.status === "Done" ? "✓ " : ""}${esc(b.task)}</span></div>`; }).join("")}
      ${p.queued.length ? `<div class="tt-q" title="${esc(p.queued.map(x => x.code + " " + x.task).join(" · "))}">Up next: ${esc(p.queued.slice(0, 2).map(x => x.task).join(", "))}${p.queued.length > 2 ? ` +${p.queued.length - 2}` : ""}</div>` : ""}</div></div>`).join("");
  return hero("Pipeline", `Who is working on what, hour by hour. ${d.lunch ? "Lunch is shaded." : ""} Hover a block for details, click one to open it. Drag a repeatable task onto a person to give it.`,
      `<div class="daypick"><input class="in" type="date" id="ttDate" value="${esc(d.date)}" max="${today()}" style="width:auto"></div>`) + views +
    `<div class="toolbar"><input class="search" id="ttq" placeholder="Search person or task" value="${esc(S.ttq || "")}">
      <select class="in" id="ttd" style="width:auto"><option value="">All departments</option>${depts.map(x => `<option ${x === dept ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
      <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ttBusy" ${S.ttBusy ? "checked" : ""} style="accent-color:#0071e3"> Only people with tasks</label>${demoToggle()}</div>
    <div class="legend"><span class="tt-key b-run"></span> running <span class="tt-key b-wait"></span> waiting for approval <span class="tt-key b-docs"></span> approved – adding documents <span class="tt-key b-done"></span> finished <span class="tt-key b-back"></span> sent back <span class="tt-key tt-lk"></span> lunch${d.today ? ` <span style="display:inline-block;width:2px;height:12px;background:#ff3b30"></span> now` : ""}</div>
    ${viewPalette()}<div class="panel tt">${head}${rows || `<p class="empty">Nobody matches.</p>`}</div>`;
}
function viewBills(views) {
  const p = S.pipe; if (!p) return "";
  const open = pBills().filter(b => b.status !== "complete").length;
  const fl = [["all", "All"], ["open", "Open"], ["late", "Overdue"], ["complete", "Complete"]];
  const head = `<tr><th style="text-align:left">Bill</th>${p.stages.map(s => `<th title="${esc(s.name)} · ${esc(s.dept)}">${esc(s.code)}</th>`).join("")}<th>Status</th></tr>`;
  const rows = pipeFiltered().map(b => { const pr = billProgress(b); return `<tr><td class="bill">${billBtn(b.id)}${demoTag(b)}<div class="muted small" style="font-weight:500">${esc(b.client)}</div><div class="prog" style="margin-top:6px" title="${pr.done} of ${pr.total} stages"><i style="width:${pr.pct}%"></i></div></td>${p.stages.map(s => {
    const c = b.cells[s.code]; if (!c) return "<td></td>";
    const lab = c.status === "approved" ? "✓" : c.status === "submitted" ? "check" : c.status === "in_progress" ? "doing" : "new";
    return `<td><span class="cell c-${c.status} ${c.late ? "c-late" : ""}" title="${esc(s.name)} · ${esc(c.who)}${c.rework ? " · reworked " + c.rework + "x" : ""}">${lab}${c.rework ? " ↺" : ""}</span><div class="muted" style="font-size:11px">${esc((c.who || "").split(",")[0])}</div></td>`;
  }).join("")}<td><span class="pill ${b.status === "complete" ? "p-approved" : "p-assigned"}">${b.status === "complete" ? "Complete" : "Open"}</span><div class="muted small">${pr.pct}%</div></td></tr>`; }).join("");
  return hero("Pipeline", `${pBills().length} bills · ${open} open · columns follow the stages of the current workflow`) + views +
    `<div class="toolbar"><input class="search" id="pq" placeholder="Search bill or client" value="${esc(S.pq || "")}" aria-label="Search bills">${demoToggle()}
      <div class="seg">${fl.map(([k, l]) => `<button type="button" data-pf="${k}" aria-selected="${(S.pf || "all") === k}">${l}</button>`).join("")}</div>
      <span style="flex:1"></span><button class="btn" id="csv" type="button">Export CSV</button></div>` +
    `<div class="legend"><span class="cell c-assigned">new</span> to start <span class="cell c-in_progress">doing</span> in progress <span class="cell c-submitted">check</span> with the checker <span class="cell c-approved">✓</span> handed over <span class="cell c-assigned c-late">late</span> past time limit · ↺ sent back</div>
    <div class="panel scroll"><table><thead>${head}</thead><tbody>${rows || `<tr><td colspan="99" class="empty">No bills match.</td></tr>`}</tbody></table></div>`;
}
