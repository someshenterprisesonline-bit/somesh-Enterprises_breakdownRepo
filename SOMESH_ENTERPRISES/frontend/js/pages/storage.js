// Page: Storage (Master Tracker, Contract Register, Vault) - admins and Data Center.
"use strict";
// ---------------------------------------------------------- storage (Data Center)
function viewStore() {
  const d = S.st; if (!d) return hero("Storage", "") + skeleton("table", 6);
  if (!d.enabled) return hero("Storage", "") + `<div class="emptycard">Storage is turned off in config.json (storage.enabled).</div>`;
  const files = d.tree.filter(f => !f.dir);
  const trackers = files.filter(f => f.path.startsWith("01 Master Tracker/") && f.name.endsWith(".xlsx")).sort((a, b) => b.name.localeCompare(a.name));
  const regFile = files.find(f => f.path === "02 Contract Register/Contract_Register.xlsx"), idx = files.find(f => f.path === "03 Vault/Vault_Index.xlsx");
  const today = new Date().toISOString().slice(0, 10);
  const expired = d.register.filter(c => c["End date"] && String(c["End date"]).slice(0, 10) < today);
  const filed = d.bills.filter(b => b.vault_folder);
  const link = (f, label) => f ? `<a class="btn" href="${fileUrl(f.path)}" target="_blank" rel="noopener">${label}</a>` : `<span class="muted small">Not created yet</span>`;
  const st = d.status || {};
  const card = (color, title, big, sub, btn) => `<div class="panel" style="border-top:4px solid ${color}"><span class="muted small" style="font-weight:600">${title}</span><b style="display:block;font-size:30px;letter-spacing:-.03em;text-shadow:var(--tshadow)">${big}</b><p class="muted small" style="margin:2px 0 12px">${sub}</p>${btn}</div>`;
  const reg = d.register.map(c => { const ex = c["End date"] && String(c["End date"]).slice(0, 10) < today;
    return `<tr><td style="text-align:left"><b>${esc(c["Contract No"])}</b></td><td style="text-align:left">${esc(c.Client)}</td><td style="text-align:left">${esc(c.Service || "")}</td><td>${esc(dshort(c["End date"]))}</td><td><span class="pill ${ex ? "p-late" : "p-approved"}">${ex ? "Expired" : "Active"}</span></td><td>${c["Contract file"] ? `<a href="${fileUrl(String(c["Contract file"]).replace(/\\/g, "/"))}" target="_blank" rel="noopener">Open</a>` : ""}</td></tr>`; }).join("");
  const bills = d.bills.map(b => `<tr><td style="text-align:left"><b>${esc(b.id)}</b></td><td style="text-align:left">${esc(b.client)}</td><td style="text-align:left">${esc(b.contract_no || "-")}</td><td><span class="pill ${b.contract_status === "Active" ? "p-approved" : "p-late"}">${esc(b.contract_status || "-")}</span></td><td>${b.status === "complete" ? "Complete" : "Open"}</td><td style="text-align:left" class="mono">${esc(b.vault_folder || "")}</td></tr>`).join("");
  const tree = d.tree.map(f => f.dir ? `<div class="row" style="grid-template-columns:1fr auto"><span style="padding-left:${f.depth * 18}px"><b>📁 ${esc(f.name)}</b></span><span></span></div>`
    : `<div class="row" style="grid-template-columns:1fr auto"><span style="padding-left:${f.depth * 18}px">📄 <a href="${fileUrl(f.path)}" target="_blank" rel="noopener">${esc(f.name)}</a></span><span class="muted small">${kb(f.size)} · ${esc(f.modified)}</span></div>`).join("");
  return hero("Storage", `Data Center folders on <span class="mono">${esc(d.root)}</span>`, `<button class="btn" id="stSync" type="button">Update Master Tracker now</button>`) +
    (st.error ? `<div class="msg err">Last update failed: ${esc(st.error)}</div>` : "") +
    ((st.locked || []).length ? `<div class="msg warn">${esc(st.locked.join(", "))} is open in Excel, so the app couldn't update it. Close it and press Update.</div>` : "") +
    `<div class="cols" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">
      ${card("#34c759", "01 Master Tracker", trackers.length + (trackers.length === 1 ? " month" : " months"), `Updated ${esc(fmt(st.tracker_at) || "-")} · ${d.bills.length} bills`, link(trackers[0], "Open this month"))}
      ${card("#ff9500", "02 Contract Register", d.register.length + " contracts", `${expired.length} expired · ${d.bills.filter(b => b.contract_status && b.contract_status !== "Active").length} bills need attention`, link(regFile, "Open register"))}
      ${card("#af52de", "03 Vault", filed.length + (filed.length === 1 ? " bill filed" : " bills filed"), `Year / Month / Bill folders`, link(idx, "Open Vault index"))}</div>
    <h2>How the storage works</h2><div class="panel" style="padding:10px"><img src="/static/assets/storage_architecture.png" alt="Storage architecture: teams save to 00 Handoff, the app updates 01 Master Tracker, checks 02 Contract Register and files finished bills in 03 Vault" style="width:100%;height:auto;border-radius:12px;display:block"></div>
    <h2>Contract Register</h2><div class="panel scroll"><table><thead><tr><th style="text-align:left">Contract</th><th style="text-align:left">Client</th><th style="text-align:left">Service</th><th>Ends</th><th>Status</th><th>File</th></tr></thead><tbody>${reg || `<tr><td colspan="6" class="empty">No contracts yet. Open Contract_Register.xlsx and add one row per contract.</td></tr>`}</tbody></table></div>
    <h2>Bills: contract and vault</h2><div class="panel scroll"><table><thead><tr><th style="text-align:left">Bill</th><th style="text-align:left">Client</th><th style="text-align:left">Contract</th><th>Check</th><th>Bill</th><th style="text-align:left">Vault folder</th></tr></thead><tbody>${bills}</tbody></table></div>
    <h2>All folders and files</h2><div class="list">${tree}</div>`;
}
function wireStore() {
  const b = $("#stSync"); if (!b) return;
  b.onclick = async () => { try { await api("/api/storage/sync", {}); S.st = await api("/api/storage"); render(); note("Master Tracker updated", "The workbook now matches the app.", "approved"); } catch (e) { note("Couldn't update", e.message); } };
}
