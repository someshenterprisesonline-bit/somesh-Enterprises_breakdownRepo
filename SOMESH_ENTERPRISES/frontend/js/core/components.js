// Shared pieces: task card, file list, documents panel, preview, page header (hero), bill detail sheet.
"use strict";
function taskCard(t, mode) {
  const ins = t.inputs.length ? `<div class="box"><b>From the previous team</b>${t.inputs.map(i => `<div>${esc(i.stage)} ${esc(i.name)} · ${esc(i.by || "")}: ${esc(i.note || "")}${i.files && i.files.length ? fileList(i.files) : i.link ? `<div class="mono">${esc(i.link)}</div>` : ""}</div>`).join("")}</div>` : "";
  const canAttach = mode !== "check" && t.assignee === S.user && S.meta.storage && (t.adhoc ? t.status === "approved" : t.status === "in_progress");
  const own = mode !== "check" && (t.files.length || canAttach) ? `<div class="box"><b>${t.adhoc ? "Documents" : "Your files"}${t.accept.length ? ` <span class="muted small" style="font-weight:500">· accepts ${esc(t.accept.join(", "))}</span>` : ""}${t.file_required || (t.adhoc && t.needs_docs) ? ` <span class="pill p-soon" style="font-size:11px">required</span>` : ""}</b>
      ${t.files.length ? fileList(t.files, canAttach ? t.id : 0) : `<div class="muted small">No files attached yet.</div>`}
      ${canAttach ? `<label class="btn" style="margin-top:8px;display:inline-block;cursor:pointer">＋ Attach files<input type="file" multiple class="vh" data-attach="${t.id}" ${t.accept.length ? `accept="${esc(t.accept.map(a => "." + a).join(","))}"` : ""}></label>` : ""}</div>` : "";
  const back = t.decision_note && t.status === "in_progress" && t.rework_count ? `<div class="back"><b>Sent back:</b> ${esc(t.decision_note)}</div>` : "";
  let acts = "";
  if (mode === "check") acts = `<button class="btn good" data-act="approve" data-id="${t.id}">Approve &amp; hand over</button><button class="btn bad" data-act="reject" data-id="${t.id}">Send back</button>`;
  else if (t.status === "assigned") { const busy = t.adhoc && S.state && S.state.busy_with && S.state.busy_with !== t.id;
    acts = busy ? `<button class="btn" type="button" disabled>▶ Start</button><span class="muted small">Finish your current task first</span>` : `<button class="btn primary" data-act="claim" data-id="${t.id}">▶ Start task</button>`; }
  else if (t.status === "in_progress") acts = `<button class="btn primary" data-act="submit" data-id="${t.id}">${t.adhoc ? "✓ Done – send for approval" : "Submit for checking"}</button>`;
  else if (t.status === "submitted") acts = `<span class="muted small">Waiting for ${esc(t.validator)} to ${t.adhoc ? "approve" : "check"}</span>`;
  else if (t.status === "approved" && t.adhoc) acts = `<button class="btn good" data-act="end" data-id="${t.id}">End task${S.state && S.state.mine.some(x => x.status === "assigned" && x.adhoc) ? " &amp; go to next" : ""}</button>`;
  const timeRow = mode !== "check" && t.status === "in_progress" ? `<div class="run"><span class="live"></span>${tick(t.worked_seconds, t.timer_from)}<span class="muted small">running · lunch not counted</span></div>`
    : (t.worked_seconds || t.timer_from) ? `<div class="muted small">⏱ Worked ${dur(t.worked_seconds)}</div>` : "";
  const out = mode === "check" ? `<div class="box"><b>${esc(t.assignee)} submitted</b><div>${esc(t.output_note || "")}</div>${t.files.length ? fileList(t.files) : t.output_link ? `<div class="mono">${esc(t.output_link)}</div>` : ""}${t.branch ? `<div>${esc(t.branch_question)} <b style="display:inline">${esc(t.branch)}</b></div>` : ""}</div>` : "";
  return `<article class="card ${isLate(t) ? "late" : ""}">
    <div class="top"><div><div class="code">${esc(t.stage)} · ${esc(t.dept)}</div><div class="stage">${esc(t.stage_name)}</div></div><span class="pill p-${t.status === "approved" && t.adhoc ? "docs" : t.status}">${t.status === "approved" && t.adhoc ? "Approved – add documents" : t.status === "in_progress" ? "Running" : t.adhoc && t.status === "submitted" ? "Waiting for approval" : STATUS[t.status]}</span></div>
    <dl class="facts"><dt>Bill</dt><dd>${billBtn(t.bill_id, t.client)}</dd><dt>Deliver</dt><dd>${esc(t.expected_output)}</dd><dt>Checker</dt><dd>${esc(t.validator)}</dd></dl>
    ${t.adhoc ? `<div><span class="chip">Given by ${esc(t.given_by)}</span></div>` : ""}${timeRow}<div>${t.status === "submitted" ? `<span class="muted small">Sent ${esc(fmt(t.submitted_at))}</span>` : t.status === "approved" ? `<span class="muted small">Approved ${esc(fmt(t.decided_at))} · upload the documents, then end the task</span>` : dueText(t)}</div>${ins}${own}${out}${back}<div class="actions">${acts}</div></article>`;
}
const PREVIEWABLE = /\.(xlsx|xlsm|csv|tsv|txt|log|json|xml|md)$/i;
function fileList(files, removeFor) {
  return files.map(f => `<div class="frow"><a href="${fileUrl(f.path)}" target="_blank" rel="noopener" title="Open">📄 ${esc(f.name)}</a><span class="muted small">${kbs(f.size)}</span>
    ${PREVIEWABLE.test(f.name) ? `<button class="btn ghost" type="button" data-preview="${esc(f.path)}">Preview</button>` : ""}
    <a class="btn ghost" href="${fileUrl(f.path)}" download="${esc(f.name)}" style="padding:2px 6px;font-size:13px">Download</a>
    ${removeFor ? `<button class="btn ghost" type="button" style="color:var(--red)" data-unattach="${removeFor}" data-name="${esc(f.name)}" aria-label="Remove ${esc(f.name)}">Remove</button>` : ""}</div>`).join("");
}
S.docs = {};
const docsBtn = (key, title, files) => { if (!files || !files.length) return ""; S.docs[key] = { title, files };
  return `<button class="btn" type="button" data-docs="${esc(key)}" style="padding:4px 12px;font-size:13px" title="View or download" aria-label="Documents: ${files.length} file${files.length === 1 ? "" : "s"}">📄 ${files.length}</button>`; };
function showDocs(key) {
  const d = S.docs[key]; if (!d) return;
  sheetHtml(`<div class="code">DOCUMENTS</div><h2 style="margin:2px 0 4px">${esc(d.title)}</h2><p class="muted small">${d.files.length} file${d.files.length === 1 ? "" : "s"} · open to view, preview spreadsheets, or download.${isAdmin() ? " Downloading also saves a copy in the storage folder, by department and person." : ""}</p>
    <div class="box">${fileList(d.files)}</div>${d.files.length > 1 ? `<button class="btn primary" type="button" id="dlAll" style="margin-top:14px">Download all</button>` : ""}`);
  const b = $("#dlAll"); if (b) b.onclick = () => downloadDocs(key, d.files);
  $("#sheet").querySelectorAll("a[download]").forEach(a => a.addEventListener("click", () => fileCopy(key)));
  $("#sheet").querySelectorAll("[data-preview]").forEach(x => x.onclick = () => showPreview(x.dataset.preview));
}
async function attachFiles(id, files) {
  for (const f of files) {
    const buf = new Uint8Array(await f.arrayBuffer()); let s = "";
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    try { await api(`/api/tasks/${id}/upload`, { name: f.name, data: btoa(s) }); } catch (e) { note("Couldn't attach " + f.name, e.message); }
  }
  load();
}
async function showPreview(path) {
  let d; try { d = await api("/api/preview?path=" + encodeURIComponent(path)); } catch (e) { return note("Couldn't preview", e.message); }
  const name = path.split("/").pop();
  const body = d.kind === "table" ? `<div class="scroll" style="max-height:60vh"><table>${d.rows.map((r, i) => `<tr>${r.map(c => i ? `<td style="text-align:left">${esc(c)}</td>` : `<th style="text-align:left">${esc(c)}</th>`).join("")}</tr>`).join("")}</table></div>${d.sheets && d.sheets.length > 1 ? `<p class="muted small">Showing sheet "${esc(d.sheet)}" of ${d.sheets.length}. Download to see the others.</p>` : ""}`
    : `<pre style="white-space:pre-wrap;max-height:60vh;overflow:auto;background:var(--card2);padding:12px;border-radius:12px;font-size:12px">${esc(d.text)}</pre>`;
  const dl = $("#dlg"), f = $("#dlgForm");
  f.innerHTML = `<h3 style="margin:0 0 12px">${esc(name)}</h3>${body}<div class="actions" style="margin-top:16px;justify-content:flex-end"><a class="btn" href="${fileUrl(path)}" target="_blank" rel="noopener">Download</a><button class="btn primary" value="cancel" type="submit">Close</button></div>`;
  dl.style.width = "min(900px, calc(100vw - 32px))"; dl.onclose = () => { dl.style.width = ""; }; dl.returnValue = ""; dl.showModal();
}
function hero(title, sub, right) { return `<div class="hero"><div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ""}</div>${right || ""}</div>`; }
// ---------------------------------------------------------- bill detail sheet
async function loadBill(id, quiet) {
  S.billId = id; if (!quiet) { S.bill = null; drawSheet(); }
  try { S.bill = await api("/api/bill?id=" + encodeURIComponent(id)); } catch (e) { S.bill = { error: e.message }; }
  drawSheet();
}
function sheetHtml(html) {
  S.billId = null; const el = $("#sheet"); el.classList.add("open"); $("#sheetBack").classList.add("open"); el.setAttribute("aria-hidden", "false");
  el.innerHTML = `<div style="display:flex;justify-content:flex-end"><button class="btn" id="shX" type="button" aria-label="Close">✕</button></div>${html}`; $("#shX").onclick = closeSheet;
}
function closeSheet() { S.billId = null; S.bill = null; $("#sheet").classList.remove("open"); $("#sheetBack").classList.remove("open"); $("#sheet").setAttribute("aria-hidden", "true"); }
function drawSheet() {
  const el = $("#sheet"); el.classList.add("open"); $("#sheetBack").classList.add("open"); el.setAttribute("aria-hidden", "false");
  const d = S.bill;
  if (!d) { el.innerHTML = `<p class="empty">Loading…</p>`; return; }
  if (d.error) { el.innerHTML = `<button class="btn" id="shX" type="button">Close</button><p class="empty">${esc(d.error)}</p>`; $("#shX").onclick = closeSheet; return; }
  const b = d.bill, byCode = Object.fromEntries(d.tasks.map(t => [t.stage, t])), opt = optionalStages();
  const order = S.meta.stages.filter(s => !opt.has(s.code) || byCode[s.code]);
  const done = order.filter(s => (byCode[s.code] || {}).status === "approved").length, pct = Math.round(done / Math.max(1, order.length) * 100);
  const now = NOW();
  const tl = order.map(s => { const t = byCode[s.code];
    if (!t) return `<li><span class="d d-none"></span><b style="color:var(--muted)">${esc(s.code)} ${esc(s.name)}</b><div class="muted">Not started · ${esc(s.owners.join(", "))} → checked by ${esc(s.validator)}</div></li>`;
    const late = (t.status === "assigned" || t.status === "in_progress") && new Date(t.due_at.replace(" ", "T")) < now;
    const when = t.decided_at && t.status === "approved" ? `approved ${fmt(t.decided_at)} by ${esc(t.validator)}` : t.submitted_at ? `submitted ${fmt(t.submitted_at)}, waiting for ${esc(t.validator)}` : t.claimed_at ? `started ${fmt(t.claimed_at)}` : `assigned ${fmt(t.created_at)}`;
    return `<li><span class="d d-${late ? "late" : t.status}"></span><b>${esc(s.code)} ${esc(t.name)}</b> <span class="pill p-${late ? "late" : t.status}" style="margin-left:4px">${late ? "Overdue" : STATUS[t.status] || t.status}</span>
      <div class="muted">${esc(t.assignee || t.owners.join(", "))} · ${when}${t.rework_count ? ` · sent back ${t.rework_count}×` : ""}</div>
      ${t.output_note ? `<div class="small">${esc(t.output_note)}${t.branch ? ` · answer: <b style="font-size:13px">${esc(t.branch)}</b>` : ""}</div>` : ""}${t.output_link ? `<div class="mono">${esc(t.output_link)}</div>` : ""}
      ${t.decision_note && t.rework_count ? `<div class="small" style="color:var(--red)">Last sent back: ${esc(t.decision_note)}</div>` : ""}</li>`; }).join("");
  const files = d.files.length ? ["Hand-off", "Vault"].map(a => { const f = d.files.filter(x => x.area === a); return f.length ? `<h3 class="dept" style="margin:16px 0 8px">${a} · ${f.length} files</h3><div class="list">${f.map(x => `<div class="row" style="grid-template-columns:1fr auto"><a href="${fileHref(x.path)}" target="_blank" rel="noopener">${esc(x.name)}</a><span class="muted small">${kbs(x.size)}</span></div>`).join("")}</div>` : ""; }).join("") : `<p class="muted small">No files in storage for this bill yet.</p>`;
  const c = d.contract;
  el.innerHTML = `<div class="top"><div><div class="code">BILL</div><h2 style="margin:2px 0 0">${esc(b.id)}</h2><div class="muted">${esc(b.client)} · opened ${esc(fmt(b.created_at))}</div></div><button class="btn" id="shX" type="button" aria-label="Close">✕</button></div>
    <div style="display:flex;gap:12px;align-items:center;margin:16px 0 6px"><div class="prog" style="flex:1;height:10px"><i style="width:${pct}%"></i></div><b>${done}/${order.length}</b></div>
    <div class="chips" style="margin-bottom:16px"><span class="pill ${b.status === "complete" ? "p-approved" : "p-assigned"}">${b.status === "complete" ? "Complete" : "Open"}</span>
      ${b.contract_status ? `<span class="pill ${b.contract_status === "Active" ? "p-approved" : "p-late"}">Contract: ${esc(b.contract_status)}</span>` : ""}${c ? `<span class="chip">${esc(c["Contract No"] || "")}</span>` : ""}</div>
    ${b.vault_folder ? `<div class="box" style="margin-bottom:14px"><b>Filed in the Vault</b><div class="mono">${esc(b.vault_folder)}</div></div>` : ""}
    <h3 style="margin:8px 0 12px">Stages</h3><ul class="tl">${tl}</ul>
    <h3 style="margin:18px 0 0">Files</h3>${files}
    <h3 style="margin:22px 0 8px">History</h3><div class="list">${d.events.slice(0, 40).map(e => `<div class="row" style="grid-template-columns:120px 1fr"><span class="t">${esc(fmt(e.ts))}</span><span class="small">${esc(e.text)}</span></div>`).join("")}</div>
    ${isAdmin() ? `<div class="dangerzone"><b>Delete this bill</b><p class="muted small">Removes the bill, all its stage tasks, timer records and alerts. Files in storage stay.</p><button class="btn bad" type="button" id="billDel">Delete bill</button></div>` : ""}`;
  $("#shX").onclick = closeSheet; const bd = $("#billDel"); if (bd) bd.onclick = () => deleteBill(b);
}
