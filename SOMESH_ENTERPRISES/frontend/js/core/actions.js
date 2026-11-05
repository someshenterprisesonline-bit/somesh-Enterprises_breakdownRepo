// Task buttons: Start, Done/Submit, Approve, Send back, End (dialogs).
"use strict";
// ---------------------------------------------------------- actions
const ALL = () => [...(S.state.mine || []), ...(S.state.check || [])];
function handoffPath(t) {
  const safe = (x) => String(x).replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/^[ .]+|[ .]+$/g, "").slice(0, 80);
  return S.meta.handoff_base + S.meta.sep + `${t.bill_id} ${safe(t.client)}` + S.meta.sep;
}
function dialog(html, onOk) {
  const d = $("#dlg"), f = $("#dlgForm");
  f.innerHTML = html + `<div class="actions" style="margin-top:20px;justify-content:flex-end"><button class="btn" value="cancel" type="submit" formnovalidate>Cancel</button><button class="btn primary" value="ok" type="submit">Confirm</button></div>`;
  const uh = $("#useHand"); if (uh) uh.onclick = () => { const t = ALL().find(x => x.id === S.dlgTask); if (t) { $("#link").value = handoffPath(t); $("#link").focus(); } };
  d.onclose = () => { if (d.returnValue === "ok") onOk(new FormData(f)); };
  d.returnValue = ""; d.showModal();
}
async function act(kind, id) {
  const t = ALL().find(x => x.id === id); unlockAudio();
  const run = async (body) => { try { await api(`/api/tasks/${id}/${kind}`, body || {}); load(); } catch (e) { note("Couldn't do that", e.message); } };
  if (kind === "claim") return run();
  if (kind === "approve") return run({ note: "" });
  if (kind === "end") return run();
  if (kind === "submit" && t.adhoc) return dialog(`<h3 style="margin:0">Done: ${esc(t.stage_name)}</h3><p class="muted small">Your timer stops and ${esc(t.validator)} gets an alert to approve it. After approval you'll add the documents and end the task.</p>
      <label class="f" for="note">What did you do? (optional)</label><textarea class="in" id="note" name="note" rows="3"></textarea>`, (fd) => run({ note: fd.get("note") || "Done" }));
  if (kind === "submit") {
    S.dlgTask = id;
    const br = t.branch_question ? `<label class="f">${esc(t.branch_question)}</label><div class="radios">${t.branch_options.map((o, i) => `<label><input type="radio" name="branch" value="${esc(o)}" ${i === 0 ? "required" : ""}> ${esc(o)}</label>`).join("")}</div>` : "";
    return dialog(`<h3 style="margin:0">Submit ${esc(t.stage)} · ${esc(t.stage_name)}</h3><p class="muted small">${esc(t.validator)} gets an alert to check it. After approval the next team is alerted.</p>
      <label class="f" for="note">What did you deliver?</label><textarea class="in" id="note" name="note" rows="2">${esc(t.expected_output)}</textarea>
      ${t.files.length ? `<p class="small" style="margin:12px 0 0;color:var(--green)"><b>${t.files.length} file${t.files.length > 1 ? "s" : ""} attached.</b> The checker and the next team get them; a path is optional.</p>` : t.file_required ? `<p class="small" style="margin:12px 0 0;color:var(--orange)"><b>This stage needs a file.</b> Attach it on the card, or give the path below.</p>` : ""}
      <label class="f" for="link">Where is the file? (shared-drive path or link)</label><input class="in" type="text" id="link" name="link" placeholder="G:\\Shared drives\\…">
      ${S.meta.handoff_base ? `<button class="btn ghost" type="button" id="useHand" style="padding-left:0;margin-top:6px">Use this bill's hand-off folder</button>` : ""}${br}`,
      (fd) => run({ note: fd.get("note"), link: fd.get("link"), branch: fd.get("branch") }));
  }
  if (kind === "reject") return dialog(`<h3 style="margin:0">Send ${esc(t.stage)} back to ${esc(t.assignee)}</h3><label class="f" for="why">What needs fixing?</label><textarea class="in" id="why" name="note" rows="3" required></textarea>`,
    (fd) => run({ note: fd.get("note") }));
}
