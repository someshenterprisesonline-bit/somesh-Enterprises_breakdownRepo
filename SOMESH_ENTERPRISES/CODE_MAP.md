# Code map: which code is responsible for which page

Use this when giving out tasks. Each row is one page. **Frontend** draws it, and **Backend** supplies or changes its data.
Two people can work at the same time without clashing when they work in different rows. Shared files are marked ⚠. Tell each other before changing them.

Frontend paths are under `frontend/`. Backend functions are in `backend/app.py` unless another file is named. To find something, search the file for the function name (Ctrl+F). Line numbers change, so they're not listed here.

## Pages

| Page (tab) | Who sees it | Frontend file | Frontend functions | Backend routes | Backend functions |
|---|---|---|---|---|---|
| **Sign-in screen** | everyone | `js/core/shell.js` | `render()` (top part), `signIn`, `finishSignIn`, `logout` | `POST /api/login`, `/api/logout`, `GET /api/me`, `/api/meta` | `admin_pin_ok`, `new_session`, `session_user` |
| **My tasks** | everyone | `js/pages/my-tasks.js` | `viewMine` | `GET /api/state` | `state`, `task_view` |
| **To check** | approvers, admins | `js/pages/my-tasks.js` | `viewCheck` | `GET /api/state` | `state` |
| Task buttons on the cards (Start, Done, Approve, Send back, End, attach files) | everyone | `js/core/actions.js`, `js/core/components.js` | `act`, `dialog`, `taskCard`, `attachFiles` | `POST /api/tasks/<id>/claim, submit, approve, reject, end, upload, unupload` | `claim`, `submit`, `approve`, `reject`, `end_task`, `save_upload`, `timer_start`, `timer_stop` |
| **Tracker** | admins | `js/pages/tracker.js` | `viewTracker`, `wireTracker` | `GET /api/tracker`, `/api/tracker/export`, `POST /api/lunch` | `tracker`, `tracker_xlsx`, `lunch_cfg` |
| **Overview** | admins | `js/pages/overview.js` | `viewOverview` | `GET /api/pipeline` | `pipeline` |
| **Dashboard** | admins | `js/pages/dashboard.js` | `viewDash`, `chartDaily`, `chartHeat`, `chartUtil`, `chartIdle`, `chartGap`, `gapTable`, `chartDept`, `chartTop`, `dashCsv`, `wireDash` | `GET /api/dashboard` | `dashboard`, `workday_cfg`, `available_seconds` |
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
| `backend/app.py` → `class H` (`get` / `do_POST`) | all API routes in one place | Add new routes next to related ones. In `do_POST`, admin-only routes go **after** the line `if not is_admin(actor): raise Denied("Only admins can do this")`. |
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
