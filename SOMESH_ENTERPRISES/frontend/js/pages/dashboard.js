// Page: Dashboard (charts and gap analysis).
"use strict";
// ---------------------------------------------------------- v2: Dashboard
const PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
const SEQ = ["#eef5fe", "#cde2fb", "#9cc5f4", "#6aa5ea", "#3b82dc", "#2a63b8", "#1a4b91", "#0d366b"];
const hrs = (s) => (s / 3600).toFixed(1);
const hTxt = (s) => { s = Math.round(s / 60); return s >= 60 ? `${Math.floor(s / 60)} h ${String(s % 60).padStart(2, "0")} m` : `${s} m`; };
const ct = (html) => `data-ct="${esc(html)}"`;
function dashUrl() {
  const p = S.dp || "30", t = today();
  let from = S.dFrom, to = S.dTo || t;
  if (p !== "custom") { const d = new Date(t + "T00:00:00"); to = t;
    if (p === "month") from = t.slice(0, 8) + "01"; else { d.setDate(d.getDate() - Number(p) + 1); from = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; } }
  return `/api/dashboard?from=${from}&to=${to}${S.showDemo !== false ? "&demo=1" : ""}`;
}
function deptColors() {
  const ds = [...new Set(S.meta.users.map(u => u.dept))]; const m = {};
  ds.forEach((d, i) => m[d] = i < PAL.length - 1 ? PAL[i] : "#8e8e93"); return m;
}
function viewDash() {
  const D = S.dash;
  const per = [["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["month", "This month"], ["custom", "Pick dates"]];
  const depts = [...new Set(S.meta.users.map(u => u.dept))];
  const filters = `<div class="toolbar"><div class="seg">${per.map(([k, l]) => `<button type="button" data-dp="${k}" aria-selected="${(S.dp || "30") === k}">${l}</button>`).join("")}</div>
    ${(S.dp || "30") === "custom" ? `<input class="in" type="date" id="dFrom" value="${esc(S.dFrom || (D && D.from) || "")}" style="width:auto"> to <input class="in" type="date" id="dTo" value="${esc(S.dTo || (D && D.to) || today())}" style="width:auto">` : ""}
    <select class="in" id="dDept" style="width:auto"><option value="">All departments</option>${depts.map(d => `<option ${S.dDept === d ? "selected" : ""}>${esc(d)}</option>`).join("")}</select>
    <select class="in" id="dPerson" style="width:auto"><option value="">Everyone</option>${S.meta.users.filter(u => !S.dDept || u.dept === S.dDept).map(u => `<option ${S.dPerson === u.name ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select>
    ${D && D.has_demo ? `<label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-demo ${S.showDemo !== false ? "checked" : ""} style="accent-color:#0071e3"> Include demo data</label>` : ""}
    <span style="flex:1"></span><button class="btn" type="button" id="dCsv">Export CSV</button><button class="btn" type="button" id="dPrint">Print / Save PDF</button></div>`;
  if (!D) return hero("Dashboard", "") + filters + skeleton("chart", 240);
  const ppl = D.people.filter(p => (!S.dDept || p.dept === S.dDept) && (!S.dPerson || p.name === S.dPerson));
  const act = ppl.filter(p => p.worked > 0);
  const worked = ppl.reduce((a, p) => a + p.worked, 0), avail = act.reduce((a, p) => a + p.available, 0), idle = act.reduce((a, p) => a + p.idle, 0);
  const fin = ppl.reduce((a, p) => a + p.finished, 0);
  const gaps = D.gaps.filter(g => !S.dDept || g.dept === S.dDept);
  const late = gaps.reduce((a, g) => a + g.late, 0), rework = gaps.reduce((a, g) => a + g.rework, 0);
  const over = gaps.filter(g => g.verdict === "over"), gen = gaps.filter(g => g.verdict === "generous");
  const range = `${new Date(D.from + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })} – ${new Date(D.to + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
  const tiles = `<div class="kpis">
    <div class="kpi blue"><span>Hours worked</span><b>${hrs(worked)}</b><small class="muted">${act.length} ${act.length === 1 ? "person" : "people"} active</small></div>
    <div class="kpi"><span>Tasks finished</span><b style="color:var(--green)">${fin}</b><small class="muted">avg ${hTxt(D.totals.avg_task)} each</small></div>
    <div class="kpi"><span>Time used of working hours</span><b>${avail ? Math.round(worked / avail * 100) : 0}%</b><small class="muted">on days they worked</small></div>
    <div class="kpi orange"><span>Idle gaps (15 min +)</span><b>${hrs(idle)} h</b><small class="muted">inside working hours</small></div>
    <div class="kpi red"><span>Late / sent back</span><b>${late} / ${rework}</b><small class="muted">tasks past limit / reworks</small></div>
    <div class="kpi purple"><span>Time-limit gaps</span><b>${over.length + gen.length}</b><small class="muted">${over.length} over · ${gen.length} too generous</small></div></div>`;
  const empty = !worked ? `<div class="emptycard" style="margin-top:16px;padding:36px">No timer records in this period${S.dDept ? " for " + esc(S.dDept) : ""}. Records appear as people press Start on tasks.</div>` : "";
  const printHead = `<div class="printhead"><b>${APP} · Dashboard</b><span>${range}${S.dDept ? " · " + esc(S.dDept) : ""}${S.dPerson ? " · " + esc(S.dPerson) : ""} · printed ${new Date().toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })}</span></div>`;
  return printHead + hero("Dashboard", `${range} · how the team's working time was spent, and where the gaps are`) + filters + tiles + empty + (worked ? `
    <div class="dgrid">
      <div class="panel span2"><h3>Hours worked per day</h3><p class="muted small">Stacked by department. Hover a bar for the split.</p>${chartDaily(D, ppl)}</div>
      <div class="panel span2"><h3>Day by day, per person</h3><p class="muted small">Darker = more hours. Hover a cell for the exact time.</p>${chartHeat(D, act)}</div>
      <div class="panel"><h3>Time used of working hours</h3><p class="muted small">Worked ÷ available (${esc(ampm(D.workday.start))}–${esc(ampm(D.workday.end))} minus lunch) on the days each person worked.</p>${chartUtil(act)}</div>
      <div class="panel"><h3>Idle gaps</h3><p class="muted small">Breaks of 15 minutes or more between tasks, inside working hours (lunch excluded).</p>${chartIdle(act)}</div>
      <div class="panel span2"><h3>Is the time limit right?</h3><p class="muted small">Average actual time (dot) against the time limit (ring) for every task finished in the period. Over 1.2× the limit: needs more time or help. Under half the limit: the limit can be cut.</p>${chartGap(gaps)}</div>
      <div class="panel span2"><h3>Suggestions</h3>${gapTable(gaps)}</div>
      <div class="panel"><h3>By department</h3><p class="muted small">Share of all hours worked.</p>${chartDept(D, ppl)}</div>
      <div class="panel"><h3>Where the time went</h3><p class="muted small">Tasks that took the most total hours.</p>${chartTop(gaps)}</div>
    </div>` : "");
}
function chartDaily(D, ppl) {
  const col = deptColors(), depts = [...new Set(ppl.map(p => p.dept))].filter(d => ppl.some(p => p.dept === d && p.worked));
  const days = D.days, W = 1120, H = 260, L = 40, B = 26, T = 10, pw = W - L - 10, ph = H - B - T;
  const tot = days.map(d => ppl.reduce((a, p) => a + (p.days[d] || 0), 0));
  const max = Math.max(3600, ...tot); const step = max / 3600 > 40 ? 10 : max / 3600 > 16 ? 4 : max / 3600 > 6 ? 2 : 1;
  const top = Math.ceil(max / 3600 / step) * step; const y = (h) => T + ph - h / top * ph;
  const bw = Math.max(4, Math.min(38, pw / days.length * 0.62)), gx = (i) => L + pw / days.length * (i + 0.5);
  let g = ""; for (let h = 0; h <= top; h += step) g += `<line x1="${L}" x2="${W - 10}" y1="${y(h)}" y2="${y(h)}" class="grid"/><text x="${L - 6}" y="${y(h) + 4}" class="ax" text-anchor="end">${h}</text>`;
  const every = Math.ceil(days.length / 12);
  const bars = days.map((d, i) => { let acc = 0; const segs = depts.map(dp => { const v = ppl.filter(p => p.dept === dp).reduce((a, p) => a + (p.days[d] || 0), 0); const y0 = acc; acc += v / 3600; return { dp, v, y0, y1: acc }; }).filter(s => s.v > 0);
    const lbl = new Date(d + "T00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
    const tip = `<b>${lbl}</b> · ${hTxt(tot[i])}<br>` + segs.map(s => `<i class="sw" style="background:${col[s.dp]}"></i>${esc(s.dp)}: ${hTxt(s.v)}`).join("<br>");
    const rects = segs.map((s, k) => { const top_ = y(s.y1), hgt = Math.max(1, y(s.y0) - y(s.y1) - (k ? 2 : 0)); const last = k === segs.length - 1;
      return last ? `<path d="${rr(gx(i) - bw / 2, top_, bw, hgt, Math.min(4, hgt))}" fill="${col[s.dp]}"/>` : `<rect x="${gx(i) - bw / 2}" y="${top_}" width="${bw}" height="${hgt}" fill="${col[s.dp]}"/>`; }).join("");
    return `<g class="hit" ${ct(tip)}><rect x="${gx(i) - pw / days.length / 2}" y="${T}" width="${pw / days.length}" height="${ph}" fill="transparent"/>${rects}</g>${i % every === 0 ? `<text x="${gx(i)}" y="${H - 8}" class="ax" text-anchor="middle">${esc(new Date(d + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }))}</text>` : ""}`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Hours worked per day">${g}${bars}<text x="4" y="${T + 4}" class="ax">h</text></svg>${legend(depts.map(d => [d, col[d]]))}`;
}
const rr = (x, y, w, h, r) => `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
const legend = (items) => items.length > 1 ? `<div class="clegend">${items.map(([l, c]) => `<span><i class="sw" style="background:${c}"></i>${esc(l)}</span>`).join("")}</div>` : "";
function chartHeat(D, act) {
  const days = D.days, max = Math.max(1, ...act.flatMap(p => days.map(d => p.days[d] || 0)));
  const shade = (v) => v ? SEQ[Math.min(SEQ.length - 1, 1 + Math.floor(v / max * (SEQ.length - 1.01)))] : "var(--card2)";
  const show = days.length > 31 ? days.slice(-31) : days;
  const head = `<div class="hm-row hm-head" style="--n:${show.length}"><span></span>${show.map(d => { const x = new Date(d + "T00:00"); return `<span class="ax2">${x.toLocaleDateString("en-IN", { weekday: "narrow" })}<br>${x.getDate()}</span>`; }).join("")}<span class="ax2">Total</span></div>`;
  const rows = act.sort((a, b) => b.worked - a.worked).map(p => `<div class="hm-row" style="--n:${show.length}"><span class="hm-name">${esc(p.name)}<small class="muted">${esc(p.dept)}</small></span>${show.map(d => { const v = p.days[d] || 0;
      return `<span class="hm-c" style="background:${shade(v)}" ${ct(`<b>${esc(p.name)}</b><br>${new Date(d + "T00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" })}<br>${v ? hTxt(v) + " worked" : "No timer records"}`)}></span>`; }).join("")}<b class="small">${hrs(p.worked)} h</b></div>`).join("");
  return `<div class="hm">${head}${rows}</div><div class="clegend"><span>Less</span>${SEQ.slice(1).map(c => `<i class="sw" style="background:${c}"></i>`).join("")}<span>More</span>${days.length > 31 ? `<span class="muted">· last 31 days shown</span>` : ""}</div>`;
}
function hbars(rows, opts) {   // rows: [label, sub, value, tipHtml, valueText]
  const max = opts.max || Math.max(1, ...rows.map(r => r[2]));
  return `<div class="hb">${rows.map(r => `<div class="hb-row" ${ct(r[3])}><span class="hb-l">${esc(r[0])}${r[1] ? `<small class="muted">${esc(r[1])}</small>` : ""}</span>
    <span class="hb-t">${opts.ref ? `<i class="hb-ref" style="left:${opts.ref / max * 100}%"></i>` : ""}<i class="hb-b" style="width:${Math.min(100, r[2] / max * 100)}%;background:${opts.color}"></i></span><b class="small">${r[4]}</b></div>`).join("") || `<p class="muted small">Nothing to show.</p>`}</div>`;
}
function chartUtil(act) {
  const rows = act.slice().sort((a, b) => b.utilisation - a.utilisation).map(p => [p.name, p.dept, p.utilisation,
    `<b>${esc(p.name)}</b><br>Worked ${hTxt(p.worked)} of ${hTxt(p.available)} available<br>${p.active_days} day${p.active_days === 1 ? "" : "s"} · ${p.finished} task${p.finished === 1 ? "" : "s"} finished`, Math.round(p.utilisation * 100) + "%"]);
  return hbars(rows, { max: Math.max(1, ...rows.map(r => r[2])), ref: 1, color: PAL[0] }) + `<div class="clegend"><span><i class="hb-ref sm"></i>100% of working hours</span></div>`;
}
function chartIdle(act) {
  const rows = act.filter(p => p.idle).sort((a, b) => b.idle - a.idle).map(p => { const g = p.longest_gap;
    return [p.name, g ? `longest ${hTxt(g.secs)} on ${new Date(g.day + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${ampm(g.from)}–${ampm(g.to)}` : "", p.idle,
      `<b>${esc(p.name)}</b><br>${hTxt(p.idle)} idle across ${p.active_days} day${p.active_days === 1 ? "" : "s"}${g ? `<br>Longest: ${ampm(g.from)}–${ampm(g.to)} on ${esc(g.day)}` : ""}`, hTxt(p.idle)]; });
  return rows.length ? hbars(rows, { color: PAL[1] }) : `<p class="muted small">No idle gaps of 15 minutes or more.</p>`;
}
function chartGap(gaps) {
  if (!gaps.length) return `<p class="muted small">No finished tasks in this period yet.</p>`;
  const list = gaps.slice(0, 14), max = Math.max(...list.map(g => Math.max(g.avg_h, g.limit_h))) * 1.08 || 1;
  const W = 1120, rowH = 32, L = 270, R = 20, H = list.length * rowH + 34, x = (h) => L + h / max * (W - L - R);
  const step = max > 20 ? 5 : max > 8 ? 2 : max > 3 ? 1 : 0.5; let g = "";
  for (let h = 0; h <= max; h += step) g += `<line x1="${x(h)}" x2="${x(h)}" y1="6" y2="${H - 24}" class="grid"/><text x="${x(h)}" y="${H - 8}" class="ax" text-anchor="middle">${h} h</text>`;
  const VC = { over: PAL[7], generous: PAL[3], ok: PAL[0] }, VL = { over: "Over the limit", generous: "Limit too generous", ok: "About right" };
  const rows = list.map((r, i) => { const cy = 18 + i * rowH, a = x(r.avg_h), l = x(r.limit_h);
    const tip = `<b>${esc(r.task)}</b> · ${esc(r.dept)}<br>Average ${r.avg_h} h vs limit ${r.limit_h} h${r.ratio ? ` (${r.ratio}×)` : ""}<br>Median ${r.median_h} h · ${r.count} done<br><b>${VL[r.verdict]}</b>${r.verdict !== "ok" ? ` · suggest ${r.suggest_h} h` : ""}`;
    return `<g class="hit" ${ct(tip)}><rect x="0" y="${cy - rowH / 2}" width="${W}" height="${rowH}" fill="transparent"/>
      <text x="${L - 12}" y="${cy + 4}" class="lb" text-anchor="end">${esc(r.task.length > 34 ? r.task.slice(0, 33) + "…" : r.task)}</text>
      <line x1="${Math.min(a, l)}" x2="${Math.max(a, l)}" y1="${cy}" y2="${cy}" stroke="${VC[r.verdict]}" stroke-width="2" stroke-linecap="round" opacity=".55"/>
      <circle cx="${l}" cy="${cy}" r="6" fill="var(--card)" stroke="#8e8e93" stroke-width="2"/><circle cx="${a}" cy="${cy}" r="6" fill="${VC[r.verdict]}" stroke="var(--card)" stroke-width="2"/></g>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Actual time against time limit">${g}${rows}</svg>
    <div class="clegend"><span><i class="sw" style="background:${PAL[0]};border-radius:50%"></i>About right</span><span><i class="sw" style="background:${PAL[7]};border-radius:50%"></i>Over the limit</span><span><i class="sw" style="background:${PAL[3]};border-radius:50%"></i>Limit too generous</span><span><i class="sw ring"></i>Time limit</span>${gaps.length > 14 ? `<span class="muted">· top 14 of ${gaps.length}</span>` : ""}</div>`;
}
function gapTable(gaps) {
  if (!gaps.length) return `<p class="muted small">Suggestions appear once tasks are finished in the period.</p>`;
  const lab = { over: `<span class="pill p-late">▲ Over the limit</span>`, generous: `<span class="pill p-assigned">▼ Limit too generous</span>`, ok: `<span class="pill p-approved">✓ About right</span>` };
  const why = (g) => g.verdict === "over" ? `Takes ${g.ratio}× the limit. Raise the limit to ${g.suggest_h} h, split the task, or check why it's slow${g.rework ? ` (${g.rework} sent back)` : ""}.`
    : g.verdict === "generous" ? `Done in ${Math.round(g.ratio * 100)}% of the limit. ${g.suggest_h} h would be enough, so the time can go to other work.` : "No change needed.";
  const rows = gaps.slice().sort((a, b) => (a.verdict === "ok") - (b.verdict === "ok") || (b.ratio || 0) - (a.ratio || 0));
  return `<div class="scroll"><table class="gt"><thead><tr><th style="text-align:left">Task</th><th>Done</th><th>Average</th><th>Limit</th><th>Suggested</th><th style="text-align:left">Verdict</th><th style="text-align:left">What to do</th></tr></thead><tbody>
    ${rows.map(g => `<tr><td style="text-align:left"><b>${esc(g.task)}</b><div class="muted small">${esc(g.dept)}</div></td><td>${g.count}</td><td>${g.avg_h} h</td><td>${g.limit_h} h</td><td><b>${g.verdict === "ok" ? "–" : g.suggest_h + " h"}</b></td><td style="text-align:left">${lab[g.verdict]}</td><td style="text-align:left;white-space:normal" class="small">${why(g)}</td></tr>`).join("")}</tbody></table></div>`;
}
function chartDept(D, ppl) {
  const col = deptColors(), m = {}; ppl.forEach(p => { m[p.dept] = (m[p.dept] || 0) + p.worked; });
  const tot = Object.values(m).reduce((a, b) => a + b, 0) || 1;
  const rows = Object.entries(m).filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
  return `<div class="hb">${rows.map(([d, v]) => `<div class="hb-row" ${ct(`<b>${esc(d)}</b><br>${hTxt(v)} · ${Math.round(v / tot * 100)}% of the hours<br>${ppl.filter(p => p.dept === d && p.worked).length} people active`)}><span class="hb-l">${esc(d)}</span><span class="hb-t"><i class="hb-b" style="width:${v / rows[0][1] * 100}%;background:${col[d]}"></i></span><b class="small">${Math.round(v / tot * 100)}%</b></div>`).join("")}</div>`;
}
function chartTop(gaps) {
  const rows = gaps.slice().sort((a, b) => b.total_h - a.total_h).slice(0, 8).map(g => [g.task, g.dept, g.total_h, `<b>${esc(g.task)}</b><br>${g.total_h} h in total · ${g.count} done · avg ${g.avg_h} h`, g.total_h + " h"]);
  return hbars(rows, { color: PAL[6] });
}
function dashCsv() {
  const D = S.dash; if (!D) return;
  const rows = [["Person", "Department", ...D.days, "Total hours", "Available hours", "Time used %", "Idle hours", "Tasks finished"]];
  D.people.filter(p => p.worked).forEach(p => rows.push([p.name, p.dept, ...D.days.map(d => hrs(p.days[d] || 0)), hrs(p.worked), hrs(p.available), Math.round(p.utilisation * 100), hrs(p.idle), p.finished]));
  rows.push([]); rows.push(["Task", "Department", "Done", "Average h", "Median h", "Limit h", "Ratio", "Verdict", "Suggested h", "Late", "Sent back"]);
  D.gaps.forEach(g => rows.push([g.task, g.dept, g.count, g.avg_h, g.median_h, g.limit_h, g.ratio || "", g.verdict, g.suggest_h, g.late, g.rework]));
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" }));
  a.download = `Dashboard_${D.from}_to_${D.to}.csv`; document.body.appendChild(a); a.click(); a.remove();
}
function wireDash() {
  const app = $("#app"), reload = async () => { try { S.dash = await api(dashUrl()); } catch (e) { note("Couldn't load", e.message); } render(); };
  app.querySelectorAll("[data-dp]").forEach(b => b.onclick = () => { S.dp = b.dataset.dp; if (S.dp === "custom" && S.dash) { S.dFrom = S.dFrom || S.dash.from; S.dTo = S.dTo || S.dash.to; } reload(); });
  const f = $("#dFrom"), t = $("#dTo"); if (f) f.onchange = () => { S.dFrom = f.value; reload(); }; if (t) t.onchange = () => { S.dTo = t.value; reload(); };
  $("#dDept").onchange = (e) => { S.dDept = e.target.value; S.dPerson = ""; render(); };
  $("#dPerson").onchange = (e) => { S.dPerson = e.target.value; render(); };
  $("#dCsv").onclick = dashCsv;
  $("#dPrint").onclick = () => { hideTip(); const ct = $("#chTip"); if (ct) ct.classList.remove("show"); window.print(); };
}
// one tooltip for every chart: any element with data-ct
function chartTip(e) {
  const el = e.target.closest && e.target.closest("[data-ct]"); let tip = $("#chTip");
  if (!el) { if (tip) tip.classList.remove("show"); return; }
  if (!tip) { tip = document.createElement("div"); tip.id = "chTip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
  if (tip.dataset.src !== el.dataset.ct) { tip.innerHTML = el.dataset.ct; tip.dataset.src = el.dataset.ct; }
  tip.classList.add("show"); const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, e.clientX + 14)) + "px";
  tip.style.top = (e.clientY - h - 12 > 8 ? e.clientY - h - 12 : e.clientY + 18) + "px";
}
document.addEventListener("mousemove", chartTip);
