# Dark/light theme verification — 2026-11-10

## Result

Added an accessible Sun/Moon toggle to the login screen and the shared Admin/Employee header. Switching updates the root theme immediately without rebuilding the page, closing panels or losing drafts. Preferences are stored separately for each profile in this browser; the login screen has its own preference. Without a saved choice, the system preference is used. Explicit choices override the system setting, including after refresh. Same-profile browser tabs synchronize through storage events. If storage is blocked, the toggle still works for the current page.

`frontend/js/core/theme.js` runs before styles load to apply saved settings early. `frontend/css/theme.css` centralizes light/dark surfaces, foregrounds, muted text, accents, button fills, focus, selected/disabled states, alert cards and white paper colors.

## Verified fixes

- Dynamic Island cards no longer force white backgrounds while inheriting dark-mode light text. Cards, titles, excerpts, task details, timestamps, expanded histories and controls now use paired surface/foreground tokens.
- Open Task, Mark Read and View All Alerts have readable normal/hover/focus/disabled states. The island itself retains its black appearance. Dragging, expansion, delayed dismissal and task navigation remain intact.
- Login headings, accordion groups, department icons/counts and the intro use theme variables instead of fixed light colors.
- Inputs, search fields, placeholders, native select/option colors, badges, tables, menus, sheets and dialogs use consistent foregrounds and surfaces. Accent text colors are separate from filled-button colors so dark-mode pale blue/green does not appear behind white button text.
- Live task banners, timetable status pills, lunch and connection overlays and navigation states retain readable paired colors.
- Avatar initials choose dark/light ink for their existing background color. Automation diagram avatars, department labels, numbered rule-builder badges and the Employee alert counter were corrected.
- Excel editors follow the chosen theme. Word paper previews and print styles intentionally retain white paper with dark text, even when the surrounding app is dark.

## Executed tests

| Test | Result |
|---|---|
| `python -m unittest discover -s tests -v` with private reference files | **PASS: 61 tests, zero failures/skips**. Includes backend/API, data preservation, Excel/PDF/DOCX, roles and both actual BAT startup paths. |
| `python tests/run_browser.py --themes` | **PASS: 75 screen states, 6,271 rendered solid-color text checks, zero final contrast findings**. Both themes, keyboard toggle, system default/explicit override, profile isolation, refresh/login/logout, cross-tab updates, storage restrictions, drafts, print, no JavaScript/console errors, no failed static assets or HTTP 5xx responses. |
| Core Chrome suite, `TEST_THEME=light` and `TEST_THEME=dark` | **PASS in both themes**. Login, navigation, Tracker cards/hover, sorting/search, timers, downloads, Dynamic Island hover/click/drag/touch/expand/read/task/view-all, persistence and 390px layout. |
| Action Center Chrome suite, both `TEST_THEME` values | **PASS in both themes**. Counters, filters, review/reassign dialogs, exports, Tracker, mobile and permissions. |
| Excel/Word Chrome suite with real private references, both `TEST_THEME` values | **PASS in both themes**. All four eligible employee profiles, previews, editing, formulas, undo/redo, saving, filenames, uploads, new tabs, downloads/reopening, search, 10,000-row pagination and mobile bounds. |
| Employee CRUD Chrome suite | **PASS**. Add/edit/delete, duplicate validation, confirmation/cancel, refresh persistence, actual theme button, mobile and employee API denial. |
| `node --check` for frontend/test/tool JS/CJS | **PASS** |
| Python `compileall`, `git diff --check` | **PASS** |
| Live `node tools/audit_live.cjs` after BAT restart | **PASS**. Actual localhost Admin/Employee sign-in/navigation/forms, theme switching, mobile bounds, refresh, authorization, no page exceptions/HTTP 5xx, no business mutations. |
| Actual project BAT restart and second invocation | **PASS**. Chrome opened at `http://localhost:8080`; frontend and API served successfully. Second invocation safely reused the running instance. Both BAT files were inspected; no launcher code change was necessary for these static assets. |

The initial contrast scan exposed low-contrast dark Automation number badges and the light Employee alert count. Both were fixed and the full theme scan rerun. Test harness updates account for native-modal focus blocking, asynchronous system preference events, post-drag click suppression and recent-alert reordering after Mark Read; the actual existing interactions were retained.

## Screen coverage

Both themes were exercised for login and PIN dialog; Admin Dashboard and employee cards; My Tasks and To Check; Tracker and employee details; Overview; Action Center; Pipeline; Activity; Alerts and expanded task details; Assign Tasks; Automation, stage details and rule builder; New Bill; Workflow Input; Walkthrough; Storage; Excel Workspace with NEFT, worksheet and covering letter previews; Admin management and access confirmation; Employee add/edit/delete dialogs; export menu; lunch overlay; mobile Dashboard/Island; Employee tasks/help/alerts; Employee Excel workspace; and print styling.

Document filename/upload interactions, task review/reassignment and exports also ran through the existing browser suites in both themes. Theme changes were checked against open employee forms and New Bill drafts without losing entered text.

## Screenshots and evidence

**91 PNG captures** remain in the ignored local folder `data/theme-audit/`:

- 8 before captures of login, Dashboard, Island and Alerts in both themes, using the original tracked frontend against isolated synthetic data.
- 75 after captures corresponding to the theme audit states.
- 8 additional after comparison captures at the same login/Dashboard/Island/Alerts setup as the before images.

Open `data/theme-audit/index.html` for the side-by-side gallery and full-resolution links. `contrast-results.json` contains the screen-by-screen measurements. In particular, compare `before-dark-island.png` with `comparison-after-dark-island.png`; the original invisible white-card text is clearly reproduced and corrected. No user screenshot attachments were available in this turn, so these captures establish the before/after evidence.

An online SQLite backup was taken before the live restart. Every original non-session row matched after restart and live checks, and `PRAGMA integrity_check` returned `ok`. Screenshots, backup and measurements stay local and are not added to source control.

## Practical limits

- Chrome on Windows and desktop/390px mobile emulation were executed. Other browsers, physical mobile devices and operating systems were not executed.
- The contrast check applies the AA text thresholds of 4.5:1 (normal) and 3:1 (large) to sampled rendered solid-color text. SVG/gradient/image content and OS-native popup/download UI are not exhaustively measured by this checker. Critical Island and light/dark screenshots were also visually reviewed. This is not a formal full WCAG conformance certification.
- This plain HTML/CSS/JavaScript app has no frontend build or configured lint pipeline. Syntax and behavioral checks above were executed instead; no npm build/lint result is claimed.
- Preferences persist per profile on the current browser; no cross-device preference service was introduced. When browser storage is unavailable, persistence cannot be guaranteed, although switching remains functional.

Release verification also checks every avatar palette color. The purple background exposed a 4.33:1 edge case with near-black ink; using black for the dark-ink fallback brings every palette color above 4.5:1. This palette regression is included in the theme browser suite.
