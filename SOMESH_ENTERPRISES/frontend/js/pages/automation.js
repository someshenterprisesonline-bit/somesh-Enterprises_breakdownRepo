// Page: Automation (workflow model, rules, history, settings).
"use strict";
// ---------------------------------------------------------- admin: automation
// Data: S.autoCfg (settings), S.rules (GET /api/rules: rules + editor lists), S.wm (GET /api/workflow-model),
// S.rlog (GET /api/rules/log). View: S.autoView = "model" | "rules" | "history" | "settings". Builder draft: S.rb.
async function loadAuto() {
  const errors = [];
  const get = (u) => api(u).catch(e => { errors.push(e.message); return null; });
  const [cfg, rules, wm, lg] = await Promise.all([get("/api/automation"), get("/api/rules"), get(`/api/workflow-model?demo=${S.autoDemo === false ? 0 : 1}`), get("/api/rules/log?limit=500")]);
  if (cfg) S.autoCfg = cfg; if (rules) S.rules = rules; if (wm) S.wm = wm; if (lg) S.rlog = lg.runs || [];
  S.autoError = errors.join(" ? ");
}
const AUTO_VIEWS = [["model", "Workflow model"], ["rules", "Rules"], ["history", "History"], ["settings", "Settings"]];
function viewAuto() {
  const d = S.autoCfg; if (!d) return hero("Automation", "") + skeleton("table", 4);
  const v = S.autoView || "model";
  const seg = `<div class="toolbar au-seg"><div class="seg" role="tablist" aria-label="Automation views">${AUTO_VIEWS.map(([k, l]) => `<button type="button" role="tab" data-av="${k}" aria-selected="${v === k}">${l}</button>`).join("")}</div></div>`;
  const body = v === "rules" ? auRulesHtml() : v === "history" ? auHistoryHtml() : v === "settings" ? auSettingsHtml(d) : auModelHtml();
  return hero("Automation", "See how work flows, and make rules that move it along on their own.") + seg + (S.autoError ? `<div class="au-err" role="alert">Could not refresh: ${esc(S.autoError)} <button class="btn" id="auRetry">Retry</button></div>` : "") + body;
}
async function auRefresh() { await loadAuto(); render(); }
function wireAuto() {
  app.querySelectorAll("[data-av]").forEach(b => b.onclick = () => { S.autoView = b.dataset.av; render(); });
  const retry = $("#auRetry"); if (retry) retry.onclick = auRefresh;
  const demo = $("#auDemoCounts"); if (demo) demo.onchange = async () => { S.autoDemo = demo.checked; await auRefresh(); };
  // workflow model
  app.querySelectorAll("[data-stage]").forEach(g => {
    g.onclick = () => auStagePanel(g.dataset.stage);
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); auStagePanel(g.dataset.stage); } };
  });
  const br = $("#auBillRules"); if (br) br.onclick = () => { S.autoView = "rules"; render(); };
  // rules
  const nr = $("#auNew"); if (nr) nr.onclick = () => rbOpen();
  app.querySelectorAll("[data-tpl-rule]").forEach(b => b.onclick = () => rbOpen(null, RULE_TEMPLATES[Number(b.dataset.tplRule)].make()));
  app.querySelectorAll("[data-rtog]").forEach(c => c.onchange = async () => { try { await api(`/api/rules/${c.dataset.rtog}/toggle`, { enabled: c.checked }); await auRefresh(); } catch (e) { c.checked = !c.checked; note("Couldn't switch the rule", e.message); } });
  app.querySelectorAll("[data-redit]").forEach(b => b.onclick = () => rbOpen(auRule(Number(b.dataset.redit))));
  app.querySelectorAll("[data-rtest]").forEach(b => b.onclick = () => auTestPanel(Number(b.dataset.rtest)));
  app.querySelectorAll("[data-rdel]").forEach(b => b.onclick = () => auDelete(Number(b.dataset.rdel)));
  // history
  const hf = $("#auHistRule"); if (hf) hf.onchange = () => { S.histRule = hf.value; render(); };
  app.querySelectorAll("[data-otask]").forEach(b => b.onclick = () => openTask(Number(b.dataset.otask)));
  app.querySelectorAll(".au-run [data-bill]").forEach(b => b.onclick = () => loadBill(b.dataset.bill));
  // settings (unchanged from the old page)
  const sv = $("#aSave"); if (sv) sv.onclick = async () => {
    const settings = { auto_start: $("#aStart").checked, escalate_to_admins: $("#aEsc").checked, remind_every_hours: Number($("#aRem").value), monthly_open_day: Number($("#aDay").value), monthly_open_hour: Number($("#aHour").value) };
    try { await api("/api/automation", { settings }); S.autoCfg = await api("/api/automation"); render(); note("Automation saved", "The new settings are live.", "approved"); } catch (e) { note("Couldn't save", e.message); }
  };
  const on = $("#aOpenNow"); if (on) on.onclick = async () => { try { const r = await api("/api/automation/open-now", {}); note("Bills opened", r.bills.length ? r.bills.join(", ") : "Every active contract already has a bill this month.", "approved"); load(); } catch (e) { note("Couldn't open bills", e.message); } };
}

// ---------------------------------------------------------- rule wording
const auMeta = () => S.rules || { rules: [], triggers: [], actions: [], conditions: [], placeholders: [], people: [], departments: [], stages: [], templates: [] };
const auRule = (id) => auMeta().rules.find(r => r.id === id);
const auTrig = (id) => auMeta().triggers.find(t => t.id === id);
const lc1 = (s) => s ? s[0].toLowerCase() + s.slice(1) : "";
function auTarget(to) {
  to = String(to || "");
  if (to === "admins") return "admins"; if (to === "assignee") return "the person doing it"; if (to === "approver") return "the checker";
  const m = to.match(/^(department|dept|person):(.*)$/); if (!m) return to || "…";
  return m[1] === "person" ? m[2] : `the ${m[2]} team`;
}
function auWhenText(trigger, when) {
  const t = auTrig(trigger), w = when || {};
  if (trigger === "task_overdue") return Number(w.minutes) ? `When a task is overdue by ${Number(w.minutes)} min` : "When a task is overdue";
  if (trigger === "task_not_started") return `When a task is not started after ${w.hours ?? 1} h`;
  if (trigger === "daily_at") return `Every day at ${w.at || "09:00"}`;
  return t ? "When " + lc1(t.label) : "When …";
}
function auCondText(id, v) {
  switch (id) {
    case "dept": return `department is ${v}`; case "person": return `person is ${v}`; case "stage": return `stage code is ${v}`;
    case "task_contains": return `task name contains “${v}”`; case "client_contains": return `client contains “${v}”`;
    case "rework_min": return `sent back at least ${v} times`; case "include_demo": return "including demo data";
    default: return `${id} is ${v}`;
  }
}
function auActText(a) {
  switch (a.type) {
    case "alert": return `alert ${auTarget(a.to)}`; case "reassign_least_busy": return "move to least busy"; case "reassign_to": return `move to ${a.person || "…"}`;
    case "escalate_admins": return "escalate to admins"; case "give_template": return `give “${a.template || "…"}” to ${auTarget(a.to)}`;
    case "extend_limit": return `extend the limit by ${a.hours || "…"} h`; case "start_automatically": return "start it for the least busy owner";
    default: return a.type;
  }
}
function auSentence(r) {
  const conds = Object.entries(r.conditions || {}).map(([k, v]) => auCondText(k, v));
  const acts = (r.actions || []).map(auActText);
  return esc(auWhenText(r.trigger, r.when)) + (conds.length ? ` · <span class="au-if">if</span> ${esc(conds.join(" and "))}` : "") + ` · <span class="au-then">then</span> ${esc(acts.join(", ") || "…")}`;
}
function auStats() {
  const s = {}; (S.rlog || []).forEach(x => { if (x.result !== "fired") return; const o = s[x.rule_id] = s[x.rule_id] || { n: 0, last: null }; o.n++; if (!o.last || x.ts > o.last) o.last = x.ts; });
  return s;
}

// ---------------------------------------------------------- 1. workflow model
function auDeptColor(dept) {
  const departments = [...new Set([...(auMeta().departments || []), ...((S.wm || {}).stages || []).map(s => s.dept)])];
  const palette = ["#6253c9", "#0076d6", "#008277", "#a45813", "#b83c78", "#3e782b", "#826225"];
  return palette[Math.max(0, departments.indexOf(dept)) % palette.length];
}
const WM = { W: 280, H: 128, GX: 78, GY: 26, BAND: 70, PAD: 50, TOP: 24 };
function auLayout(stages, start) {
  const by = Object.fromEntries(stages.map(s => [s.code, s]));
  const out = (s) => [...new Set([...(s.next || []), ...Object.values((s.branch || {}).options || {}).flat()])].filter(c => by[c]);
  const lvl = Object.fromEntries(stages.map(s => [s.code, 0]));
  for (let i = 0; i < stages.length; i++) { let ch = false; stages.forEach(s => out(s).forEach(c => { if (lvl[c] < lvl[s.code] + 1) { lvl[c] = lvl[s.code] + 1; ch = true; } })); if (!ch) break; }
  if (by[start]) lvl[start] = 0;
  const nLvl = Math.max(0, ...Object.values(lvl)) + 1;
  const avail = Math.min(window.innerWidth, 1240) - 60;
  const per = window.innerWidth < 700 ? 3 : Math.max(2, Math.min(nLvl, Math.floor((avail - WM.PAD) / (WM.W + WM.GX))));
  const cols = Array.from({ length: nLvl }, (_, i) => stages.filter(s => lvl[s.code] === i));
  const bands = []; for (let i = 0; i < nLvl; i += per) bands.push(cols.slice(i, i + per));
  const pos = {}; let y = WM.TOP;
  bands.forEach((b, bi) => {
    const tall = Math.max(1, ...b.map(c => c.length)), bh = tall * WM.H + (tall - 1) * WM.GY;
    b.forEach((col, ci) => { const ch = col.length * WM.H + (col.length - 1) * WM.GY, y0 = y + (bh - ch) / 2;
      col.forEach((s, k) => { pos[s.code] = { x: WM.PAD + ci * (WM.W + WM.GX), y: y0 + k * (WM.H + WM.GY), band: bi, bottom: y + bh }; }); });
    y += bh + WM.BAND;
  });
  const width = WM.PAD + Math.min(per, nLvl) * (WM.W + WM.GX) + 6, height = y - WM.BAND / 2 + 8;
  return { pos, out, width, height };
}
function auPoly(pts, r = 8) { // a path through the points with rounded corners
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1], [x, y] = pts[i], [nx, ny] = pts[i + 1];
    const l1 = Math.hypot(x - px, y - py), l2 = Math.hypot(nx - x, ny - y), k = Math.min(r, l1 / 2, l2 / 2);
    if (!l1 || !l2) continue;
    d += ` L${x - (x - px) / l1 * k},${y - (y - py) / l1 * k} Q${x},${y} ${x + (nx - x) / l2 * k},${y + (ny - y) / l2 * k}`;
  }
  const e = pts[pts.length - 1]; return d + ` L${e[0]},${e[1]}`;
}
function auEdge(a, b, label) {
  const { W, H, GX } = WM; let d, lx, ly;
  if (a.band === b.band && b.x > a.x && b.x - a.x <= W + GX) { // next column: a smooth curve
    const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x - 4, y2 = b.y + H / 2;
    d = `M${x1},${y1} C${x1 + 36},${y1} ${x2 - 36},${y2} ${x2},${y2}`; lx = (x1 + x2) / 2; ly = (y1 + y2) / 2;
  } else { // skips a column or goes to a later row: out to the right, along the gap under the row, then in from the left
    const x1 = a.x + W, y1 = a.y + H / 2, cx = x1 + GX / 2, cy = a.bottom + WM.BAND / 2, ex = b.x - 22, y2 = b.y + H / 2;
    d = auPoly([[x1, y1], [cx, y1], [cx, cy], [ex, cy], [ex, y2], [b.x - 4, y2]]);
    lx = ex; ly = y2 - 16;
  }
  const lab = label ? `<g class="wm-lab"><rect x="${lx - 17}" y="${ly - 10}" width="34" height="20" rx="10"/><text x="${lx}" y="${ly + 4}" text-anchor="middle">${esc(label)}</text></g>` : "";
  return `<path class="wm-edge${label ? " br" : ""}" d="${d}" marker-end="url(#wmArr)"/>${lab}`;
}
const cut = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
function auCard(s, p, isStart, isEnd) {
  const { W, H } = WM, c = s.counts || {}, col = auDeptColor(s.dept || "");
  const chips = [[`${c.open || 0} open`, c.open ? "open" : "idle"], c.overdue ? [`${c.overdue} overdue`, "late"] : null, c.waiting_check ? [`${c.waiting_check} to check`, "check"] : null].filter(Boolean);
  let cx = 14; const chipSvg = chips.map(([t, k]) => { const w = t.length * 6.4 + 16, g = `<g class="wm-chip ${k}"><rect x="${cx}" y="${H - 28}" width="${w}" height="18" rx="9"/><text x="${cx + w / 2}" y="${H - 15}" text-anchor="middle">${t}</text></g>`; cx += w + 5; return g; }).join("");
  const av = (s.owners || []).slice(0, 4).map((o, i) => `<g><title>${esc(o)}</title><circle cx="${25 + i * 18}" cy="${H - 50}" r="11" fill="${colorOf(o)}" class="wm-av"/><text x="${25 + i * 18}" y="${H - 46.5}" text-anchor="middle" class="wm-avt">${esc(initials(o))}</text></g>`).join("") + ((s.owners || []).length > 4 ? `<text x="${25 + 4 * 18}" y="${H - 46}" class="wm-sm">+${s.owners.length - 4}</text>` : "");
  const rules = s.rules || [], onN = rules.filter(r => r.enabled).length;
  const badge = rules.length ? `<g class="wm-bolt${onN ? "" : " off"}"><title>Rules for this stage:\n${rules.map(r => "• " + r.name + (r.enabled ? "" : " (off)")).join("\n")}</title><rect x="${W - 46}" y="8" width="38" height="20" rx="10"/><text x="${W - 27}" y="22" text-anchor="middle">⚡${rules.length}</text></g>` : "";
  const tag = isStart ? `<text x="4" y="-7" class="wm-tag">▶ START</text>` : isEnd ? `<text x="4" y="-7" class="wm-tag">■ END</text>` : "";
  const lbl = `${s.code} ${s.name}, ${s.dept}. ${c.open || 0} open, ${c.overdue || 0} overdue, ${c.waiting_check || 0} to check. ${rules.length} rules.`;
  return `<g class="wm-st" data-stage="${esc(s.code)}" transform="translate(${p.x},${p.y})" tabindex="0" role="button" aria-label="${esc(lbl)}">${tag}
    <rect class="wm-card" width="${W}" height="${H}" rx="14"/><rect width="6" height="${H}" rx="3" fill="${col}"/>
    <text x="16" y="24" class="wm-code">${esc(s.code)}</text><text x="16" y="42" class="wm-name">${esc(cut(s.name, 34))}</text>
    <text x="16" y="58" class="wm-dept" fill="${col}">${esc(cut(s.dept, 38))}</text>${av}
    <text x="${W - 12}" y="${H - 46}" text-anchor="end" class="wm-sm">⏱ ${esc(s.sla_hours)} h</text>${chipSvg}${badge}</g>`;
}
function auModelHtml() {
  const m = S.wm; if (!m) return skeleton("table", 5);
  const L = auLayout(m.stages, m.start_stage), by = Object.fromEntries(m.stages.map(s => [s.code, s]));
  const edges = m.stages.map(s => {
    const opt = (s.branch || {}).options || {}, lab = {};
    Object.entries(opt).forEach(([k, v]) => (v.length ? v : s.next || []).forEach(c => { lab[c] = lab[c] ? lab[c] + "/" + k : k; }));
    return L.out(s).map(c => auEdge(L.pos[s.code], L.pos[c], lab[c])).join("");
  }).join("");
  const cards = m.stages.map(s => auCard(s, L.pos[s.code], s.code === m.start_stage, (m.final_stages || []).includes(s.code))).join("");
  const svg = `<svg class="wm" width="${L.width}" height="${L.height}" viewBox="0 0 ${L.width} ${L.height}" role="group" aria-label="Workflow model: stages from left to right">
    <defs><marker id="wmArr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="wm-arrhead"/></marker></defs>${edges}${cards}</svg>`;
  const depts = [...new Set(m.stages.map(s => s.dept))];
  const tot = m.stages.reduce((a, s) => { const c = s.counts || {}; a.o += c.open || 0; a.l += c.overdue || 0; a.c += c.waiting_check || 0; return a; }, { o: 0, l: 0, c: 0 });
  const legend = `<div class="au-legend"><div class="au-lg-row">${depts.map(d => `<span><i style="background:${auDeptColor(d)}"></i>${esc(d)}</span>`).join("")}</div>
    <div class="au-lg-row"><span class="au-chip open">open</span> tasks in the stage <span class="au-chip late">overdue</span> past the time limit <span class="au-chip check">to check</span> waiting for the checker
      <span class="au-chip bolt">⚡</span> rules (hover to see, click the stage to change) <span class="au-dash"></span> decision branch</div></div>`;
  const bills = (m.bill_rules || []).length ? `<button type="button" class="au-chip bolt" id="auBillRules" style="border:0">⚡${m.bill_rules.length} bill rules</button>` : "";
  return `<div class="au-sum"><span><b>${tot.o}</b> open</span><span class="late"><b>${tot.l}</b> overdue</span><span class="check"><b>${tot.c}</b> to check</span>${bills}<span class="muted small" style="margin-left:auto">Live · updates every 30 s · click a stage for details</span></div>
    <label class="au-demo"><input id="auDemoCounts" type="checkbox" ${S.autoDemo !== false ? "checked" : ""}> Include demo bills in counts</label><div class="panel au-model"><div class="wm-scroll" tabindex="0" aria-label="Workflow model, scroll sideways">${svg}</div></div>${legend}`;
}
function auStagePanel(code) {
  const s = ((S.wm || {}).stages || []).find(x => x.code === code); if (!s) return;
  const c = s.counts || {}, rules = s.rules || [], col = auDeptColor(s.dept || ""), names = Object.fromEntries((S.wm.stages || []).map(x => [x.code, x.name]));
  const st = auStats();
  const rl = rules.length ? rules.map(r => { const full = auRule(r.id) || r; return `<div class="au-mini"><div><b>${esc(r.name)}</b> <span class="pill ${r.enabled ? "p-approved" : ""}">${r.enabled ? "On" : "Off"}</span>
    <div class="small muted">${full.actions ? auSentence(full) : ""}${st[r.id] ? ` · fired ${st[r.id].n}×` : ""}</div></div><button class="btn" type="button" data-sredit="${r.id}">Edit</button></div>`; }).join("") : `<p class="muted small">No rules apply to this stage yet.</p>`;
  const br = s.branch ? `<div class="box" style="margin-top:10px"><b>Decision: ${esc(s.branch.question)}</b>${Object.entries(s.branch.options || {}).map(([k, v]) => `${esc(k)} → ${v.length ? v.map(x => esc(x + " " + (names[x] || ""))).join(", ") : "carry on as normal"}`).join("<br>")}</div>` : "";
  sheetHtml(`<div class="au-sh-head" style="border-left:6px solid ${col}"><div class="code">${esc(s.code)}</div><h2 style="margin:2px 0">${esc(s.name)}</h2><div style="color:${col};font-weight:600">${esc(s.dept)}</div></div>
    <div class="au-sum" style="margin:14px 0"><span><b>${c.open || 0}</b> open</span><span class="late"><b>${c.overdue || 0}</b> overdue</span><span class="check"><b>${c.waiting_check || 0}</b> to check</span></div>
    <div class="facts"><span class="muted">Done by</span><span>${(s.owners || []).map(o => `${avatar(o)} ${esc(o)}`).join("<br>")}</span>
      <span class="muted">Checked by</span><span>${s.validator ? avatar(s.validator) + " " + esc(s.validator) : "—"}</span>
      <span class="muted">Time limit</span><span>${esc(s.sla_hours)} hours</span>
      <span class="muted">Next</span><span>${(s.next || []).length ? s.next.map(x => esc(x + " " + (names[x] || ""))).join("<br>") : "End of the flow"}</span></div>${br}
    <h3 style="margin:22px 0 8px">⚡ Rules for this stage (${rules.length})</h3>${rl}
    <button class="btn primary" type="button" id="auStageAdd" style="margin-top:14px">＋ Add rule for this stage</button>`);
  $("#auStageAdd").onclick = () => rbOpen(null, { name: "", trigger: "task_overdue", wv: "60", conds: [{ f: "stage", v: code }], acts: [{ type: "alert", to: "admins", message: "{task} for {bill} is past its time limit. With: {person}." }] });
  $("#sheet").querySelectorAll("[data-sredit]").forEach(b => b.onclick = () => rbOpen(auRule(Number(b.dataset.sredit))));
}

// ---------------------------------------------------------- 2. rules
const RULE_TEMPLATES = [
  { icon: "⏰", title: "Escalate overdue", text: "When a task is 2 h past its limit, alert the admins.", make: () => ({ name: "Escalate overdue work after 2 h", trigger: "task_overdue", wv: "120", conds: [], acts: [{ type: "alert", to: "admins", message: "{task} for {bill} ({client}) is {minutes} min past its time limit. With: {person}." }, { type: "escalate_admins" }] }) },
  { icon: "▶️", title: "Auto-start idle tasks", text: "When a task isn't started after 1 h, start it for the least busy owner.", make: () => ({ name: "Start idle tasks after 1 h", trigger: "task_not_started", wv: "1", conds: [], acts: [{ type: "start_automatically" }] }) },
  { icon: "📦", title: "Courier after bill complete", text: "When a bill is complete, give “Courier dispatch” to Operations.", make: () => ({ name: "Courier after bill complete", trigger: "bill_completed", wv: "", conds: [], acts: [{ type: "give_template", template: "Courier dispatch", to: "dept:Operations" }] }) },
];
function auRulesHtml() {
  if (!S.rules) return skeleton("table", 4);
  const st = auStats(), rules = auMeta().rules;
  const tpl = `<div class="au-tpls">${RULE_TEMPLATES.map((t, i) => `<button type="button" class="au-tpl" data-tpl-rule="${i}"><span class="au-tpl-i">${t.icon}</span><b>${esc(t.title)}</b><span class="muted small">${esc(t.text)}</span><span class="au-tpl-go">Use template →</span></button>`).join("")}</div>`;
  const cards = rules.length ? rules.map(r => { const s = st[r.id]; return `<div class="au-rule${r.enabled ? " on" : ""}">
      <div class="au-rule-top"><b>${esc(r.name)}</b><label class="au-sw" title="${r.enabled ? "On: click to switch off" : "Off: click to switch on"}"><input type="checkbox" data-rtog="${r.id}" ${r.enabled ? "checked" : ""} aria-label="Rule ${esc(r.name)} on"><span></span></label></div>
      <p class="au-sent">${auSentence(r)}</p>
      <div class="au-rule-foot"><span class="muted small">${s ? `Last fired ${esc(fmt(s.last))} · fired ${s.n}×` : "No firings in recent history"}</span><span style="flex:1"></span>
        <button class="btn" type="button" data-redit="${r.id}">Edit</button><button class="btn" type="button" data-rtest="${r.id}">Test</button><button class="btn au-del" type="button" data-rdel="${r.id}">Delete</button></div></div>`; }).join("") : `<p class="empty">No rules yet. Start from a template or make a new one.</p>`;
  return `<div class="row2" style="margin-bottom:12px"><h3 style="margin:0">Start from a template</h3><span style="flex:1"></span><button class="btn primary" id="auNew" type="button">＋ New rule</button></div>${tpl}
    <h3 style="margin:24px 0 12px">Your rules (${rules.length})</h3><div class="au-rules">${cards}</div>`;
}
function auDelete(id) {
  const r = auRule(id); if (!r) return;
  dialog(`<h3 style="margin:0">Delete this rule?</h3><p class="muted">“${esc(r.name)}” will stop working and be removed. Its firing history will also be removed.</p>`, async () => {
    try { await api(`/api/rules/${id}/delete`, {}); note("Rule deleted", r.name, "approved"); await auRefresh(); } catch (e) { note("Couldn't delete", e.message); }
  });
}
const auTestHtml = (t) => t.error ? `<div class="au-err">${esc(t.error)}</div>` : `<div class="au-test"><b>Would have fired ${t.would_fire} time${t.would_fire === 1 ? "" : "s"}</b> in the last ${t.days || 7} days.
  ${(t.examples || []).length ? `<ul>${t.examples.slice(0, 6).map(x => `<li><span class="muted small">${esc(fmt(x.ts))}</span> ${esc(x.text || x.task)}</li>`).join("")}</ul>` : ""}<div class="muted small">${esc(t.note || "")}</div></div>`;
async function auTestPanel(id) {
  const r = auRule(id); if (!r) return;
  sheetHtml(`<h2 style="margin:0 0 6px">Test: ${esc(r.name)}</h2><p class="au-sent">${auSentence(r)}</p>${skeleton("table", 3)}`);
  let t; try { t = await api(`/api/rules/${id}/test`, {}); } catch (e) { t = { error: e.message }; }
  sheetHtml(`<h2 style="margin:0 0 6px">Test: ${esc(r.name)}</h2><p class="au-sent">${auSentence(r)}</p>${auTestHtml(t)}<button class="btn" type="button" id="auTEdit" style="margin-top:14px">Edit this rule</button>`);
  $("#auTEdit").onclick = () => rbOpen(r);
}

// ---------------------------------------------------------- rule builder (side panel)
const AU_MSG = "{task} ({bill}) · {person}, {dept}";
function rbOpen(rule, draft) {
  if (rule) {
    const tv = (auTrig(rule.trigger) || {}).value;
    S.rb = { id: rule.id, name: rule.name, enabled: rule.enabled, trigger: rule.trigger, wv: tv ? String((rule.when || {})[tv.key] ?? tv.default ?? "") : "",
      conds: Object.entries(rule.conditions || {}).filter(([f, v]) => f !== "include_demo" || v).map(([f, v]) => ({ f, v })), acts: (rule.actions || []).map(a => ({ ...a })) };
  } else {
    const d = draft || {}, trig = d.trigger || "task_submitted", tv = (auTrig(trig) || {}).value;
    S.rb = { id: null, name: d.name || "", enabled: false, trigger: trig, wv: d.wv != null && d.wv !== "" ? d.wv : tv ? String(tv.default ?? "") : "", conds: d.conds || [], acts: d.acts && d.acts.length ? d.acts : [{ type: "alert", to: "admins", message: AU_MSG }] };
  }
  S.rb.err = ""; S.rb.test = null; rbDraw();
}
function rbBody() {
  const r = S.rb, tv = (auTrig(r.trigger) || {}).value, conditions = {}, condDef = Object.fromEntries(auMeta().conditions.map(c => [c.id, c]));
  r.conds.forEach(c => { if (!c.f) return; const t = (condDef[c.f] || {}).type; conditions[c.f] = t === "number" ? Number(c.v) : t === "bool" ? true : c.v; });
  const when = {}; if (tv) when[tv.key] = tv.type === "number" ? (r.wv === "" ? NaN : Number(r.wv)) : r.wv;
  const actDef = Object.fromEntries(auMeta().actions.map(a => [a.id, a]));
  const actions = r.acts.map(a => { const o = { type: a.type }; ((actDef[a.type] || {}).params || []).forEach(p => { o[p] = p === "hours" ? Number(a[p]) : (a[p] ?? ""); }); return o; });
  const body = { name: r.name.trim(), enabled: !!r.enabled, trigger: r.trigger, when, conditions, actions };
  if (r.id) body.id = r.id;
  if (!body.name) body.name = cut(auWhenText(r.trigger, when).replace(/^When a/, "A") + " → " + actions.map(auActText).join(", "), 80);
  return body;
}
function rbSel(attr, opts, val, extra) { return `<select class="in" ${attr} ${extra || ""}>${opts.map(o => typeof o === "string" ? `<option value="${esc(o)}" ${o === val ? "selected" : ""}>${esc(o)}</option>` : o.group ? `<optgroup label="${esc(o.group)}">${o.items.map(([v, l]) => `<option value="${esc(v)}" ${v === val ? "selected" : ""}>${esc(l)}</option>`).join("")}</optgroup>` : `<option value="${esc(o[0])}" ${o[0] === val ? "selected" : ""} ${o[2] ? "disabled" : ""}>${esc(o[1])}</option>`).join("")}</select>`; }
function rbHtml() {
  const M = auMeta(), r = S.rb, trig = auTrig(r.trigger) || {}, scope = trig.scope || "task", tv = trig.value;
  const scopes = { task: "Task events", bill: "Bill events", time: "Time" };
  const trigOpts = Object.keys(scopes).map(k => ({ group: scopes[k], items: M.triggers.filter(t => t.scope === k).map(t => [t.id, t.label]) }));
  const whenField = tv ? `<label class="au-fl">${esc(tv.label)}<input class="in" data-rb="wv" type="${tv.type === "time" ? "time" : "number"}" ${tv.type === "number" ? `min="0" step="any"` : ""} value="${esc(r.wv)}"></label>` : "";
  const conds = M.conditions.filter(c => c.scopes.includes(scope)), cDef = Object.fromEntries(M.conditions.map(c => [c.id, c]));
  const valField = (c, i) => { const t = (cDef[c.f] || {}).type, a = `data-cv="${i}" aria-label="Value"`;
    if (t === "dept") return rbSel(a, ["", ...M.departments].map(d => [d, d || "Pick a department"]), c.v);
    if (t === "person") return rbSel(a, [["", "Pick a person"], ...M.people.map(p => [p.name, `${p.name} (${p.dept})`])], c.v);
    if (t === "stage") return rbSel(a, [["", "Pick a stage"], ...M.stages.map(s => [s.code, `${s.code} ${s.name}`])], c.v);
    if (t === "bool") return `<span class="muted small" style="align-self:center">yes</span>`;
    return `<input class="in" ${a} type="${t === "number" ? "number" : "text"}" ${t === "number" ? `min="0"` : ""} value="${esc(c.v ?? "")}" placeholder="${t === "number" ? "N" : "text"}">`; };
  const condRows = r.conds.map((c, i) => `<div class="au-row">${rbSel(`data-cf="${i}" aria-label="Field"`, [["", "Pick a field"], ...conds.map(x => [x.id, x.label, r.conds.some((other, j) => j !== i && other.f === x.id)])], c.f)}${c.f ? valField(c, i) : ""}<button type="button" class="btn au-x" data-cdel="${i}" aria-label="Remove condition">✕</button></div>`).join("");
  const people = M.people.map(p => [p.name, p.name]);
  const alertTo = [["assignee", "The person doing it"], ["approver", "The checker"], ["admins", "Admins"], { group: "Department", items: M.departments.map(d => ["department:" + d, d]) }, { group: "Person", items: M.people.map(p => ["person:" + p.name, p.name]) }];
  const giveTo = [{ group: "Anyone in a department", items: M.departments.map(d => ["dept:" + d, d]) }, { group: "A person", items: M.people.map(p => ["person:" + p.name, p.name]) }];
  const ph = (i) => `<div class="au-ph"><span class="muted small">Insert:</span>${(M.placeholders || []).map(p => `<button type="button" class="au-phc" data-ph="${i}" data-v="{${p}}">{${p}}</button>`).join("")}</div>`;
  const actFields = (a, i) => {
    const f = [], at = (p) => `data-ap="${i}" data-k="${p}"`;
    if (a.type === "alert") f.push(`<label class="au-fl">Send to${rbSel(at("to"), alertTo, a.to || "admins")}</label>`, `<label class="au-fl">Message<textarea class="in" ${at("message")} rows="2" placeholder="For example: {task} from {person} needs a look">${esc(a.message || "")}</textarea></label>${ph(i)}`);
    if (a.type === "reassign_to") f.push(`<label class="au-fl">Person${rbSel(at("person"), [["", "Pick a person"], ...people], a.person || "")}</label>`);
    if (a.type === "give_template") f.push(`<label class="au-fl">Task${rbSel(at("template"), [["", "Pick a task"], ...M.templates.map(t => [t, t])], a.template || "")}</label>`, `<label class="au-fl">Give to${rbSel(at("to"), [["", "Pick who"], ...giveTo], a.to || "")}</label>`);
    if (a.type === "extend_limit") f.push(`<label class="au-fl">Extra hours<input class="in" type="number" min="0" step="any" ${at("hours")} value="${esc(a.hours ?? "")}"></label>`);
    return f.join("");
  };
  const actRows = r.acts.map((a, i) => `<div class="au-act"><div class="au-row"><span class="au-n">${i + 1}</span>${rbSel(`data-at="${i}" aria-label="Action"`, M.actions.map(x => [x.id, x.label + (x.needs_task && scope !== "task" ? " (needs a task)" : ""), x.needs_task && scope !== "task"]), a.type)}<button type="button" class="btn au-x" data-adel="${i}" aria-label="Remove action">✕</button></div>${actFields(a, i)}</div>`).join("");
  const tplRow = r.id ? "" : `<div class="au-tpl-mini"><span class="muted small">Templates:</span>${RULE_TEMPLATES.map((t, i) => `<button type="button" class="au-phc" data-rbtpl="${i}">${t.icon} ${esc(t.title)}</button>`).join("")}</div>`;
  return `<h2 style="margin:0 0 4px">${r.id ? "Edit rule" : "New rule"}</h2>${tplRow}
    <label class="au-fl">Rule name<input class="in" data-rb="name" value="${esc(r.name)}" placeholder="Made from the sentence below if left empty"></label>
    <div class="au-step"><div class="au-step-h"><span class="au-badge w">1</span><b>WHEN</b><span class="muted small">this happens</span></div>
      ${rbSel(`data-rb="trigger" aria-label="Trigger"`, trigOpts, r.trigger)}${whenField}</div>
    <div class="au-arrow" aria-hidden="true">↓</div>
    <div class="au-step"><div class="au-step-h"><span class="au-badge i">2</span><b>IF</b><span class="muted small">all of these are true (optional)</span></div>
      ${condRows || `<p class="muted small" style="margin:4px 0">No conditions: it applies to every ${scope === "bill" ? "bill" : scope === "time" ? "day" : "task"}.</p>`}
      <button type="button" class="btn au-add" id="rbAddC">＋ Add condition</button></div>
    <div class="au-arrow" aria-hidden="true">↓</div>
    <div class="au-step"><div class="au-step-h"><span class="au-badge t">3</span><b>THEN</b><span class="muted small">do these, in order</span></div>
      ${actRows}<button type="button" class="btn au-add" id="rbAddA">＋ Add action</button></div>
    <div class="au-preview"><span class="muted small">This rule says</span><p class="au-sent" id="rbSent">${auSentence(rbBody())}</p></div>
    <label class="switch" style="border:0;padding:6px 0"><input type="checkbox" data-rb="enabled" ${r.enabled ? "checked" : ""}><span><b>Rule is on</b><span class="muted small" style="display:block">Off rules are kept but never fire.</span></span></label>
    <p class="muted small">Demo bills are excluded unless you add the ?Include demo data? condition.</p><div id="rbErr">${r.err ? `<div class="au-err" role="alert">${esc(r.err)}</div>` : ""}</div>
    <div id="rbTest">${r.test ? auTestHtml(r.test) : ""}</div>
    <div class="row2 au-rb-btns"><button class="btn" type="button" id="rbTestBtn">Test on last 7 days</button><span style="flex:1"></span><button class="btn" type="button" id="rbCancel">Cancel</button><button class="btn primary" type="button" id="rbSave">Save rule</button></div>`;
}
function rbDraw() { const sc = $("#sheet").scrollTop; sheetHtml(rbHtml()); $("#sheet").scrollTop = sc; rbWire(); }
function rbPreview() { const el = $("#rbSent"); if (el) el.innerHTML = auSentence(rbBody()); }
function rbWire() {
  const sh = $("#sheet"), r = S.rb, q = (s) => sh.querySelectorAll(s);
  q("[data-rb]").forEach(el => {
    const k = el.dataset.rb;
    el.oninput = el.onchange = () => {
      if (k === "enabled") r.enabled = el.checked; else r[k] = el.value;
      if (k === "trigger") { const tv = (auTrig(r.trigger) || {}).value, sc = (auTrig(r.trigger) || {}).scope; r.wv = tv ? String(tv.default ?? "") : "";
        const ok = new Set(auMeta().conditions.filter(c => c.scopes.includes(sc)).map(c => c.id)); r.conds = r.conds.filter(c => !c.f || ok.has(c.f)); return rbDraw(); }
      rbPreview();
    };
  });
  q("[data-cf]").forEach(el => el.onchange = () => { const c = r.conds[Number(el.dataset.cf)]; c.f = el.value; c.v = ""; rbDraw(); });
  q("[data-cv]").forEach(el => el.oninput = el.onchange = () => { r.conds[Number(el.dataset.cv)].v = el.value; rbPreview(); });
  q("[data-cdel]").forEach(b => b.onclick = () => { r.conds.splice(Number(b.dataset.cdel), 1); rbDraw(); });
  q("[data-at]").forEach(el => el.onchange = () => { const i = Number(el.dataset.at); r.acts[i] = { type: el.value }; if (el.value === "alert") Object.assign(r.acts[i], { to: "admins", message: AU_MSG }); rbDraw(); });
  q("[data-ap]").forEach(el => el.oninput = el.onchange = () => { r.acts[Number(el.dataset.ap)][el.dataset.k] = el.value; rbPreview(); });
  q("[data-adel]").forEach(b => b.onclick = () => { r.acts.splice(Number(b.dataset.adel), 1); rbDraw(); });
  q("[data-ph]").forEach(b => b.onclick = () => {
    const ta = sh.querySelector(`textarea[data-ap="${b.dataset.ph}"]`); if (!ta) return;
    const s = ta.selectionStart ?? ta.value.length, e = ta.selectionEnd ?? s; ta.value = ta.value.slice(0, s) + b.dataset.v + ta.value.slice(e);
    ta.focus(); ta.selectionStart = ta.selectionEnd = s + b.dataset.v.length; ta.dispatchEvent(new Event("input"));
  });
  q("[data-rbtpl]").forEach(b => b.onclick = () => rbOpen(null, RULE_TEMPLATES[Number(b.dataset.rbtpl)].make()));
  $("#rbAddC").onclick = () => { r.conds.push({ f: "", v: "" }); rbDraw(); };
  $("#rbAddA").onclick = () => { r.acts.push({ type: "alert", to: "admins", message: AU_MSG }); rbDraw(); };
  $("#rbCancel").onclick = closeSheet;
  $("#rbSave").onclick = () => rbSave(false);
  $("#rbTestBtn").onclick = () => rbSave(true);
}
async function rbSave(forTest) {
  const r = S.rb, body = rbBody();
  const btn = $(forTest ? "#rbTestBtn" : "#rbSave"); if (btn) btn.disabled = true;
  const active = () => S.rb === r && !!$("#rbSave") && $("#sheet").classList.contains("open");
  let temporaryId;
  try {
    if (forTest) {
      // The API tests saved rules. Use a disabled copy so testing never changes a live rule.
      const draft = { ...body, enabled: false }; delete draft.id;
      temporaryId = (await api("/api/rules", draft)).rule.id;
      r.test = await api(`/api/rules/${temporaryId}/test`, {});
      r.err = "";
    } else {
      const saved = (await api("/api/rules", body)).rule;
      if (active()) { closeSheet(); S.autoView = "rules"; note("Rule saved", `${saved.name} ? ${saved.enabled ? "on" : "off"}`, "approved"); }
    }
  } catch (e) { r.err = e.message; r.test = null; }
  finally {
    if (temporaryId) {
      try { await api(`/api/rules/${temporaryId}/delete`, {}); }
      catch (e) { r.err = `Test finished, but its disabled copy could not be removed: ${e.message}`; }
    }
    if (active()) rbDraw();
    await auRefresh();
  }
}

// ---------------------------------------------------------- 3. history
function auHistoryHtml() {
  if (!S.rlog) return skeleton("table", 5);
  const f = S.histRule || "", names = {}; S.rlog.forEach(x => { names[x.rule_id] = x.rule || `Rule ${x.rule_id}`; }); auMeta().rules.forEach(r => { names[r.id] = r.name; });
  const runs = S.rlog.filter(x => !f || String(x.rule_id) === f).slice(0, 50);
  const sel = `<label class="au-history-filter"><span class="muted small">Rule</span><select class="in" id="auHistRule"><option value="">All rules</option>${Object.entries(names).map(([id, n]) => `<option value="${id}" ${f === id ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`;
  const cards = runs.length ? runs.map(x => `<div class="au-run ${x.result === "fired" ? "ok" : "bad"}">
      <div class="au-run-top"><span class="pill ${x.result === "fired" ? "p-approved" : "p-late"}">${x.result === "fired" ? "Fired" : esc(x.result)}</span><b>${esc(names[x.rule_id] || x.rule)}</b><span class="muted small" style="margin-left:auto">${esc(fmt(x.ts))}</span></div>
      <div class="au-run-links">${x.task_id ? `<button type="button" class="billlink" data-otask="${x.task_id}">Task #${x.task_id}</button>` : ""}${x.bill_id ? `<button type="button" class="billlink" data-bill="${esc(x.bill_id)}">${esc(x.bill_id)}</button>` : ""}</div>
      <div class="small">${esc(x.detail || "")}</div></div>`).join("") : `<p class="empty">No firings yet${f ? " for this rule" : ""}. When a rule that is on does something, it shows here.</p>`;
  return `<div class="toolbar" style="justify-content:space-between;flex-wrap:wrap;gap:8px">${sel}<span class="muted small">Last ${runs.length} firings, newest first</span></div><div class="au-runs">${cards}</div>`;
}

// ---------------------------------------------------------- 4. settings (the old Automation page, unchanged)
function auSettingsHtml(d) {
  const a = d.settings;
  const sw = (id, on, title, text) => `<label class="switch"><input type="checkbox" id="${id}" ${on ? "checked" : ""}><span><b>${title}</b><span class="muted small" style="display:block">${text}</span></span></label>`;
  return `<div class="panel">${sw("aStart", a.auto_start, "Start tasks automatically", "A new task is started straight away for the person in its team with the fewest tasks in progress, so nobody has to press Start. They get the alert “started for you”.")}
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
