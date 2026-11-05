// Pages: My tasks (staff + admins) and To check (approvers).
"use strict";
function viewMine() {
  const st = S.state; if (!st) return hero("Hello", "") + skeleton("cards");
  const running = st.mine.filter(t => t.status === "in_progress"), docs = st.mine.filter(t => t.status === "approved"),
        waiting = st.mine.filter(t => t.status === "submitted"), next = st.mine.filter(t => t.status === "assigned");
  const L = st.lunch || S.meta.lunch || {};
  const sec = (h, list) => list.length ? `<h2>${h}</h2><div class="grid">${list.map(t => taskCard(t, "mine")).join("")}</div>` : "";
  const fin = (st.finished_today || []).map(f => `<div class="row" style="grid-template-columns:110px 1fr auto"><span class="t">${esc(f.code)}</span><span>${esc(f.name)}</span><span class="muted small">${esc(fmt(f.at))} · ${dur(f.seconds)}</span></div>`).join("");
  return hero(`Hello, ${esc(S.user.split(" ").pop())}`, `${esc(me().dept || "")}${L.enabled !== false ? ` · lunch ${ampm(L.start)}–${ampm(L.end)}` : ""}`,
      `<div class="kpi" style="min-width:220px"><span>Worked today</span><b>${tick(st.today_seconds, running.length ? st.server_now : null, "timer")}</b></div>`) +
    (!st.mine.length ? `<div class="emptycard" style="padding:40px">No tasks right now. You'll hear a double beep when one arrives.</div>` : "") +
    sec("Working now", running) + sec("Approved – add documents and end", docs) + sec("Waiting for approval", waiting) + sec("Up next", next) +
    (fin ? `<h2>Finished today</h2><div class="list">${fin}</div>` : "");
}
function viewCheck() {
  const list = S.state ? S.state.check : [];
  return hero("To check", "Approve to hand the work to the next team, or send it back with what to fix.") +
    (list.length ? `<div class="grid">${list.map(t => taskCard(t, "check")).join("")}</div>` : `<div class="emptycard">Nothing to check right now.</div>`);
}
