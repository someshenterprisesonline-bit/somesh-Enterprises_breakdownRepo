// Pipeline: repeatable-task bar, drag-and-drop assigning, Edit list.
"use strict";
// ---------------------------------------------------------- v2: drag-and-drop task templates on the Pipeline
function viewPalette() {
  const list = S.tpls || [];
  const chips = list.map((t, i) => `<button type="button" class="tpl ${S.selTpl === i ? "sel" : ""}" draggable="true" data-tpl="${i}" aria-pressed="${S.selTpl === i}">
      <span class="grip" aria-hidden="true">⋮⋮</span>${esc(t.name)}<span class="muted small">${t.hours} h</span>${t.docs ? `<span class="docmark" title="Needs documents">📄</span>` : ""}</button>`).join("");
  return `<div class="panel palette"><div class="row2" style="margin-bottom:10px"><b>Repeatable tasks</b><span class="muted small">Drag one onto a person below to give it to them${S.selTpl != null ? " · or click a person's name to give the selected one" : " · or click one, then click a person"}</span><span style="flex:1"></span><button class="btn" type="button" id="tplEdit">Edit list</button></div>
    <div class="tpls">${chips || `<span class="muted small">No repeatable tasks yet. Use Edit list to add some.</span>`}</div></div>`;
}
function tplTip(el) {
  const t = (S.tpls || [])[Number(el.dataset.tpl)]; if (!t) return;
  let pop = $("#ttPop"); if (!pop) { pop = document.createElement("div"); pop.id = "ttPop"; pop.setAttribute("role", "tooltip"); document.body.appendChild(pop); }
  pop.innerHTML = `<div class="hd"><span class="pill p-assigned">Repeatable task</span></div><div style="font-weight:700;font-size:15px">${esc(t.name)}</div>
    ${t.about ? `<div class="small" style="margin-top:4px">${esc(t.about)}</div>` : ""}
    <dl><dt>Time limit</dt><dd>${t.hours} h</dd><dt>Documents</dt><dd>${t.docs ? "Needed after approval" : "Not needed"}</dd><dt>Approver</dt><dd>${esc(S.user)}</dd></dl>
    <div class="muted small" style="margin-top:8px">Drag onto anyone, in any department</div>`;
  const r = el.getBoundingClientRect(); pop.classList.add("show");
  const w = pop.offsetWidth, h = pop.offsetHeight;
  pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  pop.style.top = (r.bottom + 10 + h < window.innerHeight ? r.bottom + 10 : Math.max(8, r.top - h - 10)) + "px";
}
function giveTemplate(i, person) {
  const t = (S.tpls || [])[i]; if (!t) return;
  const u = S.meta.users.find(x => x.name === person) || {};
  dialog(`<h3 style="margin:0 0 4px">Give “${esc(t.name)}”</h3><p class="muted small" style="margin:6px 0;display:flex;gap:8px;align-items:center">${avatar(person)}<span><b>${esc(person)}</b> · ${esc(u.dept || "")}. They get the double beep straight away.</span></p>
    ${t.about ? `<p class="small" style="margin:0 0 8px">${esc(t.about)}</p>` : ""}
    <div class="row2"><span style="flex:1"><label class="f" for="gH">Time limit (hours)</label><input class="in" id="gH" name="hours" type="number" min="0.25" step="0.25" value="${t.hours}"></span>
      <span style="flex:2"><label class="f" for="gC">Approver</label><select class="in" id="gC" name="checker">${S.meta.users.map(x => `<option ${x.name === S.user ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></span></div>
    <label class="small" style="display:flex;gap:8px;align-items:center;margin-top:12px"><input type="checkbox" name="docs" ${t.docs ? "checked" : ""} style="accent-color:#0071e3"> Needs documents after approval</label>
    <label class="f" for="gN">Note for ${esc(person.split(" ").pop())} (optional)</label><input class="in" id="gN" name="output" placeholder="${esc(t.about || "")}">`,
    async (fd) => {
      try { const r = await api("/api/assign", { tasks: [{ title: t.name, who: person, checker: fd.get("checker"), hours: fd.get("hours"), docs: fd.get("docs") === "on", output: fd.get("output") || t.about || "" }] });
        note("Task given", `${r.codes[0]} ${t.name} → ${person}`, "approved"); S.selTpl = null; S.tt = await api(ttUrl()); render(); }
      catch (e) { note("Couldn't give the task", e.message); }
    });
}
function editTemplates() {
  const rows = (S.tpls || []).concat([{ name: "", hours: 1, docs: false, about: "" }]);
  const row = (t) => `<div class="tplrow"><input class="in" data-k="name" placeholder="Task name" value="${esc(t.name)}"><input class="in" data-k="hours" type="number" min="0.25" step="0.25" value="${t.hours}" title="Hours">
    <label class="small" title="Needs documents"><input type="checkbox" data-k="docs" ${t.docs ? "checked" : ""} style="accent-color:#0071e3"> Docs</label>
    <input class="in" data-k="about" placeholder="What it involves (shown in the popup)" value="${esc(t.about || "")}" style="grid-column:1/-1"></div>`;
  sheetHtml(`<h2 style="margin:0 0 4px">Repeatable tasks</h2><p class="muted small">Tasks anyone can do, in any department. They appear above the Pipeline timetable for drag and drop. Clear a name to remove that task.</p>
    <div id="tplRows">${rows.map(row).join("")}</div><div class="row2" style="margin-top:12px"><button class="btn" type="button" id="tplAdd">＋ Add another</button><span style="flex:1"></span><button class="btn primary" type="button" id="tplSave">Save list</button></div>`);
  $("#tplAdd").onclick = () => $("#tplRows").insertAdjacentHTML("beforeend", row({ name: "", hours: 1, docs: false, about: "" }));
  $("#tplSave").onclick = async () => {
    const templates = [...document.querySelectorAll("#tplRows .tplrow")].map(r => Object.fromEntries([...r.querySelectorAll("[data-k]")].map(e => [e.dataset.k, e.type === "checkbox" ? e.checked : e.value.trim()]))).filter(t => t.name);
    try { const r = await api("/api/templates", { templates }); S.tpls = r.templates; closeSheet(); render(); note("Saved", `${r.templates.length} repeatable tasks`, "approved"); } catch (e) { note("Couldn't save", e.message); }
  };
}
function wirePalette() {
  const app = $("#app");
  app.querySelectorAll("[data-tpl]").forEach(el => {
    el.onmouseenter = el.onfocus = () => tplTip(el); el.onmouseleave = el.onblur = hideTip;
    el.ondragstart = (e) => { hideTip(); e.dataTransfer.setData("text/plain", "tpl:" + el.dataset.tpl); e.dataTransfer.effectAllowed = "copy"; document.body.classList.add("dragging"); };
    el.ondragend = () => { document.body.classList.remove("dragging"); app.querySelectorAll(".tt-row.drop").forEach(r => r.classList.remove("drop")); };
    el.onclick = () => { const i = Number(el.dataset.tpl); S.selTpl = S.selTpl === i ? null : i; render(); };
  });
  app.querySelectorAll(".tt-row[data-person]").forEach(row => {
    row.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; row.classList.add("drop"); };
    row.ondragleave = (e) => { if (!row.contains(e.relatedTarget)) row.classList.remove("drop"); };
    row.ondrop = (e) => { e.preventDefault(); row.classList.remove("drop"); document.body.classList.remove("dragging");
      const v = e.dataTransfer.getData("text/plain"); if (v.startsWith("tpl:")) giveTemplate(Number(v.slice(4)), row.dataset.person); };
    const who = row.querySelector(".tt-who"); if (who) who.onclick = () => { if (S.selTpl != null) giveTemplate(S.selTpl, row.dataset.person); };
  });
  const ed = $("#tplEdit"); if (ed) ed.onclick = editTemplates;
  app.querySelectorAll("[data-task]").forEach(b => b.onclick = () => openTask(Number(b.dataset.task)));
}
