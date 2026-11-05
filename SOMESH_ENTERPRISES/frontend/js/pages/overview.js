// Page: Overview.
"use strict";
// ---------------------------------------------------------- overview (leads / CEO)
function viewOverview() {
  const p = S.pipe; if (!p) return `<p class="empty">Loading…</p>`;
  const open = pBills().filter(b => b.status !== "complete"), done = pBills().filter(b => b.status === "complete");
  const cells = open.flatMap(b => Object.entries(b.cells).map(([code, c]) => ({ ...c, code, bill: b })));
  const active = cells.filter(c => c.status !== "approved"), late = active.filter(c => c.late), checking = active.filter(c => c.status === "submitted");
  const avg = open.length ? Math.round(open.reduce((a, b) => a + billProgress(b).pct, 0) / open.length) : 100;
  const stageOf = Object.fromEntries(p.stages.map(s => [s.code, s]));
  const byDept = {}; active.forEach(c => { const d = (stageOf[c.code] || {}).dept || "Other"; byDept[d] = byDept[d] || { n: 0, late: 0, chk: 0 }; byDept[d].n++; if (c.late) byDept[d].late++; if (c.status === "submitted") byDept[d].chk++; });
  const maxD = Math.max(1, ...Object.values(byDept).map(v => v.n));
  const byStage = {}; active.forEach(c => { byStage[c.code] = (byStage[c.code] || 0) + 1; });
  const top = Object.entries(byStage).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const depts = Object.entries(byDept).sort((a, b) => b[1].n - a[1].n).map(([d, v]) => `<div class="bar2"><span>${esc(d)}</span><div class="track" title="${v.n} open · ${v.late} overdue · ${v.chk} with checker">
      <i style="width:${(v.n - v.late - v.chk) / maxD * 100}%;background:#0071e3"></i><i style="width:${v.chk / maxD * 100}%;background:#af52de"></i><i style="width:${v.late / maxD * 100}%;background:#ff3b30"></i></div><b>${v.n}</b></div>`).join("") || `<p class="muted">No open work.</p>`;
  const bills = open.concat(done).map(b => { const pr = billProgress(b);
    return `<div class="billrow"><div>${billBtn(b.id)}${demoTag(b)}<div class="muted small">${esc(b.client)}</div></div><div class="small">${b.status === "complete" ? `<span class="pill p-approved">Complete</span>` : pr.late ? `<span class="pill p-late">Overdue</span>` : `<span class="muted">Now at ${esc(pr.now.join(", "))}</span>`}</div>
      <div class="prog" title="${pr.done} of ${pr.total} stages"><i style="width:${pr.pct}%"></i></div><b class="small" style="text-align:right">${pr.done}/${pr.total}</b></div>`; }).join("");
  return hero("Overview", `${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })} · live`, demoToggle()) +
    (!pBills().length ? `<div class="emptycard" style="margin-bottom:16px">No bills yet. Open one on <b>New bill</b>, or load the demo data there to try the app.</div>` : "") +
    `<div class="kpis"><div class="kpi blue"><span>Open bills</span><b>${open.length}</b></div><div class="kpi"><span>Completed</span><b style="color:var(--green)">${done.length}</b></div>
     <div class="kpi red"><span>Overdue tasks</span><b>${late.length}</b></div><div class="kpi purple"><span>With checkers</span><b>${checking.length}</b></div><div class="kpi orange"><span>Avg. progress (open)</span><b>${avg}%</b></div></div>
    <div class="cols" style="margin-top:18px"><div class="panel"><h3>Where work is waiting</h3><p class="muted small"><span style="color:#0071e3">■</span> open <span style="color:#af52de">■</span> with checker <span style="color:#ff3b30">■</span> overdue</p><div class="bars">${depts}</div></div>
      <div class="panel"><h3>Busiest stages</h3><p class="muted small">Open tasks per stage: the likely bottlenecks.</p><div class="bars">${top.map(([c, n]) => `<div class="bar2"><span><b style="text-align:left">${esc(c)}</b> ${esc((stageOf[c] || {}).name || "")}</span><div class="track"><i style="width:${n / Math.max(1, top[0][1]) * 100}%;background:#ff9500"></i></div><b>${n}</b></div>`).join("") || `<p class="muted">Nothing waiting.</p>`}</div></div></div>
    <h2>Every bill</h2><div class="list">${bills || `<p class="empty">No bills yet.</p>`}</div>`;
}
