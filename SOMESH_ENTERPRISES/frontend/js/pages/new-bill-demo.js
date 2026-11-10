// Optional page: New bill (open bills + demo controls).
"use strict";
function viewAdmin() {
  return hero("New bill", "Opening a bill alerts the team at the start stage.") + `<div class="cols">
  <div class="panel"><h3>Open bills</h3><p class="muted small">One client per line to open several at once. The start-stage team hears the double beep straight away.</p>
    <textarea class="in" id="client" rows="3" placeholder="ABC Industries&#10;XYZ Hospital" aria-label="Client names, one per line">${esc(S.billDraft?.user === S.user ? S.billDraft.text : "")}</textarea>
    <div class="row2" style="margin-top:10px"><span style="flex:1"></span><button class="btn primary" id="newBill" type="button" ${S.openingBills ? "disabled" : ""}>${S.openingBills ? "Opening..." : "Open bills"}</button></div></div>
  <div class="panel"><h3>Demo</h3><p class="muted small">Only admins see demo data: staff never get its tasks, alerts or files, and it stays out of the real Master Tracker, Vault and daily export. Demo bills are numbered DEMO-… and run 60× faster. Real bills are never touched.</p>
    <div class="row2"><button class="btn primary" id="reset" type="button">${hasDemo() ? "Reload demo data" : "Load demo data"}</button><button class="btn" id="sim" type="button" ${hasDemo() ? "" : "disabled"}>Move one step</button>
      <button class="btn" id="auto" type="button" ${hasDemo() ? "" : "disabled"}>${S.auto ? "Stop auto-play" : "Auto-play every 4 s"}</button>${hasDemo() ? `<button class="btn bad" id="clearDemo" type="button">Clear demo data</button>` : ""}</div>
    <p class="muted small" id="simOut" style="margin-top:10px">${esc(S.billOpenStatus?.user === S.user ? S.billOpenStatus.text : "")}</p></div></div>`;
}
function wireAdmin() {
  $("#client").oninput = () => { S.billDraft = { user: S.user, text: $("#client").value }; };
  $("#newBill").onclick = async () => {
    if (S.openingBills) return;
    const user = S.user, token = S.token, client = $("#client").value;
    S.billDraft = { user, text: client }; S.openingBills = true; render();
    try {
      const r = await api("/api/bills", { client });
      if (S.user !== user || S.token !== token) return;
      S.billOpenStatus = { user, text: r.bill_id + " opened" };
      if (S.billDraft?.text === client) S.billDraft = { user, text: "" };
      await load();
    } catch (e) { if (S.user === user && S.token === token) note("Couldn't do that", e.message); }
    finally { if (S.user === user && S.token === token) { S.openingBills = false; render(); } }
  };
  $("#sim").onclick = async () => { try { const r = await api("/api/demo/simulate", {}); $("#simOut").textContent = r.did; } catch (e) { note("Couldn't do that", e.message); } };
  $("#reset").onclick = async () => { try { const r = await api("/api/demo/reset", {}); S.showDemo = true; note("Demo data loaded", `${r.bills.join(", ")} · visible to admins only`, "approved"); load(); } catch (e) { note("Couldn't load the demo", e.message); } };
  const cd = $("#clearDemo"); if (cd) cd.onclick = async () => { if (!confirm("Remove all demo bills, tasks, alerts and demo files? Real data is kept.")) return;
    if (S.auto) { clearInterval(S.auto); S.auto = null; } try { const r = await api("/api/demo/clear", {}); note("Demo data cleared", `${r.cleared} demo bill${r.cleared === 1 ? "" : "s"} removed`, "approved"); load(); } catch (e) { note("Couldn't clear", e.message); } };
  $("#auto").onclick = () => {
    if (S.auto) { clearInterval(S.auto); S.auto = null; } else S.auto = setInterval(() => api("/api/demo/simulate", {}).then(r => { const o = $("#simOut"); if (o) o.textContent = r.did; }).catch(() => {}), 4000);
    render();
  };
}
