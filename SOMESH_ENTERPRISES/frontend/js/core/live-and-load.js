// Live connection (Server-Sent Events) and load(): fetches the data each tab needs.
"use strict";
// ---------------------------------------------------------- live connection
function connect() {
  if (S.es) S.es.close();
  clearTimeout(S.reconnectT);
  if (!S.user) return;
  const es = S.es = new EventSource(withT("/stream"));
  startAlertCenterLive();
  es.onopen = () => { S.retry = 0; const d = $("#dot"); if (d) d.classList.add("on"); clearTimeout(S.offT); $("#banner").classList.remove("show"); if (S.wasOff) { S.wasOff = false; refresh(); } };
  es.onerror = () => {
    const d = $("#dot"); if (d) d.classList.remove("on"); clearTimeout(S.offT); S.offT = setTimeout(() => { S.wasOff = true; $("#banner").classList.add("show"); }, 4000);
    // The browser retries a dropped stream by itself; a refused/failed response closes it for good, so retry with back-off.
    if (es.readyState === EventSource.CLOSED && S.es === es) reconnectLater();
  };
  es.onmessage = async (e) => {
    const m = JSON.parse(e.data);
    if (m.seq) {   // each server message is applied once, even across reconnects
      if (m.boot !== S.boot) { S.boot = m.boot; S.seen = new Set(); }
      if (S.seen.has(m.seq)) return;
      S.seen.add(m.seq); if (S.seen.size > 500) S.seen = new Set([...S.seen].slice(-200));
    }
    if (m.type === "excel_changed") { if (typeof xlRemoteChange === "function") xlRemoteChange(m); return; }
    if (m.type === "alert") { receiveAlertNotification(m); if (isAdmin()) return; }
    if (m.type === "alerts_changed") { scheduleAlertCenterRefresh(); return; }
    if (isAdmin()) scheduleAlertCenterRefresh();
    if (m.type === "reload") { try { S.meta = await api("/api/meta"); } catch (er) {} if (!S.meta.users.some(u => u.name === S.user)) { logout(true); return; } }
    refresh();
  };
}
function reconnectLater() {
  clearTimeout(S.reconnectT);
  S.retry = (S.retry || 0) + 1;
  S.reconnectT = setTimeout(async () => {
    if (!S.user) return;
    try { await api("/api/me"); } catch (e) { if (S.user) reconnectLater(); return; }   // 401 signs out inside api()
    S.wasOff = true; connect();
  }, Math.min(30000, 1000 * 2 ** Math.min(S.retry, 5)));
}
window.addEventListener("online", () => {
  if (S.user && (!S.es || S.es.readyState === EventSource.CLOSED)) { S.retry = 0; S.wasOff = true; connect(); }
});
let refreshTimer = null;
function refresh() { clearTimeout(refreshTimer); refreshTimer = setTimeout(load, 150); }
async function load() {
  if (!S.user) return render();
  try { [S.state, S.pipe] = await Promise.all([api("/api/state"), isAdmin() ? api("/api/pipeline") : Promise.resolve(null)]); } catch (e) { console.error(e); }
  if (S.user && isAdmin()) await refreshAlertCenter(false);
  if (!S.user) return;
  if (S.tab === "assign") { try { S.adhoc = await api("/api/adhoc"); } catch (e) {} }
  if (S.tab === "action") await sacLoad(false);
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
