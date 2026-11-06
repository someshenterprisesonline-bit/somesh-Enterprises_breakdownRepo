// Starts the app. Must be the LAST script in index.html.
"use strict";
// ---------------------------------------------------------- start
(async () => {
  try { startBrandIntro(); } catch (e) { finishBrandIntro(); }
  try { S.meta = await api("/api/meta"); syncClock(S.meta.server_now); } catch (e) { $("#app").innerHTML = `<p class="empty">Can't reach the server. Is the app running? Double-click START SOMESH ENTERPRISES.bat.</p>`; return; }
  S.token = store.get("se_token") || null; S.user = null;
  if (S.token) { try { const m = await api("/api/me"); S.user = m.user; if (m.admin) S.tab = "dash"; } catch (e) { S.token = null; store.set("se_token", ""); } }
  render(); if (S.user) { connect(); load(); }
  document.addEventListener("click", unlockAudio, { once: true });
  setInterval(ticker, 1000);
  setInterval(async () => {
    if (S.user || $("#dlg").open || document.hidden) return;
    try { const meta = await api("/api/meta"); const changed = JSON.stringify(meta.users) !== JSON.stringify(S.meta.users); S.meta = meta; if (changed) render(); } catch (e) {}
  }, 15000);
  $("#sheetBack").onclick = closeSheet;
  // Esc: close the side panel; if none is open, hide pop-ups and alerts (an open dialog closes itself on Esc)
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || $("#dlg").open) return;
    if ($("#sheet").classList.contains("open")) { closeSheet(); return; }
    hideTip(); const ct = $("#chTip"); if (ct) ct.classList.remove("show");
    if ($("#toasts").children.length) dismissAll();
  });
  setInterval(() => { if (!S.user || (document.activeElement && document.activeElement.tagName === "INPUT")) return; if (["over", "pipe", "tracker", "dash"].includes(S.tab)) load(); else if (["mine", "check"].includes(S.tab)) render(); }, 30000);
})();
