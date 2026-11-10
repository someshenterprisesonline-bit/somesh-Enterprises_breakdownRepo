# Code map: which code is responsible for which page

Use this when giving out tasks. Each row is one page. **Frontend** draws it, and **Backend** supplies or changes its data.
Two people can work at the same time without clashing when they work in different rows. Shared files are marked ⚠. Tell each other before changing them.

Frontend paths are under `frontend/`. Backend functions are in `backend/app.py` unless another file is named. To find something, search the file for the function name (Ctrl+F). Line numbers change, so they're not listed here.

## Pages

| Page (tab) | Who sees it | Frontend file | Frontend functions | Backend routes | Backend functions |
|---|---|---|---|---|---|
| **Sign-in screen** | everyone | `js/core/shell.js`, `js/core/login-and-admins.js` | `loginMarkup`, `wireLogin`, `startBrandIntro`, `signIn`, `finishSignIn`, `logout` | `POST /api/login`, `/api/logout`, `GET /api/me`, `/api/meta` | `verify_admin_pin`, `new_session`, `session_user` |
| **My tasks** | everyone | `js/pages/my-tasks.js` | `viewMine` | `GET /api/state` | `state`, `task_view` |
| **To check** | approvers, admins | `js/pages/my-tasks.js` | `viewCheck` | `GET /api/state` | `state` |
| Task buttons on the cards (Start, Done, Approve, Send back, End, attach files) | everyone | `js/core/actions.js`, `js/core/components.js` | `act`, `dialog`, `taskCard`, `attachFiles` | `POST /api/tasks/<id>/claim, submit, approve, reject, end, upload, unupload` | `claim`, `submit`, `approve`, `reject`, `end_task`, `save_upload`, `timer_start`, `timer_stop` |
| **Tracker** | admins | `js/pages/tracker.js` | `viewTracker`, `wireTracker`, `trShowPreview`, `trOpenEmployee`, `trWireTaskDisclosure`, `trDownload` | `GET /api/tracker`, `/api/tracker/export`, `/api/tracker/export.pdf`, `POST /api/lunch` | `tracker`, `tracker_xlsx`, `tracker_export.tracker_pdf`, `lunch_cfg` |
| **Overview** | admins | `js/pages/overview.js` | `viewOverview` | `GET /api/pipeline` | `pipeline` |
| **Dashboard** | admins | `js/pages/dashboard.js` | `viewDash`, `chartDaily`, `chartHeat`, `chartUtil`, `chartIdle`, `chartGap`, `gapTable`, `chartDept`, `chartTop`, `dashCsv`, `wireDash` | `GET /api/dashboard` | `dashboard`, `workday_cfg`, `available_seconds` |
| **Action Center** | admins | `js/pages/action-center.js` | `viewActionCenter`, `wireActionCenter`, `sacLoad`, `sacOpenTask`, `sacOpenTracker` | `GET /api/action-center`, `/api/action-center/task/<id>`, `/api/action-center/export.xlsx`, `/api/action-center/export.pdf`; `POST /api/action-center/reassign` | `action_center_report`, `action_center_reassign`; `action_center.build_report`, `action_center.export_report` |
| **Pipeline → Timetable** | admins | `js/pages/pipeline.js` | `viewPipe`, `viewTimetable`, `showTip`, `lanesOf` | `GET /api/timetable` | `timetable` |
| **Pipeline → Bills × stages** | admins | `js/pages/pipeline.js` | `viewBills`, `billProgress`, `exportCsv` | `GET /api/pipeline` | `pipeline` |
| **Pipeline → drag-and-drop repeatable tasks** | admins | `js/pages/pipeline-dragdrop.js` | `viewPalette`, `tplTip`, `giveTemplate`, `editTemplates`, `wirePalette` | `GET/POST /api/templates`, `POST /api/assign` | `templates`, `create_adhoc` (list in `config.json` → `task_templates`) |
| **Activity** | admins | `js/pages/activity-alerts.js` | `viewLog` | `GET /api/pipeline` (events) | `log` |
| **Alerts** (and the 🔔 bell) | everyone | `js/pages/activity-alerts.js`, bell in `js/core/shell.js` | `viewAlerts` | `GET /api/state`, `POST /api/alerts/read` | `alert`, `send_email`, `send_ntfy`, `send_webhooks` |
| **Assign tasks** | admins | `js/pages/assign-tasks.js` | `viewAssign`, `asgRow`, `wireAssign` | `GET /api/adhoc`, `POST /api/assign` | `create_adhoc`, `adhoc_busy` |
| Admin task panel (click a task block or row: details, documents, Delete) | admins | `js/pages/task-panel.js` | `openTask`, `deleteTask`, `deleteBill`, `downloadDocs`, `fileCopy` | `POST /api/admin-task/<id>/delete`, `/api/admin-task/<id>/file`, `/api/bill/<id>/delete` | `delete_task`, `delete_bill`, `file_task_docs` |
| **Automation** | admins | `js/pages/automation.js` | `viewAuto`, `wireAuto` | `GET/POST /api/automation`, `POST /api/automation/open-now` | `auto_cfg`, `auto_start`, `automation_loop`, `open_bills_for_contracts`, `remind_loop_once` |
| **Walkthrough** (optional tab; also the "?" guide for staff) | everyone | `js/pages/walkthrough.js` | `viewGuide` | `GET /api/meta` | (none) |
| **Storage** (optional for admins; always shown to Data Center) | admins, Data Center | `js/pages/storage.js` | `viewStore`, `wireStore` | `GET /api/storage`, `POST /api/storage/sync`, `GET /files/...` | `storage_sync`, `storage_archive`, `storage_contract_check`; **`backend/storage.py`** builds the Excel files and folders |
| **New bill** + demo controls (optional tab) | admins | `js/pages/new-bill-demo.js` | `viewAdmin`, `wireAdmin` | `POST /api/bills`, `/api/demo/reset`, `/api/demo/simulate`, `/api/demo/clear` | `new_bill`, `create_task`, `load_demo`, `_build_demo`, `_demo_history`, `simulate_step`, `clear_demo` |
| **Workflow input** (optional tab) | admins | `js/pages/workflow-input.js` | `viewInput`, `wireInput`, `resultHtml` | `GET /api/workflow`, `/api/workflow/template`, `POST /api/workflow/upload`, `/api/workflow/load` | `process_input`, `apply_definitions`, `fetch_location`, `input_loop`; **`backend/workflow_input.py`** (`parse`, `build`) |
| Bill detail panel (click a bill ID anywhere) | admins | `js/core/components.js` | `loadBill`, `drawSheet`, `sheetHtml`, `closeSheet` | `GET /api/bill?id=` | `bill_detail` |
| Documents panel, file preview | admins | `js/core/components.js` | `showDocs`, `fileList`, `docsBtn`, `showPreview` | `GET /files/...`, `/api/preview` | `preview`, `task_files` |
| Optional-tab menu (the ＋ button) | admins | `js/core/shell.js` | `tabMenu`, `OPTIONAL_TABS`, `shownTabs` | (none; remembered in the browser) | (none) |
| Lunch lock screen | staff | `index.html` (`#lunch`), `js/core/utils.js` | `lunchWin`, `lunchNow`, `ticker` | `POST /api/tasks/...` refused at lunch | `is_lunch`, `lunch_window` |
| Automation **rules** (When → If → Then; backend only so far) | admins | (UI comes in part 2) | | `GET /api/rules`, `POST /api/rules`, `POST /api/rules/<id>/toggle`, `/delete`, `/test`, `GET /api/rules/log?limit=50`, `GET /api/workflow-model` | see **Automation rules** below |

## Automation rules (backend/app.py)

Admins make rules: **When** something happens (a trigger), **If** the conditions match, **Then** do one or more actions in order.

- **Tables:** `rules` (`trigger`, `conditions` JSON with the trigger's own value under `when`, `actions` JSON, `enabled`) and `rule_runs` (one row per firing or error). Both are in `SCHEMA`, so old databases upgrade by themselves. `seed_rules` adds 3 example rules, switched **off**, the first time the `rules` table is created.
- **Lists of choices:** `TRIGGERS`, `CONDITIONS`, `ACTIONS` and `PLACEHOLDERS` (`{task} {person} {bill} {client} {dept} {minutes}`).
- **Engine:** `fire_rules(trigger, task=None, bill_id=None, extra=None)` is called by `create_task` and `create_adhoc` (assigned, and started if Auto-start started it), `claim`, `submit`, `approve` (including bill complete), `reject`, `end_task` and `new_bill`. `rules_tick` checks the time-based triggers (`task_overdue`, `task_not_started`, `daily_at`) from `automation_loop` every 30 s.
- **Helpers:** `rule_ctx` collects the facts, `rule_matches` checks the If part, `run_action` does one Then step, and `rule_move` / `least_busy` hand a task to someone else. `auto_start(tid, force=True)` starts a task even when the Auto-start setting is off.
- **Safety:**
  - Each rule runs inside `try`, so a broken rule only writes an `error` row in `rule_runs`.
  - A rule fires at most once per task (or per bill, or per day for `daily_at`).
  - Actions done by a rule never fire rules again (`RULE_CTX.on`).
  - Demo bills are skipped unless the rule has `include_demo`.
  - Every firing writes a `rule_runs` row and an Activity event "Rule '…' …".
- **API helpers:** `validate_rule` and `save_rule` (clear `FlowError` messages), `rule_test` (dry run over the last 7 days; it changes nothing), `rules_meta` (everything a rule editor needs) and `workflow_model` (stages, live counts, and the rules that apply to each stage).
- `wipe_all` (used by `--demo`) clears `rule_runs`, because task IDs start again from 1. The rules themselves stay.

## Shared files ⚠ (talk before changing)

| File | What's in it | Why it's shared |
|---|---|---|
| `frontend/js/core/shell.js` | `render()`: the header, the tab list, and which view function each tab calls (`{ mine: viewMine, dash: viewDash, … }`). It also wires up each page's buttons. | Adding a **new page** means adding one line here. Keep these edits small. |
| `frontend/js/core/live-and-load.js` | `load()`: which `/api/...` each tab fetches | A new page that needs new data adds one line here. |
| `frontend/js/core/state-and-api.js` | `S` (all page state), `api()`, toasts, beep | Used by everything |
| `frontend/js/core/utils.js` | date and time helpers, `fileUrl`, `today`, `trUrl`, `ttUrl` | Used by everything |
| `frontend/css/app.css` | all styles. Sections are in this order: base, components, timetable, sheet, then v2 (buttons, palette, dashboard). | Add new styles at the **end** under a comment with your page name, so merges don't clash. |
| `frontend/index.html` | page skeleton + the `<script>` list | A new JS file must be added to the list **before** `js/core/actions.js`, and `main.js` must stay last. |
| `backend/app.py` → `class H` (`get` / `post`) | all API routes in one place. `do_GET`/`do_POST` first run `guard()` (office-network allowlist, optional HTTP→HTTPS redirect, same-origin POSTs); `do_POST` then calls `post()` and, only if the response was 200, sends Excel `excel_changed` notices and admin refreshes for `ADMIN_SYNC_PATHS`. | Add new routes next to related ones. In `post()`, admin-only routes go **after** the line `if not is_admin(actor): raise Denied("Only admins can do this")`. A new admin-only settings route that other admins should see live: add its prefix to `ADMIN_SYNC_PATHS`. |
| `backend/app.py` → `push` / `broadcast` / `push_admins` / `stamp` | live notices over `/stream` (SSE); every notice gets `seq` + `boot` so browsers apply it once | Shared by every module that changes data. `log()` already broadcasts a refresh. |
| `backend/lan.py` | `network` settings: allowed client networks, Origin check, HTTPS listener (`TLSServer`), LAN address list | Used by `app.py`, `launcher.py` and `tools/make_office_cert.py`. |
| `backend/launcher.py`, `START SOMESH ENTERPRISES.bat` | SERVER MODE: checks, automatic startup backup, start, LAN addresses | `OPEN SOMESH ENTERPRISES (Employee PC).bat` is the client-only launcher. |
| `tools/backup_db.py`, `tools/restore_db.py`, `tools/make_office_cert.py`, `tools/office_firewall.ps1` | online backup/restore, office CA + HTTPS certificate, Windows Firewall rule | See README "Shared office setup". |
| `backend/config.json`, `workflow.json`, `users.json` | live settings | Changing them affects everyone. Don't commit test edits. |

## Recipes

**Add a new page (tab) "Reports":**
1. Create `frontend/js/pages/reports.js` with `function viewReports() { return hero("Reports", "…") + … }`. If it has buttons, add a `wireReports()` too.
2. In `frontend/index.html`, add `<script src="/static/js/pages/reports.js"></script>` before `js/core/actions.js`.
3. In `frontend/js/core/shell.js` → `render()`, add `["reports", "Reports"]` to the admin tab list, add `reports: viewReports` to the view map, and add `if (S.tab === "reports") wireReports();`.
4. If it needs data, add a GET route in `backend/app.py` → `class H.get()`. Then fetch it in `load()` (`live-and-load.js`) and in the tab-click handler in `render()`.

**Add a new API route:** add `if u.path == "/api/xyz": ...` in `get()` for a read, or in `do_POST()` for a change. Return with `self.send_json({...})`, and raise `FlowError("message")` for errors the user should see. Use `self.need_admin(qs)` for admin-only reads.

**Add a chart to the Dashboard:** add the number to `dashboard()` in `backend/app.py`. Then add a `chartXyz()` function in `frontend/js/pages/dashboard.js` and place it in the `dgrid` in `viewDash()`. Reuse `hbars()` for bar lists, and `ct()` for the hover tooltip.

**Change a colour, spacing or button style:** edit `frontend/css/app.css`. Button shadows are in the "v2" section at the end.

**Change the stages or people:** use the Workflow input page or `samples/Workflow_Input_Template.xlsx`. Don't edit `workflow.json` by hand.

## Data model (SQLite, `data/monthly_cycle.db`)

| Table | Holds |
|---|---|
| `bills` | one row per bill (`id`, client, status, `demo` flag, contract, vault folder) |
| `tasks` | one row per stage of a bill, or per task an admin gave (`stage` = `S01`… or `TASK-001`…), with status, owners, assignee and times |
| `work_log` | timer segments (`task_id`, `user`, `start`, `end`). The Tracker, Timetable and Dashboard are all built from this table. |
| `adhoc` | the definition of each task an admin gave (`TASK-…`) |
| `events` | the Activity history |
| `alerts` | everyone's alerts |
| `sessions` | sign-in tokens |

Statuses are `assigned` → `in_progress` → `submitted` → `approved`; a sent-back task goes back to `in_progress`. For tasks an admin gave, `approved` + `ended_at` means the task is finished.

Rule execution is serialized across scheduler and request threads. `rule_runs.trigger` records the trigger at firing time; deduplication uses rule, task and trigger. Malformed rules are isolated and logged as errors. API dry runs use current task details for historical events (they do not reconstruct past ownership or rework counts).


## Admin Smart Action Center

`backend/action_center.py` builds read-only projections from existing tasks, work logs, Activity, user profiles and stage definitions; there are no new tables. `app.py` validates filters, takes a consistent snapshot under the existing lock, and enforces Admin authorization on every new endpoint. Demo tasks and orphaned time-log references are excluded.

- Outstanding task state/deadlines are live; assignment/completion/activity totals use the selected date. Ad-hoc completion requires End task; workflow completion uses approval. Submitted work is pending approval, never counted as completed.
- Queue order: tasks overdue by at least 120 lunch-adjusted minutes, the current Admin's approvals, other overdue tasks, deadlines within 60 lunch-adjusted minutes, current corrections/document follow-ups, other approvers' submissions, then availability checks. Ties use lateness, deadline and task ID. Flags can overlap; queue cards are not duplicated.
- Availability checks need open work, no recorded work/activity, today's configured working period, a 30-working-minute grace period, and no lunch. No leave/attendance register exists, so these are prompts to check availability, never absence findings.
- Workload review means multiple overdue assignments or remaining configured task limits above one normal day's capacity. It is a planning indicator, not an effort prediction or performance score. Shared unclaimed work appears for each eligible owner, while task counts are unique.
- Frontend reuses the existing SSE refresh and 30-second loader. Review uses original `/api/tasks/<id>/approve` and `/reject` endpoints; only the designated approver gets review controls. Reassignment requires explicit confirmation, a matching task snapshot, same-department destination and existing busy checks, then reuses `rule_move` to retain time history/approver and records an Activity event.
- Related Alerts applies a task-ID filter to the existing recipient-scoped Alert Center, with an explicit Clear filter button. Employee navigation reuses the Tracker detail modal. Excel/PDF exports include the filtered summary, complete attention queue and employee workload; PDF uses bordered wrapping tables with repeating headers.
- Regression checks: `tests/test_action_center.py`; optional `python tests/run_browser.py --action-center`. All mutations in tests use synthetic temporary databases.

## Login and Admin access management

`frontend/js/core/login-and-admins.js` supplies the Admin/Employees login accordion, cross-profile search, first-load CSS intro and `openAdminManagement` modal. `shell.js` keeps the existing PIN sign-in and adds Manage Admins beside the header controls. `main.js` starts the intro and refreshes public profile metadata while signed out.

- `GET /api/admins` requires an authenticated Admin and returns existing users, Admin count and recent access audit entries.
- `POST /api/admins/role` accepts `{user, admin: boolean, confirmation_pin}`. `change_admin_role` rechecks the acting Admin, validates the target and last-Admin guard under the shared lock, and checks the acting Admin's existing PIN with `verify_admin_pin` (five failed attempts per user in five minutes).
- Roles remain in the existing `backend/users.json`, preserving all other profile fields and configured credentials. Changes invalidate the affected user's sessions and write `admin_access` Activity events with actor and timestamp. Login issuance and role updates share the lock; workflow imports also invalidate sessions when roles change and cannot remove the last Admin. No database migration is required.


## Admin Alert Center and notification island

`frontend/js/pages/alert-center.js` renders the recipient-scoped header island and Admin Alert Center (the employee Alerts sheet remains in `activity-alerts.js`). `shell.js` wires them on every Admin page. `live-and-load.js` reuses the existing SSE stream; refreshes are coalesced and a single 30-second check updates deadlines and expired snoozes. Opening Alerts never automatically marks Admin notifications read.

- `GET /api/alerts`: Admin-only, all existing alerts addressed to that session user, grouped by task and event kind with every original message retained. `alert_center` derives priorities from live task deadlines/status, designated approver, current contract status and active workflow-input errors. Summary counts distinguish unread notifications from unresolved urgent issues and pending approval tasks.
- `GET /api/alerts/<alert_id>/task`: Admin-only and recipient-checked; reuses `task_view` for workflow and admin-assigned tasks. Review actions call the existing task approve/reject routes, which still require the designated validator.
- `POST /api/alerts/read`: existing route, now accepts optional `ids` for selected own alerts; omitting IDs preserves the existing mark-all behavior. It never changes tasks.
- `POST /api/alerts/snooze`: Admin-only, own `ids` plus `minutes` (15, 60, 240 or 0 to undo). Urgent alerts cannot be snoozed; a task becoming overdue overrides an earlier snooze. The additive nullable `alerts.snoozed_until` migration preserves all existing alerts and read flags.
- No alert history is deleted. Contract actions read existing authorized Storage data. UI refreshes abort on sign-out and stale task/contract responses cannot open another session's panel.


### Island preview interaction

The Admin header reserves a centered top dock for the fixed notification pill. Mouse hover opens its floating preview; leaving the pill and preview closes it after 300 ms, while touch/keyboard activation toggles it. The panel stays below header navigation, is at most 460 px wide and 65% of the visible viewport high, and scrolls internally.

`acIslandCard` is the compact variant of `acCard`; the full Alerts page keeps its existing layout. Preview descriptions have separate `S.acIslandExpanded` state and only explicit Open task buttons invoke task navigation. `acWireIslandCards` handles captured pointer dragging and keyboard Up/Down reordering, suppresses release clicks, and defers live card repaint during a drag. Preferred display order is stored locally per Admin under `se_alert_island_order_<user>`. The preview still selects the backend's top five priority groups; neither priorities nor backend records are changed by ordering.
