// Starts the app. Must be the LAST script in index.html.
"use strict";
function validateProfileMeta(meta){
 if(!Array.isArray(meta?.users)||!meta.users.length||!meta.users.some(u=>u.admin))throw new Error('Authoritative user profiles are unavailable.');
 return meta;
}
// ---------------------------------------------------------- start
(async () => {
  try { startBrandIntro(); } catch (e) { finishBrandIntro(); }
  try { S.meta = validateProfileMeta(await api("/api/meta")); syncClock(S.meta.server_now); } catch (e) { $("#app").innerHTML = `<p class="empty">Unable to load user profiles: ${esc(e.message)}. Check the server and its configuration; no replacement profiles are displayed.</p>`; return; }
  S.token = store.get("se_token") || null; S.user = null;
  if (S.token) { try { const m = await api("/api/me"); S.user = m.user; if (m.admin) S.tab = "dash"; } catch (e) { S.token = null; store.set("se_token", ""); } }
  if (S.user && new URLSearchParams(location.search).has("excel") && xlEligible()) S.tab = "excel";
  render(); if (S.user) { connect(); load(); }
  document.addEventListener("click", unlockAudio, { once: true });
  setInterval(ticker, 1000);
  setInterval(async () => {
    if (S.user || $("#dlg").open || document.hidden) return;
    try { const meta = validateProfileMeta(await api("/api/meta")); const changed = JSON.stringify(meta.users) !== JSON.stringify(S.meta.users); S.meta = meta; const failed=S.profileError;S.profileError=null;if(changed||failed)render(); } catch (e) {S.profileError=e.message;render();}
  }, 15000);
  $("#sheetBack").onclick = closeSheet;
  // Esc: close the side panel; if none is open, hide pop-ups and alerts (an open dialog closes itself on Esc)
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || $("#dlg").open) return;
    if ($("#sheet").classList.contains("open")) { closeSheet(); return; }
    hideTip(); const ct = $("#chTip"); if (ct) ct.classList.remove("show");
    if ($("#toasts").children.length) dismissAll();
  });
  setInterval(() => { if (!S.user || document.hidden || (S.tab !== "action" && document.activeElement && document.activeElement.tagName === "INPUT")) return; if (["action", "over", "pipe", "tracker", "dash"].includes(S.tab)) load(); else if (["mine", "check"].includes(S.tab)) render(); }, 30000);
})();
