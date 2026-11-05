// Optional page: Workflow input (load the process from Excel / Google Sheet).
"use strict";
// ---------------------------------------------------------- workflow input (admins)
function resultHtml(r) {
  if (!r) return "";
  if (r.error) return `<div class="msg err"><b>Couldn't read it.</b> ${esc(r.error)}</div>`;
  const s = r.summary || {};
  const chips = (list, cls) => list.map(x => `<span class="chip ${cls}">${esc(x)}</span>`).join("");
  const changes = [s.added_stages.length ? `<div><b>New stages</b> <span class="chips">${chips(s.added_stages, "add")}</span></div>` : "",
    s.removed_stages.length ? `<div><b>Removed stages</b> <span class="chips">${chips(s.removed_stages, "del")}</span></div>` : "",
    s.changed_stages.length ? `<div><b>Changed stages</b> <span class="chips">${chips(s.changed_stages, "chg")}</span></div>` : "",
    s.added_people.length ? `<div><b>New people</b> <span class="chips">${chips(s.added_people, "add")}</span></div>` : "",
    s.removed_people.length ? `<div><b>Removed people</b> <span class="chips">${chips(s.removed_people, "del")}</span></div>` : ""].join("") || `<div class="muted">No changes to stages or people.</div>`;
  const bills = s.bills.length ? `<div><b>Bills to open</b> ${s.bills.map(b => `<span class="chip ${b.skip ? "" : "add"}">${esc(b.client)}${b.skip ? " (already this month)" : ""}</span>`).join(" ")}</div>` : "";
  return (r.errors.length ? `<div class="msg err"><b>Fix these in the file, then check again:</b><ul>${r.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul></div>` : "") +
    (r.warnings.length ? `<div class="msg warn"><b>Worth a look:</b><ul>${r.warnings.map(e => `<li>${esc(e)}</li>`).join("")}</ul></div>` : "") +
    (r.applied ? `<div class="msg ok"><b>Applied${r.fresh ? " and started fresh" : ""}.</b> Everyone's screen now uses this workflow.${(r.opened || []).length ? " Opened " + esc(r.opened.join(", ")) + "." : ""}</div>` :
      r.ok ? `<div class="msg ok"><b>Looks good.</b> ${s.stages} stages, ${s.people} people, starts at ${esc(s.start)}, ends at ${esc(s.final.join(", "))}, time speed ${s.speed}×. Press <b>Apply</b> to switch over.</div>` : "") +
    `<div class="panel" style="margin-top:12px"><h3 style="margin-bottom:10px">What changes</h3><div style="display:grid;gap:10px">${changes}${bills}</div>` +
    `<details style="margin-top:10px"><summary class="small" style="cursor:pointer">Preview the stages in this file</summary><div class="scroll" style="margin-top:8px"><table><thead><tr><th style="text-align:left">Stage</th><th style="text-align:left">Done by</th><th style="text-align:left">Checked by</th><th>Hours</th><th style="text-align:left">Next</th><th style="text-align:left">Waits for</th><th style="text-align:left">Also alert</th></tr></thead><tbody>${s.table.map(t => `<tr><td style="text-align:left"><b>${esc(t.code)}</b> ${esc(t.name)}</td><td style="text-align:left">${esc(t.owners.join(", "))}</td><td style="text-align:left">${esc(t.validator)}</td><td>${esc(t.sla_hours)}</td><td style="text-align:left">${esc(t.next.join(", "))}</td><td style="text-align:left">${esc(t.requires.join(", "))}</td><td style="text-align:left">${esc(t.cc.join(", "))}</td></tr>`).join("")}</tbody></table></div></details></div>`;
}
function viewInput() {
  if (!isAdmin()) return `<div class="emptycard">Only admins can change the workflow.</div>`;
  const w = S.wf ? S.wf.input : {};
  const status = w.loaded_at ? `Last applied ${esc(fmt(w.loaded_at))} from <span class="mono">${esc(w.source)}</span>` : "Using the built-in Monthly Cycle definitions.";
  const mins = Number(w.auto_reload_minutes || 0);
  const pend = S.wfPending;
  return hero("Workflow input", "The stages, people and alerts come from one Excel workbook.") + `
  <div class="panel" style="margin-bottom:16px"><div class="row2"><div style="flex:1;min-width:240px"><h3>1 · Get the template</h3><p class="muted small" style="margin:0">Pre-filled with today's stages and people. Edit it in Excel, or upload it to Google Drive and open it as a Google Sheet.</p></div>
    <a class="btn primary" href="${withT("/api/workflow/template")}" download>Download template</a></div>
    <p class="muted small" style="margin:12px 0 0">${status}${w.error ? `<br><span style="color:var(--red)">Auto reload problem: ${esc(w.error)}</span>` : ""}</p></div>
  <div class="cols">
    <div class="panel"><h3>2a · Google Sheet link or file path</h3><p class="muted small">Google Sheet: Share → <i>Anyone with the link: Viewer</i>. Path: must be reachable from the PC running the app, for example <span class="kbd">G:\\Shared drives\\Data Center\\Workflow_Input.xlsx</span>.</p>
      <input class="in" id="loc" placeholder="https://docs.google.com/spreadsheets/d/…  or  G:\\…\\Workflow_Input.xlsx" value="${esc(w.location || "")}" aria-label="Google Sheet link or file path">
      <div class="row2" style="margin-top:10px"><label class="small muted" for="mins">Re-read automatically</label>
        <select class="in" id="mins" style="flex:0 0 auto;min-width:0;width:auto">${[[0, "Off"], [5, "Every 5 min"], [15, "Every 15 min"], [60, "Every hour"]].map(([v, l]) => `<option value="${v}" ${v === mins ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span style="flex:1"></span><button class="btn" id="locCheck" type="button">Check</button><button class="btn primary" id="locApply" type="button" ${pend && pend.kind === "loc" && pend.ok ? "" : "disabled"}>Apply</button></div></div>
    <div class="panel"><h3>2b · Upload from this computer</h3><p class="muted small">Pick the filled-in .xlsx (from Excel, or Google Sheets → File → Download → .xlsx).</p>
      <label class="drop" id="drop"><input type="file" id="file" accept=".xlsx" class="vh"><span id="fileName">${pend && pend.name ? esc(pend.name) : "Drop the .xlsx here or click to choose"}</span></label>
      <div class="row2" style="margin-top:10px"><span style="flex:1"></span><button class="btn" id="upCheck" type="button">Check</button><button class="btn primary" id="upApply" type="button" ${pend && pend.kind === "up" && pend.ok ? "" : "disabled"}>Apply</button></div></div>
  </div>
  <label class="panel" style="margin-top:16px;display:flex;gap:12px;align-items:flex-start;cursor:pointer">
    <input type="checkbox" id="merge" ${S.wfMerge ? "checked" : ""} style="width:20px;height:20px;margin-top:2px;accent-color:#0071e3">
    <span><b>Only update the stages in this file</b><span class="muted small" style="display:block">For a department's own sheet: its tasks are added (or replace stages with the same code) and every other stage stays. Column names can be the department's own (Task, Assigned to, Approver, TAT…); missing codes are made up and rows run in order.</span></span></label>
  <label class="panel" style="margin-top:12px;display:flex;gap:12px;align-items:flex-start;cursor:pointer">
    <input type="checkbox" id="fresh" ${S.wfFresh ? "checked" : ""} style="width:20px;height:20px;margin-top:2px;accent-color:#0071e3">
    <span><b>Start fresh</b><span class="muted small" style="display:block">Clears all current bills, tasks, alerts and time records and starts the new workflow empty. Use it when the new file changes the stage codes. People, contracts and Vault files are kept.</span></span></label>
  <div id="wfOut" style="margin-top:16px">${S.wfBusy ? `<div class="msg warn">Reading the file…</div>` : resultHtml(S.wfRes)}</div>`;
}
function wireInput() {
  const file = $("#file"), drop = $("#drop");
  const pick = (f) => { if (!f) return; const rd = new FileReader(); rd.onload = () => { const b = new Uint8Array(rd.result); let s = ""; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); S.wfPending = { kind: "up", name: f.name, file: btoa(s), ok: false }; S.wfRes = null; render(); }; rd.readAsArrayBuffer(f); };
  file.onchange = () => pick(file.files[0]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
  const run = async (kind, apply) => {
    let body;
    if (kind === "loc") { const loc = $("#loc").value.trim(); body = { location: loc, apply, fresh: S.wfFresh, merge: S.wfMerge, auto_reload_minutes: Number($("#mins").value) }; S.wfPending = { kind, loc, ok: false }; }
    else { if (!S.wfPending || !S.wfPending.file) return note("Choose a file first", "Drop the .xlsx in the box or click it to choose."); body = { file: S.wfPending.file, name: S.wfPending.name, apply, fresh: S.wfFresh, merge: S.wfMerge }; }
    if (apply && S.wfFresh && !confirm("Start fresh? All current bills, tasks, alerts and time records will be cleared.")) return;
    S.wfBusy = true; render();
    try { const resp = await fetch(kind === "loc" ? "/api/workflow/load" : "/api/workflow/upload", { method: "POST", headers: hdrs(), body: JSON.stringify(body) });
      const r = await resp.json().catch(() => ({ error: "Bad response" }));
      if (r.error && !r.summary) throw new Error(r.error); S.wfRes = r; S.wfPending.ok = r.ok && !r.applied;
      if (r.applied) { S.meta = await api("/api/meta"); S.wf = await api("/api/workflow"); note("Workflow applied", `${r.summary.stages} stages and ${r.summary.people} people are now live.`, "approved"); } }
    catch (e) { S.wfRes = { error: e.message }; }
    S.wfBusy = false; render();
  };
  $("#merge").onchange = (e) => { S.wfMerge = e.target.checked; if (S.wfPending) S.wfPending.ok = false; S.wfRes = null; render(); };
  $("#fresh").onchange = (e) => { S.wfFresh = e.target.checked; if (S.wfPending) S.wfPending.ok = false; S.wfRes = null; render(); };
  $("#locCheck").onclick = () => run("loc", false); $("#locApply").onclick = () => run("loc", true);
  $("#upCheck").onclick = () => run("up", false); $("#upApply").onclick = () => run("up", true);
}
