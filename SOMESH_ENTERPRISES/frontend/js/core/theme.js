// Applied before CSS loads; preferences are private to each profile on this browser.
"use strict";
const Theme = (() => {
  const read = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const valid = value => value === "light" || value === "dark";
  const key = user => user ? "se_theme_user_" + encodeURIComponent(user) : "se_theme_guest";
  const system = matchMedia("(prefers-color-scheme: dark)");
  let owner = read("se_token") ? read("se_user") || null : null;
  const preferred = () => {
    const saved = read(key(owner)), guest = read(key(null));
    return valid(saved) ? saved : valid(guest) ? guest : system.matches ? "dark" : "light";
  };
  const icon = mode => mode === "dark"
    ? '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z"/></svg>'
    : '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>';
  function update() {
    const mode = document.documentElement.dataset.theme;
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      const label = "Switch to " + (mode === "dark" ? "light" : "dark") + " mode";
      button.setAttribute("aria-label", label); button.title = label;
      button.setAttribute("aria-pressed", String(mode === "dark"));
      button.querySelector(".theme-icon").innerHTML = icon(mode);
      button.querySelector(".theme-label").textContent = mode === "dark" ? "Dark" : "Light";
    });
  }
  function apply(mode) {
    document.documentElement.dataset.theme = mode;
    update();
  }
  function set(mode) {
    if (!valid(mode)) return;
    write(key(owner), mode); apply(mode);
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: mode } }));
  }
  function syncUser(user) {
    user = user || null;
    if (user !== owner) { owner = user; apply(preferred()); }
    else update();
  }
  function button() {
    const mode = document.documentElement.dataset.theme;
    return `<button class="btn theme-toggle" type="button" data-theme-toggle aria-label="Switch to ${mode === 'dark' ? 'light' : 'dark'} mode" aria-pressed="${mode === 'dark'}"><span class="theme-icon">${icon(mode)}</span><span class="theme-label">${mode === 'dark' ? 'Dark' : 'Light'}</span></button>`;
  }
  document.addEventListener("click", event => {
    if (event.target.closest("[data-theme-toggle]")) set(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
  window.addEventListener("storage", event => { if (event.key === key(owner) || event.key === key(null)) apply(preferred()); });
  system.addEventListener("change", () => apply(preferred()));
  apply(preferred());
  return {set, syncUser, button};
})();
