// Login presentation and authenticated Admin management. Permissions stay on the server.
"use strict";
function employeeSection() {
  if (!isAdmin()) return "";
  const users = S.meta.users, departments = [...new Set(users.map(u => u.dept || "Other"))];
  return `<section class="card employee-section"><div class="admin-manager-head"><h2>EMPLOYEES</h2><div class="actions"><button class="btn primary" id="addEmployee" type="button">+ Add Employee</button><button class="btn" id="manageEmployees" type="button" aria-expanded="${!!S.manageEmployees}">Manage Employees</button></div></div><input class="search" id="employeeSearch" aria-label="Search employees" placeholder="Search employees" value="${esc(S.employeeSearch || '')}">${departments.map(d => `<div data-employee-dept><h3 class="dept">${esc(d)}</h3><div class="people">${users.filter(u => (u.dept || 'Other') === d).map(u => `<article class="person" data-employee-card data-search="${esc(`${u.name} ${u.dept} ${u.role}`.toLowerCase())}">${avatar(u.name)}<span><b>${esc(u.name)}</b><small>${esc(u.designation || u.role)}</small><small>${u.admin ? 'Admin' : 'Employee'}</small>${S.manageEmployees ? `<span class="actions"><button class="btn" type="button" data-edit-employee="${esc(u.name)}">Edit</button><button class="btn" type="button" data-delete-employee="${esc(u.name)}">Delete</button></span>` : ''}</span></article>`).join('')}</div></div>`).join('')}</section>`;
}
function wireEmployees() {
  if (!isAdmin()) return;
  const add = $('#addEmployee'), manage = $('#manageEmployees'), search = $('#employeeSearch');
  if (add) add.onclick = () => editEmployee();
  if (manage) manage.onclick = () => { S.manageEmployees = !S.manageEmployees; render(); };
  if (search) {
    const filter = () => {
      S.employeeSearch = search.value;
      document.querySelectorAll('[data-employee-card]').forEach(c => c.hidden = !c.dataset.search.includes(search.value.trim().toLowerCase()));
      document.querySelectorAll('[data-employee-dept]').forEach(d => d.hidden = ![...d.querySelectorAll('[data-employee-card]')].some(c => !c.hidden));
    };
    search.oninput = filter; filter();
  }
  document.querySelectorAll('[data-edit-employee]').forEach(b => b.onclick = () => editEmployee(S.meta.users.find(u => u.name === b.dataset.editEmployee)));
  document.querySelectorAll('[data-delete-employee]').forEach(b => b.onclick = () => {
    const u = S.meta.users.find(u => u.name === b.dataset.deleteEmployee);
    dialog(`<h3>Delete employee: ${esc(u.name)}?</h3><p>This removes the profile from active lists and sign-in. Tasks, time records, documents and history will be preserved. Existing assignments may need reassignment.</p>${u.admin ? '<label class="f">Your Admin PIN<input class="in" name="confirmation_pin" type="password" required autocomplete="current-password"></label>' : ''}`, fd => saveEmployee({action: 'delete', original: u.name, confirmed: true, confirmation_pin: fd.get('confirmation_pin')}));
  });
}
async function saveEmployee(body) {
  try {
    await api('/api/employees', body);
    S.meta = await api('/api/meta'); await load();
  } catch (e) { note('Employee change failed', e.message); }
}
function editEmployee(user) {
  if (!isAdmin()) return;
  const u = user || {};
  // Keep validation errors and entered values in the form until a successful save.
  const d = document.createElement('dialog'); d.id = 'employeeEditor'; d.className = 'admin-manager';
  d.innerHTML = `<form><h2>${user ? 'Edit Employee' : 'Add Employee'}</h2>${[['name','Name',u.name],['designation','Designation',u.designation || u.role],['dept','Department',u.dept]].map(([key,label,value]) => `<label class="f">${label}<input class="in" name="${key}" value="${esc(value || '')}" maxlength="120" required></label>`).join('')}<label class="f">Role<select class="in" name="access_role"><option value="employee">Employee</option><option value="admin" ${u.admin ? 'selected' : ''}>Admin</option></select></label><label class="f">Your Admin PIN (required when changing Admin access)<input class="in" name="confirmation_pin" type="password" autocomplete="current-password"></label><p role="alert" class="employee-error"></p><div class="actions"><button class="btn" type="button" data-cancel>Cancel</button><button class="btn primary" type="submit">Save Employee</button></div></form>`;
  document.body.append(d); d.onclose = () => d.remove(); d.querySelector('[data-cancel]').onclick = () => d.close();
  d.querySelector('form').onsubmit = async e => {
    e.preventDefault(); const button = d.querySelector('[type=submit]'); button.disabled = true;
    try {
      await api('/api/employees', {action: user ? 'edit' : 'add', original: u.name, ...Object.fromEntries(new FormData(e.target))});
      d.close(); S.meta = await api('/api/meta'); await load();
    } catch (error) { d.querySelector('.employee-error').textContent = error.message; }
    finally { button.disabled = false; }
  };
  d.showModal();
}
function loginProfiles() {
  const q = (S.uq || "").trim().toLowerCase();
  return S.meta.users.filter(u => !q || `${u.name} ${u.role || ""} ${u.dept || ""}`.toLowerCase().includes(q));
}
function loginPerson(u) {
  return `<button class="person" data-user="${esc(u.name)}" type="button">${avatar(u.name)}<span><b>${esc(u.name)}</b><small>${esc(u.role || "")}</small>${u.dept ? `<small>${esc(u.dept)}</small>` : ""}</span></button>`;
}
function loginGroupOpen(group) {
  return (S.uq || "").trim() ? loginProfiles().some(u => group === "admins" ? u.admin : !u.admin) : S.loginGroup === group;
}
function loginIcon(admin) {
  return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${admin ? '<path d="M12 3l8 3v5c0 5-8 10-8 10S4 16 4 11V6l8-3z"/><path d="M8 12l3 3 5-6"/>' : '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0112 0v3M17 5a3 3 0 010 6M18 15a5 5 0 013 4v2"/>'}</svg>`;
}
function loginMarkup() {
  const matches = loginProfiles(), searching = !!(S.uq || "").trim();
  const group = (id, title, icon) => {
    const users = matches.filter(u => id === "admins" ? u.admin : !u.admin), open = loginGroupOpen(id);
    const total = S.meta.users.filter(u => id === "admins" ? u.admin : !u.admin).length;
    const departments = [...new Set(users.map(u => u.dept || "Other"))];
    const list = id === "admins" ? `<div class="people">${users.map(loginPerson).join("")}</div>` : departments.map(d => `<h3 class="dept">${esc(d)}</h3><div class="people">${users.filter(u => (u.dept || "Other") === d).map(loginPerson).join("")}</div>`).join("");
    return `<section class="login-group ${open ? "is-open" : ""}" data-login-group="${id}"><button class="login-group-toggle" type="button" data-login-toggle="${id}" aria-expanded="${open}" aria-controls="login-${id}"><span class="login-group-icon" aria-hidden="true">${icon}</span><b>${title}</b><span class="login-count">${searching ? `${users.length} / ` : ""}${total}</span><span class="login-chevron" aria-hidden="true">&#9662;</span></button><div class="login-group-body" id="login-${id}" ${open ? "" : "inert"}><div><div class="login-group-content">${list || `<p class="muted small">No matching profiles.</p>`}</div></div></div></section>`;
  };
  return `<div class="login login-new ${S.introStarted && !S.introDone ? "intro-login" : ""}"><div class="login-theme-bar">${Theme.button()}</div><div class="logo mark">S</div><h1>${APP}</h1><div class="ver">${APP_VERSION}</div><input class="search" id="uq" placeholder="Type your name" value="${esc(S.uq || "")}" aria-label="Find your name" autocomplete="off"><div class="login-groups">${group("admins", "ADMIN", loginIcon(true))}${group("employees", "EMPLOYEES", loginIcon(false))}</div>${searching && !matches.length ? `<p class="muted" role="status">No matching users.</p>` : ""}</div>`;
}
function syncLoginGroups() {
  document.querySelectorAll("[data-login-group]").forEach(group => {
    const open = loginGroupOpen(group.dataset.loginGroup);
    group.classList.toggle("is-open", open); group.querySelector("button").setAttribute("aria-expanded", String(open)); group.querySelector(".login-group-body").inert = !open;
  });
}
function wireLogin() {
  const intro = $("#brandIntro"), heading = $(".login-new h1");
  if (intro && heading) {
    const range = document.createRange(); range.selectNodeContents(heading);
    const target = range.getBoundingClientRect();
    intro.style.setProperty("--brand-end-x", `${target.left + target.width / 2 - innerWidth / 2}px`);
    intro.style.setProperty("--brand-end-y", `${target.top + target.height / 2 - innerHeight / 2}px`);
  }
  const uq = $("#uq");
  uq.oninput = () => {
    S.uq = uq.value; S.loginGroup = null; const position = uq.selectionStart; render();
    const input = $("#uq"); input.focus(); input.setSelectionRange(position, position);
  };
  uq.onkeydown = e => { if (e.key === "Enter") $("#app [data-user]")?.click(); };
  document.querySelectorAll("[data-login-toggle]").forEach(button => button.onclick = () => {
    // Search reveals both matching groups; returning to browsing restores the accordion.
    if ((S.uq || "").trim()) { S.uq = ""; S.loginGroup = button.dataset.loginToggle; render(); return; }
    S.loginGroup = S.loginGroup === button.dataset.loginToggle ? null : button.dataset.loginToggle; syncLoginGroups();
  });
  document.querySelectorAll("[data-user]").forEach(button => button.onclick = () => { unlockAudio(); signIn(button.dataset.user); });
}

let introTimeout, introClock;
function finishBrandIntro() {
  clearTimeout(introTimeout); clearInterval(introClock); S.introDone = true;
  $("#brandIntro")?.remove(); document.querySelector(".intro-login")?.classList.remove("intro-login");
}
function startBrandIntro() {
  if (S.introStarted) return;
  S.introStarted = true;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { S.introDone = true; return; }
  const intro = document.createElement("div"); intro.id = "brandIntro"; intro.className = "brand-intro";
  intro.setAttribute("aria-label", "SOMESH ENTERPRISES introduction");
  intro.innerHTML = `<div class="intro-word" aria-hidden="true"><span class="intro-s">S</span><span class="intro-rest">${[..."OMESH ENTERPRISES"].map((letter, i) => `<span style="--letter:${i}">${letter === " " ? "&nbsp;" : letter}</span>`).join("")}</span></div><button class="btn ghost" type="button" id="skipIntro">Skip Intro</button>`;
  document.body.append(intro);
  intro.style.setProperty("--brand-rest-width", `${intro.querySelector(".intro-rest").scrollWidth}px`);
  intro.style.setProperty("--s-zoom", String(Math.min(32, Math.max(innerWidth, innerHeight) * .8 / parseFloat(getComputedStyle(intro.querySelector(".intro-s")).fontSize))));
  $("#skipIntro").onclick = finishBrandIntro;
  // Keep the short presentation on wall time when background/slow frames stall the CSS timeline.
  const began = performance.now();
  if (intro.getAnimations) introClock = setInterval(() => {
    try {
      const elapsed = performance.now() - began;
      const elements = [intro, document.querySelector(".intro-login")].filter(Boolean);
      elements.forEach(element => element.getAnimations({ subtree: true }).forEach(animation => {
        if (/^(brand-|login-rise$)/.test(animation.animationName || "")) animation.currentTime = elapsed;
      }));
    } catch (e) { clearInterval(introClock); }
  }, 50);
  introTimeout = setTimeout(finishBrandIntro, 3200);
  intro.addEventListener("animationend", e => { if (e.animationName === "brand-intro-away") finishBrandIntro(); });
}

function closeAdminManagement() { const modal = $("#adminManager"); if (modal) { modal.close(); modal.remove(); } }
async function openAdminManagement() {
  if (!isAdmin()) return;
  closeAdminManagement();
  const modal = document.createElement("dialog"); modal.id = "adminManager"; modal.className = "admin-manager"; modal.setAttribute("aria-labelledby", "adminManagerTitle");
  modal.innerHTML = `<div class="admin-manager-head"><div><h2 id="adminManagerTitle">Manage Admins</h2><p class="muted small">Change access without changing employee profiles or tasks.</p></div><button class="btn" id="adminManagerClose" type="button" aria-label="Close Admin management">&#10005;</button></div><label class="admin-search-label">Search employees<input class="search" id="adminSearch" placeholder="Name or department" autocomplete="off"></label><div id="adminManagerError" role="alert"></div><div id="adminManagerRows" aria-live="polite">Loading users...</div>`;
  document.body.append(modal); modal.querySelector("#adminManagerClose").onclick = closeAdminManagement;
  modal.onclose = () => modal.remove(); modal.onkeydown = e => { if (e.key === "Escape") e.stopPropagation(); };
  modal.onclick = e => { const r = modal.getBoundingClientRect(); if (e.target === modal && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) closeAdminManagement(); };
  modal.querySelector("#adminSearch").oninput = () => drawAdminManagement(); modal.showModal();
  try { S.adminManagement = await api("/api/admins"); drawAdminManagement(); }
  catch (e) { if ($("#adminManagerError")) $("#adminManagerError").textContent = e.message; }
}
function drawAdminManagement() {
  const area = $("#adminManagerRows"), data = S.adminManagement; if (!area || !data) return;
  const q = ($("#adminSearch")?.value || "").trim().toLowerCase();
  const users = data.users.filter(u => `${u.name} ${u.dept || ""} ${u.role || ""}`.toLowerCase().includes(q));
  area.innerHTML = `<div class="scroll"><table><thead><tr><th>Employee</th><th>Department</th><th>Current Role</th><th>Action</th></tr></thead><tbody>${users.map(u => `<tr><td><div class="admin-person">${avatar(u.name)}<span><b>${esc(u.name)}</b><small>${esc(u.role || "")}</small></span></div></td><td>${esc(u.dept || "–")}</td><td>${u.admin ? "Admin" : "Employee"}</td><td><button type="button" class="btn" data-admin-user="${esc(u.name)}" ${u.admin && data.admin_count <= 1 ? 'disabled title="The last Admin cannot be removed"' : ""}>${u.admin ? "Revoke Admin" : "Make Admin"}</button></td></tr>`).join("") || `<tr><td colspan="4" class="empty">No matching employees.</td></tr>`}</tbody></table></div><p class="muted small">Role changes require your Admin PIN. Affected sessions are signed out. Promoted users use their configured Admin PIN; existing credentials are unchanged.</p><details class="admin-audit"><summary>Recent access changes</summary>${data.audit.map(event => `<p class="small"><b>${esc(event.ts)}</b> ${esc(event.text)}</p>`).join("") || `<p class="muted small">No access changes yet.</p>`}</details>`;
  area.querySelectorAll("[data-admin-user]").forEach(button => button.onclick = () => confirmAdminChange(button.dataset.adminUser));
}
function confirmAdminChange(name) {
  const user = S.adminManagement.users.find(u => u.name === name); if (!user || !isAdmin()) return;
  const enabled = !user.admin;
  dialog(`<h3>${enabled ? "Make Admin" : "Revoke Admin"}: ${esc(name)}?</h3><p class="muted">${enabled ? "This employee will gain access to Admin pages and management controls." : "This employee will return to regular employee access."} Existing tasks, documents and profile details stay intact. Their current sessions will be signed out.</p><label class="admin-confirm-pin">Your Admin PIN<input class="in" name="confirmation_pin" type="password" autocomplete="current-password" aria-label="Confirm with your Admin PIN" required></label>`, async form => {
    const error = $("#adminManagerError"); if (error) error.textContent = "";
    try {
      S.adminManagement = await api("/api/admins/role", { user: name, admin: enabled, confirmation_pin: form.get("confirmation_pin") });
      S.meta = await api("/api/meta");
      if (!isAdmin()) { logout(true); return; }
      drawAdminManagement(); render();
    } catch (e) { if ($("#adminManagerError")) $("#adminManagerError").textContent = e.message; }
  });
}
