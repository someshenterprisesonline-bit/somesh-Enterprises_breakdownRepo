// Shared state (S), small helpers, server calls (api), alert sound and toasts.
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
const S = { meta: null, user: store.get("se_user"), tab: "mine", state: null, pipe: null, es: null, sound: store.get("se_sound") !== "off", audio: null, wf: null, wfRes: null, wfPending: null };
const APP = "SOMESH ENTERPRISES";
const COLORS = ["#0071e3", "#34c759", "#ff9500", "#af52de", "#ff2d55", "#5ac8fa", "#5856d6", "#ff3b30", "#30b0c7", "#a2845e"];
const colorOf = (n) => COLORS[[...String(n)].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length];
const initials = (n) => String(n).replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/).map(p => p[0]).slice(-2).join("").toUpperCase();
const avatar = (n) => `<span class="avatar" style="background:${colorOf(n)}">${esc(initials(n))}</span>`;

const hdrs = () => ({ "Content-Type": "application/json", ...(S.token ? { "X-Session": S.token } : {}) });
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: hdrs(), body: JSON.stringify(body) } : { headers: hdrs() });
  const j = await r.json().catch(() => ({ error: "Bad response" }));
  if (r.status === 401 && j.login && S.user) { logout(true); throw new Error("Please sign in again"); }
  if (!r.ok || j.ok === false) throw new Error(j.error || "Request failed");
  return j;
}
const withT = (u) => u + (u.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(S.token || "");
// ---------------------------------------------------------- sound: a simple double beep for every alert
function unlockAudio() { try { S.audio = S.audio || new (window.AudioContext || window.webkitAudioContext)(); S.audio.resume(); } catch (e) {} }
function beep() {
  if (!S.sound || !S.audio) return;
  const t0 = S.audio.currentTime + 0.02;
  [0, 0.22].forEach((d) => {
    const o = S.audio.createOscillator(), g = S.audio.createGain();
    o.type = "sine"; o.frequency.value = 880; o.connect(g); g.connect(S.audio.destination);
    const t = t0 + d;
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.3, t + 0.01);
    g.gain.setValueAtTime(0.3, t + 0.11); g.gain.linearRampToValueAtTime(0.0001, t + 0.13);
    o.start(t); o.stop(t + 0.15);
  });
}
const KIND = { new_task: "New task", validate: "Please check", approved: "Approved", rejected: "Sent back", overdue: "Overdue", complete: "Bill complete" };
function toast(a) {
  const el = document.createElement("div"); el.className = "toast " + (a.kind || "");
  el.innerHTML = `<div class="h"><span class="ic">S</span><span>${APP}</span><i>now</i></div><b><span class="k"></span>${esc(a.title)}</b><p>${esc(a.body)}</p>
    <div class="actions"><button class="btn primary" type="button">Open</button><button class="btn" type="button">Dismiss</button></div>`;
  const [open, close] = el.querySelectorAll("button");
  open.onclick = () => { el.remove(); S.tab = a.kind === "validate" ? "check" : "mine"; render(); };
  close.onclick = () => el.remove();
  $("#toasts").prepend(el);
  setTimeout(() => { el.remove(); tidyToasts(); }, a.kind === "overdue" || a.kind === "rejected" ? 60000 : 20000);
  tidyToasts(true);
  beep();
  try {
    if ("Notification" in window && Notification.permission === "granted" && document.visibilityState !== "visible")
      new Notification(a.title, { body: a.body, tag: "se-" + a.id });
  } catch (e) {}
}
// Keep at most 3 alert banners on screen; the rest are counted in a "+N more" link to the Alerts tab.
function tidyToasts(added) {
  const box = $("#toasts"), list = [...box.querySelectorAll(".toast")];
  if (added && list.length > 3) { list.slice(3).forEach(t => t.remove()); S.hidden = (S.hidden || 0) + list.length - 3; }
  let more = box.querySelector(".more");
  if (S.hidden > 0) {
    if (!more) { more = document.createElement("button"); more.className = "btn more"; more.type = "button"; box.appendChild(more);
      more.onclick = () => { S.hidden = 0; more.remove(); S.tab = "alerts"; api("/api/alerts/read", {}).then(load); render(); }; }
    more.textContent = `+${S.hidden} more alert${S.hidden > 1 ? "s" : ""} · open Alerts`;
  } else if (more) more.remove();
}
function note(title, body, kind) { toast({ kind: kind || "rejected", title, body, id: Date.now() }); }
