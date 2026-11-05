// Page: Tracker (daily time tracker, export, lunch settings).
"use strict";
// ---------------------------------------------------------- admin: time tracker
function viewTracker() {
  const d = S.tr; if (!d) return hero("Tracker", "") + skeleton("cards", 4) + `<div style="height:16px"></div>` + skeleton("table", 6);
  const L = d.lunch, live = d.date === today();
  const pq = (S.tq || "").toLowerCase();
  const rows = d.rows.filter(r => !pq || (r.person + " " + r.task + " " + r.dept + " " + r.code).toLowerCase().includes(pq))
    .filter(r => S.tAll || r.day_seconds > 0 || r.running_since || r.code.startsWith("TASK-"));
  const so = S.trSort || { k: "", dir: 1 };
  const key = { person: r => r.person.toLowerCase(), task: r => (r.code + " " + r.task).toLowerCase(), started: r => r.started_at || "", done: r => r.done_at || "",
                approved: r => r.approved_at || "", ended: r => r.ended_at || "", worked: r => r.day_seconds || 0, status: r => r.status }[so.k];
  if (key) rows.sort((a, b) => { const x = key(a), y = key(b); return (x < y ? -1 : x > y ? 1 : 0) * so.dir; });
  const th = (k, label, left) => `<th ${left ? 'style="text-align:left"' : ""} aria-sort="${so.k === k ? (so.dir > 0 ? "ascending" : "descending") : "none"}"><button type="button" class="sortbtn" data-sort="${k}">${label}<span class="arr">${so.k === k ? (so.dir > 0 ? "▲" : "▼") : "↕"}</span></button></th>`;
  const people = d.people.filter(p => S.tAll || p.seconds > 0 || p.running);
  const cards = people.map(p => `<div class="pcard"><div class="who">${avatar(p.person)}<div><b>${esc(p.person)}</b><div class="muted small">${esc(p.dept)}</div></div></div>
      <div>${live && p.running ? tick(p.seconds, d.server_now, "timer") : `<span class="timer">${clock(p.seconds)}</span>`}</div>
      <div class="muted small">${p.tasks} task${p.tasks === 1 ? "" : "s"} · ${p.finished} finished</div>
      ${p.running ? `<div class="small"><span class="live" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#34c759;margin-right:6px"></span>${esc(p.running)}</div>` : `<div class="muted small">Not running a task</div>`}</div>`).join("");
  const pill = (st) => `<span class="pill ${/Running/.test(st) ? "p-in_progress" : /Waiting for approval/.test(st) ? "p-submitted" : /documents/.test(st) ? "p-docs" : /Ended|Approved/.test(st) ? "p-approved" : "p-assigned"}">${esc(st)}</span>`;
  const t = (v) => v ? esc(String(v).slice(11, 16)) : "–";
  const table = rows.map(r => `<tr><td style="text-align:left"><b>${esc(r.person)}</b><div class="muted small">${esc(r.dept)}</div></td>
      <td style="text-align:left;white-space:normal"><b>${esc(r.code)}</b> ${esc(r.task)}${demoTag(r)}<div class="muted small">${esc(r.type)}${r.bill ? " · " + esc(r.bill) : ""}</div></td>
      <td>${t(r.started_at)}</td><td>${t(r.done_at)}</td><td>${t(r.approved_at)}</td><td>${t(r.ended_at)}</td>
      <td><b>${live && r.running_since ? tick(r.day_seconds, d.server_now, "timer sm") : clock(r.day_seconds)}</b></td><td>${pill(r.status)}</td><td>${docsBtn("tr" + r.id, `${r.code} ${r.task} · ${r.person}`, r.docs)}</td></tr>`).join("");
  return hero("Tracker", `Time on every task, from Start to Done. ${L.enabled !== false ? `Lunch ${ampm(L.start)}–${ampm(L.end)} is not counted and is locked for staff.` : "Lunch lock is off."}`,
      `<div class="daypick"><input class="in" type="date" id="tDate" value="${esc(d.date)}" max="${today()}" style="width:auto"><a class="btn primary" href="${withT("/api/tracker/export?date=" + d.date)}" download>Export day (Excel)</a></div>`) +
    `<div class="pcards">${cards || `<div class="emptycard">Nobody has tracked time on ${esc(d.date)} yet.</div>`}</div>
    <div class="toolbar" style="margin-top:20px"><input class="search" id="tq" placeholder="Search person, task or department" aria-label="Search the tracker" value="${esc(S.tq || "")}">
      <label class="small" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="tAll" ${S.tAll ? "checked" : ""}> Include tasks with no time</label>${demoToggle()}</div>
    <div class="panel scroll"><table><thead><tr>${th("person", "Person", 1)}${th("task", "Task", 1)}${th("started", "Started")}${th("done", "Done")}${th("approved", "Approved")}${th("ended", "Ended")}${th("worked", "Worked")}${th("status", "Status")}<th>Docs</th></tr></thead>
      <tbody>${table || `<tr><td colspan="9" class="empty">${pq ? `Nothing matches “${esc(S.tq)}”.` : "No tracked tasks for this day."}</td></tr>`}</tbody></table></div>
    <h2>Lunch lock</h2><div class="panel"><div class="row2"><label class="small" style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="lOn" ${L.enabled !== false ? "checked" : ""} style="width:18px;height:18px;accent-color:#0071e3"> Lock the app and pause timers</label>
      from <input class="in" type="time" id="lFrom" value="${esc(L.start)}" style="flex:0 0 auto;width:auto;min-width:0"> to <input class="in" type="time" id="lTo" value="${esc(L.end)}" style="flex:0 0 auto;width:auto;min-width:0">
      <span style="flex:1"></span><button class="btn" id="lSave" type="button">Save lunch time</button></div>
      <p class="muted small" style="margin:10px 0 0">During lunch, staff see a lock screen and can't start, finish, upload or end tasks; admins can still work. A copy of each day's tracker is also saved in Storage → 01 Master Tracker → Daily Time Tracker.</p></div>`;
}
function wireTracker() {
  const dt = $("#tDate"); if (dt) dt.onchange = async () => { S.trDate = dt.value; try { S.tr = await api(trUrl()); } catch (e) { note("Couldn't load", e.message); } render(); };
  const tq = $("#tq"); if (tq) tq.oninput = () => { S.tq = tq.value; render(); };
  document.querySelectorAll("[data-sort]").forEach(b => b.onclick = () => { const k = b.dataset.sort, cur = S.trSort || {};
    S.trSort = { k, dir: cur.k === k ? -cur.dir : (k === "worked" ? -1 : 1) }; render(); });
  const ta = $("#tAll"); if (ta) ta.onchange = () => { S.tAll = ta.checked; render(); };
  $("#lSave").onclick = async () => { try { const r = await api("/api/lunch", { lunch: { enabled: $("#lOn").checked, start: $("#lFrom").value, end: $("#lTo").value } });
    S.meta.lunch = r.lunch; S.tr = await api(trUrl()); render(); note("Lunch time saved", `${ampm(r.lunch.start)}–${ampm(r.lunch.end)}${r.lunch.enabled ? "" : " (lock off)"}`, "approved"); } catch (e) { note("Couldn't save", e.message); } };
}
