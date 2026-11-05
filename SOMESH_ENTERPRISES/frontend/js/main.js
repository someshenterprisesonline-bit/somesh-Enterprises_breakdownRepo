// Starts the app. Must be the LAST script in index.html.
"use strict";
// ---------------------------------------------------------- start
(async () => {
  try { S.meta = await api("/api/meta"); syncClock(S.meta.server_now); } catch (e) { $("#app").innerHTML = `<p class="empty">Can't reach the server. Is the app running? Double-click START SOMESH ENTERPRISES.bat.</p>`; return; }
  S.token = store.get("se_token") || null; S.user = null;
  if (S.token) { try { const m = await api("/api/me"); S.user = m.user; } catch (e) { S.token = null; store.set("se_token", ""); } }
  render(); if (S.user) { connect(); load(); }
  document.addEventListener("click", unlockAudio, { once: true });
  setInterval(ticker, 1000);
  $("#sheetBack").onclick = closeSheet;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.billId && !$("#dlg").open) closeSheet(); });
  setInterval(() => { if (!S.user || (document.activeElement && document.activeElement.tagName === "INPUT")) return; if (["over", "pipe", "tracker", "dash"].includes(S.tab)) load(); else if (["mine", "check"].includes(S.tab)) render(); }, 30000);
})();
