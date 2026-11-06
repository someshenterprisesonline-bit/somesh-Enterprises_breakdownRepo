// Live connection (Server-Sent Events) and load(): fetches the data each tab needs.
"use strict";
// ---------------------------------------------------------- live connection
function connect() {
  if (S.es) S.es.close();
  if (!S.user) return;
  S.es = new EventSource(withT("/stream"));
  startAlertCenterLive();
  S.es.onopen = () => { const d = $("#dot"); if (d) d.classList.add("on"); clearTimeout(S.offT); $("#banner").classList.remove("show"); if (S.wasOff) { S.wasOff = false; refresh(); } };
  S.es.onerror = () => { const d = $("#dot"); if (d) d.classList.remove("on"); clearTimeout(S.offT); S.offT = setTimeout(() => { S.wasOff = true; $("#banner").classList.add("show"); }, 4000); };
  S.es.onmessage = async (e) => {
    const m = JSON.parse(e.data);
    if (m.type === "alert") { receiveAlertNotification(m); if (isAdmin()) return; }
    if (m.type === "alerts_changed") { scheduleAlertCenterRefresh(); return; }
    if (isAdmin()) scheduleAlertCenterRefresh();
    if (m.type === "reload") { try { S.meta = await api("/api/meta"); } catch (er) {} if (!S.meta.users.some(u => u.name === S.user)) { logout(true); return; } }
    refresh();
  };
}
let refreshTimer = null;
function refresh() { clearTimeout(refreshTimer); refreshTimer = setTimeout(load, 150); }
async function load() {
  if (!S.user) return render();
  try { [S.state, S.pipe] = await Promise.all([api("/api/state"), isAdmin() ? api("/api/pipeline") : Promise.resolve(null)]); } catch (e) { console.error(e); }
  if (S.user && isAdmin()) await refreshAlertCenter(false);
  if (!S.user) return;
  if (S.tab === "assign") { try { S.adhoc = await api("/api/adhoc"); } catch (e) {} }
  if (S.tab === "auto") await loadAuto();
  if (S.tab === "tracker") { try { S.tr = await api(trUrl()); } catch (e) {} }
  if (S.tab === "pipe" && (S.pv || "time") === "time") { try { S.tt = await api(ttUrl()); if (!S.tpls) S.tpls = (await api("/api/templates")).templates; } catch (e) {} }
  if (S.tab === "dash") { try { S.dash = await api(dashUrl()); } catch (e) {} }
  if (S.state) syncClock(S.state.server_now);
  if (S.tab === "input") { try { S.wf = await api("/api/workflow"); } catch (e) {} }
  if (S.tab === "store") { try { S.st = await api("/api/storage"); } catch (e) {} }
  render();
  if (S.billId) loadBill(S.billId, true);
}
