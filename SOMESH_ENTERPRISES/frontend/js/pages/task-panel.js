// Admin task panel: details, documents (download + file to storage), delete task / delete bill.
"use strict";
// ---------- a task given by the admin: details, documents, delete
async function openTask(id) {
  let d; try { d = await api("/api/adhoc"); } catch (e) { return note("Couldn't open", e.message); }
  S.adhoc = d; const t = d.tasks.find(x => x.id === id); if (!t) return note("Not found", "This task was deleted.");
  const st = t.status === "approved" && t.adhoc ? (t.ended_at ? "Ended" : "Adding documents") : STATUS[t.status] || t.status;
  if (t.files && t.files.length) S.docs["tk" + t.id] = { title: `${t.stage} ${t.stage_name} · ${t.assignee || ""}`, files: t.files };
  sheetHtml(`<div class="code">TASK FROM THE ADMIN · ${esc(t.stage)}</div><h2 style="margin:2px 0 6px">${esc(t.stage_name)}</h2>
    <div class="chips" style="margin-bottom:12px"><span class="pill p-${t.status === "approved" && !t.ended_at ? "docs" : t.status}">${esc(st)}</span>${t.needs_docs ? `<span class="chip">Needs documents</span>` : ""}</div>
    <div class="box"><dl class="kv"><dt>Person</dt><dd>${esc(t.assignee || t.owners.join(", "))}</dd><dt>Approver</dt><dd>${esc(t.validator)}</dd><dt>Given by</dt><dd>${esc(t.given_by || "")}</dd>
      <dt>Given</dt><dd>${esc(fmt(t.created_at))}</dd><dt>Time limit</dt><dd>${t.sla_hours} h · due ${esc(fmt(t.due_at))}</dd><dt>Time worked</dt><dd>${dur(t.worked_seconds)}</dd>
      ${t.bill_id ? `<dt>Bill</dt><dd>${esc(t.bill_id)}</dd>` : ""}${t.output_note ? `<dt>Note</dt><dd>${esc(t.output_note)}</dd>` : ""}</dl></div>
    <h3 style="margin:18px 0 8px">Documents</h3>${t.files && t.files.length ? `<div class="box">${fileList(t.files)}</div><button class="btn primary" type="button" id="tkDl" style="margin-top:12px">Download all and save to the folder</button>` : `<p class="muted small">No documents yet.</p>`}
    <div class="dangerzone"><b>Delete this task</b><p class="muted small">Removes the task, its timer records and alerts. Uploaded documents stay in storage.</p><button class="btn bad" type="button" id="tkDel">Delete task</button></div>`);
  const dl = $("#tkDl"); if (dl) dl.onclick = () => downloadDocs("tk" + t.id, t.files);
  $("#sheet").querySelectorAll("[data-preview]").forEach(x => x.onclick = () => showPreview(x.dataset.preview));
  $("#tkDel").onclick = () => deleteTask(t);
}
function deleteTask(t) {
  dialog(`<h3 style="margin:0">Delete ${esc(t.stage)} “${esc(t.stage_name)}”?</h3><p class="muted small">${esc(t.assignee || t.owners.join(", "))} will no longer see it. Its timer records and alerts are removed; uploaded documents stay in storage. This can't be undone.</p>`,
    async () => { try { await api(`/api/admin-task/${t.id}/delete`, {}); closeSheet(); note("Task deleted", `${t.stage} ${t.stage_name}`, "approved"); load(); } catch (e) { note("Couldn't delete", e.message); } });
}
function deleteBill(b) {
  dialog(`<h3 style="margin:0">Delete bill ${esc(b.id)}?</h3><p class="muted small">${esc(b.client)}. The bill, all its stage tasks, timer records and alerts are removed. Files already in storage stay. This can't be undone.</p>`,
    async () => { try { await api(`/api/bill/${encodeURIComponent(b.id)}/delete`, {}); closeSheet(); note("Bill deleted", b.id, "approved"); load(); } catch (e) { note("Couldn't delete", e.message); } });
}
// Admin downloads: the browser downloads the files AND the app saves a copy in the local storage, by department and person.
async function fileCopy(key) {
  const m = /^(as|tr|tk)(\d+)$/.exec(key || ""); if (!m || !isAdmin()) return;
  try { const r = await api(`/api/admin-task/${m[2]}/file`, {}); note("Saved to the storage folder", `${r.files} file${r.files === 1 ? "" : "s"} → storage/${r.folder}`, "approved"); }
  catch (e) { note("Downloaded, but not filed", e.message); }
}
function downloadDocs(key, files) {
  files.forEach((f, i) => setTimeout(() => { const a = document.createElement("a"); a.href = fileUrl(f.path); a.download = f.name; document.body.appendChild(a); a.click(); a.remove(); }, i * 400));
  fileCopy(key);
}
