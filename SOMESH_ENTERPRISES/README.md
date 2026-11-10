# SOMESH ENTERPRISES · Monthly Cycle app (v2.0)

A small office web app. It runs the monthly cycle: tasks, alerts, approvals, time tracking, the Pipeline timetable, the Dashboard, and the Data Center storage (Master Tracker, Contract Register, Vault).

- **Backend:** Python 3.9+ standard library plus `openpyxl` (Excel) and ReportLab (PDF). There is no framework, no build step and no database server; SQLite is built in.
- **Frontend:** plain HTML, CSS and JavaScript, with no build step. Edit a file, refresh the browser, and you see the change.

## Run it

| On | Do this |
|---|---|
| Windows | Double-click **`START SOMESH ENTERPRISES.bat`**. It finds/installs Python and missing packages, checks the configured port, then starts the app and opens Chrome when available. |
| Windows, with demo data | Double-click **`reset_demo_data_windows.bat`**. |
| Mac / Linux | `./start.sh` |
| By hand | `pip install -r backend/requirements.txt`, then `python backend/app.py --open` |
| Docker | `docker compose up -d` |

The app opens at **http://localhost:8080**. Python serves both the frontend and `/api`; there is no React development server, npm install, production build step, or separate API URL. The host and port come from `backend/config.json`. The BAT launcher reuses a healthy server from this checkout. An occupied port belonging to another checkout or application produces an error; it never kills that process.

Sign in by selecting a profile. Employees retain their existing profile-based sign-in. Admins also enter their configured PIN; **Enter** and **Sign in** submit the same form and open the Dashboard. Credentials are under `backend/config.json` → `security.admin_pin`, with optional per-person overrides in `security.pins`. No credentials are documented here. Existing sessions survive refresh until logout, invalidation, or a role change. The existing application version remains **v2.0**, including the login label and HTTP server banner.

Employee profile selection is the existing trusted-office authentication model, not individual password authentication. Use a trusted network, or authenticated HTTPS access in front of the app for wider access.

Run every command from the **project root** (the folder with the .bat file), not from inside `backend/`.

An optional virtual environment keeps packages separate: `python -m venv .venv`, activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on Mac/Linux), then run `python -m pip install -r backend/requirements.txt` and `python backend/app.py`.

## Folder structure

```
SOMESH_ENTERPRISES/
├── START SOMESH ENTERPRISES.bat   one-click start (Windows)
├── reset_demo_data_windows.bat    start with demo data
├── start.sh                       start on Mac / Linux
├── Dockerfile, docker-compose.yml
├── README.md                      this file
├── CODE_MAP.md                    which code is responsible for which page  <- start here
├── GIT_SETUP.md                   new repo, cloning, and working on it together
│
├── backend/                       the server (Python)
│   ├── app.py                     web server, API routes, workflow engine, timers, dashboard numbers, demo data
│   ├── storage.py                 Data Center folders: Master Tracker, Contract Register, Vault, sample files
│   ├── workflow_input.py          reads and writes the Workflow Input Excel / Google Sheet
│   ├── requirements.txt           openpyxl and ReportLab
│   ├── tracker_export.py          structured multipage Tracker PDF
│   ├── config.json                settings: port, PIN, lunch, working hours, repeatable tasks, automation, email…
│   ├── workflow.json              the stages of the process now in use
│   └── users.json                 the people now in use
│
├── frontend/                      the web page (served by the backend at /static/...)
│   ├── index.html                 page skeleton + the list of scripts (order matters)
│   ├── css/app.css                all styles
│   ├── assets/                    images used by the page
│   └── js/
│       ├── core/                  shared code: state, server calls, helpers, components, sign-in/tabs, task buttons
│       ├── pages/                 one file per page (Dashboard, Pipeline, Tracker, …)
│       └── main.js                starts the app (must load last)
│
├── samples/                       example workbooks (workflow input template, long demo, department sheet)
├── docs/                          user guide, storage architecture picture, Gather setup
│
├── data/                          created on first start: the database (NOT in git)
└── storage/                       created on first start: Data Center files (NOT in git)
```

## How the two halves talk

1. The browser loads `frontend/index.html` from the backend (`/`), then the CSS and the scripts from `/static/...`. The `/static/` path maps to the `frontend/` folder.
2. Each page reads and writes data with `api("/api/...")` (in `frontend/js/core/state-and-api.js`). The backend answers with JSON in `class H` in `backend/app.py`: `get()` handles reads and `do_POST()` handles changes.
3. Live alerts come over `/stream` (Server-Sent Events). Data refreshes reuse `load()` and `render()`; alert-only updates refresh counts/panels without rebuilding the current page. Logout closes the stream and notification timers.

**CODE_MAP.md** lists every page with its frontend file, the backend routes and functions behind it, and examples of typical tasks.

## Login and Admin Management

The **Admin** and **Employees** login cards start collapsed. Opening one closes the other. Search reveals matching profiles across both groups without changing permissions. The short company intro runs once per page load; **Skip Intro** and reduced-motion support are available.

Authenticated Admins can select **Manage Admins** in the header to search, promote or revoke users. Confirmation requires the acting Admin's PIN. Backend authorization preserves profiles/tasks, invalidates affected sessions, records the actor/time in Activity, and prevents removal of the last Admin. Promotion does not reset credentials; promoted users use their existing configured Admin PIN. Roles remain in the existing users JSON.

## Admin Smart Action Center

Select **Action Center** in the Admin tabs for operational counters, **Needs Your Attention**, employee workload, and a daily summary. Filter by date, department, employee, workload or search; click a counter/recommendation to see its records. Hover/focus workload rows for open-task previews and capacity context. Outstanding work is live; activity, assignment and completion totals use the selected date. Demo tasks are excluded.

**Review submission** opens documents and the original approve/return workflow. Only the designated approver can review; approval is never automatic. **Reassign task** requires confirmation and rejects changed task snapshots, other-department destinations and existing busy conflicts. **Open employee Tracker** reuses employee details; **Related alerts** shows only your own notifications for that task.

Availability checks are limited to today's working hours, outside lunch, after a 30-working-minute grace period, and employees with open work. There is no leave register: verify availability before following up. Workload warnings use overdue work and remaining configured task limits, not a performance ranking. Shared unclaimed assignments appear for every eligible owner but count once in task totals.

**Export** downloads the filtered operations summary, workload and complete attention queue as Excel or a wrapped, bordered, multipage PDF. Existing SSE and 30-second refreshes update the page. No new runtime dependency or database schema is required. Run dedicated browser checks with `python tests/run_browser.py --action-center` after setting up Playwright as described below.

## Tracker and exports

Choose a date and use the existing search, sorting, demo filter and **Include tasks with no time** controls. Hover an employee card for that person's task preview; click for a scrollable detail dialog with totals, timings, statuses and document actions. Close it using Escape, the close button, or the backdrop.

The main table starts collapsed under **View All Tasks**. Desktop hover opens it; leaving closes it after a short delay. Click/tap pins it open, and clicking again closes it. Timers continue while collapsed. Lunch Lock settings remain below the table; staff task changes are locked during lunch and lunch is excluded from working time.

**Export** beside the date offers Excel and PDF. Exports retain the existing day-wide scope, independent of on-screen search. Main task records exclude demo bills. Excel retains its Tasks, Per person, Time log and Notes sheets. PDF uses the same main task rows in landscape A4 with wrapped bordered cells, repeating headers and additional pages as needed. Working time uses `HH:MM:SS`.

## Admin Alert Center and Dynamic Island

The black island stays centered in its own header dock across Admin pages. Hover opens the important/recent preview; leaving closes it after 300 ms. Touch toggles it. Escape or an outside click closes it. The bounded panel scrolls internally.

Drag handles reorder the preview, or focus a handle and use arrow keys. This local per-Admin preference does not change backend priority. Description arrows expand independently. Hover, text, dragging and expansion never open a task: only **Open task** does. **Mark read** never approves work. **View all alerts** opens the full Alert Center.

The Alert Center includes Urgent/Approvals/Updates counters, filters, search, timestamps, grouped task notifications, persistent read state and snoozing for noncritical notifications. Priority uses actual task state/deadlines and existing kinds. Review actions use original backend permissions. Each Admin sees only their own notifications; employees retain their existing alert view. SSE notifications are reused, with a controlled 30-second refresh for changing deadlines.

## Automation

Automation includes **Workflow model**, **Rules**, **History** and **Settings**. The model shows stages, branches, owners, live counts, time limits and applicable rules. Click a stage for details and **Add rule for this stage**.

The **When → If → Then** builder supports ordered actions, message placeholders, validation, disabled example templates, testing against the last seven days, toggles and firing history. Admin APIs include `/api/rules`, `/api/rules/log` and `/api/workflow-model`. Per-task deduplication, default demo exclusion, error isolation and recursion guards protect normal workflows. Existing automatic start, escalation/reminder and monthly opening controls remain in **Settings**. See CODE_MAP.md for routes/functions.

## Regression tests

Install test-only dependencies with `python -m pip install -r requirements-dev.txt`, then run:

```sh
python -m unittest discover -s tests -v
```

Tests create synthetic users, generated credentials and temporary databases. They never open the installed database. `pypdf` validates PDF contents/layout only during testing.

Browser tests use optional Playwright tooling, not an application dependency. Install `playwright` in a separate test-tools directory. With Windows Edge installed:

```powershell
$env:PLAYWRIGHT_MODULE_PATH = 'C:\path\to\test-tools\node_modules\playwright'
python tests/run_browser.py
```

The runner starts a synthetic app on a free loopback port and closes it afterward. Set `BROWSER_CHANNEL` for another installed channel; on other platforms install Playwright's Chromium browser. No deployment PIN or installed database is used.

## Working on it

- **Frontend change:** edit the file under `frontend/` and refresh the browser (Ctrl+F5). No restart is needed.
- **Backend change:** edit the file under `backend/`, close the black window, and start the app again.
- **Check JavaScript before committing:** run `node --check frontend/js/pages/<file>.js`, if Node is installed. Otherwise, open the browser console (F12) and look for red errors.
- **Check Python before committing:** run `python -m py_compile backend/app.py`.
- **Test with demo data:** start with `reset_demo_data_windows.bat`. Demo data is visible to admins only, and New bill → Clear demo data removes it.
- **Never commit `data/` or `storage/`.** `.gitignore` already excludes them. Each PC keeps its own database.
- **Back up before upgrades.** Preserve data, configured storage and deployment config/workflow/users files. Stop Python before copying SQLite files, or use SQLite's backup facility. Additive rules/history tables and the nullable alert snooze column preserve existing records/read flags.
- **Start fresh is destructive.** It clears bills, tasks, time, alerts and history. It is separate from reloading/clearing demo records; never use it to test an existing installation.
- **Keep credentials private.** Exclude `.env`, credentials, caches, logs and test downloads. Deployment config/profile/workflow JSON is local and ignored; commit only the safe `.example.json` files. Existing local files and credentials are preserved. Older repository history may still contain the previously tracked settings; keep access restricted and rotate any credentials previously published.
- **Watch the shared config files.** The Workflow input page rewrites `backend/workflow.json` and `backend/users.json`. Commit those only when the process change is meant for everyone.

See **GIT_SETUP.md** for the branch-and-pull-request routine, so two people can push at the same time without overwriting each other.

## Admin employee management

On the authenticated Admin Dashboard, the EMPLOYEES section offers **+ Add Employee** and **Manage Employees**. Profiles appear under their department immediately. Name, designation, department and access role are required. Duplicate names (case/spacing insensitive, including archived profiles) are rejected. Admin access changes require the acting Admin PIN.

Delete asks for confirmation and archives the employee. Sessions are invalidated and the profile disappears from active lists and login, while tasks, time logs, documents and audit history remain. Review outstanding assignments before archiving. Self deletion and removal of the last Admin are blocked. Renames update task and document ownership references; historical audit text remains unchanged.

The `employees` table in the existing `data/monthly_cycle.db` is authoritative. Existing JSON profiles are imported on first use, and `users.json` remains a compatibility mirror. Workflow imports and Manage Admins synchronize the same table. Employee changes use authenticated `/api/employees` GET/POST endpoints; regular employees receive HTTP 403.

Checks: `python -m unittest discover -s tests -v`; browser CRUD checks: `python tests/run_browser.py --employees` with Playwright and Google Chrome installed. This plain JavaScript frontend has no build step; use `node --check` and browser checks.

## Startup and database audit (2026-11-10)

There is one Python HTTP service for both the frontend and API. The database is **SQLite**, at `data/monthly_cycle.db`; no MySQL server, connector, credentials, migration command or npm service is required. SQLite schema upgrades run additively on startup. Preserve the whole `data/` directory, storage, and local `backend/config.json`, `users.json`, `workflow.json` when upgrading.

Private deployment files are excluded from Git. On a fresh checkout, startup copies `backend/config.example.json`, `users.example.json`, and `workflow.example.json` into local files. These examples contain synthetic profiles and no default Admin PIN. Set `SOMESH_ADMIN_PIN` in your local environment or set `security.admin_pin` privately in `backend/config.json` before starting. Existing configured PINs remain valid; the environment value overrides the shared PIN for that process. Never commit the real configuration or a PIN to a script.

Double-click **START SOMESH ENTERPRISES.bat**, or invoke it from any working directory with the full quoted path. The script handles spaces, discovers Python 3.9+, installs missing runtime dependencies, uses the current source files, and opens Chrome when installed (otherwise the default browser). Its port follows the local config (default `8080`). Keep the launcher open while using the server. Stop it with Ctrl+C before restarting after backend changes. It reuses an already healthy server; restart explicitly to load edited Python code.

Useful BAT arguments:

- `--check --no-browser --no-pause`: verify startup files, dependencies, PIN setup and port configuration without starting a service.
- `--no-browser --no-pause`: run without a browser or error prompt, useful for automation.
- `reset_demo_data_windows.bat`: load demo records on a stopped instance; when an instance is already running, reuse it without modifying demo or real data. Use the authenticated Admin controls for an intentional demo reload. Do not use demo reloads to test production.

A local `/api/health` probe reports application version, SQLite connectivity and a hash identifying the checkout, without exposing credentials or filesystem paths. The launcher uses a lock to avoid racing starts and refuses an unrelated service on the configured port. Failure exit codes are preserved. No password is embedded in either BAT file.

The UI follows the system light/dark preference through its existing theme variables. Attendance registers remain workflow tasks/documents; the application has no separate attendance/leave module. Existing assigned tasks support reassignment, progression and deletion; arbitrary editing of an already assigned task title is not an existing feature. Task templates can be edited before assignment.

Validation commands (run inside the project folder):

```powershell
python -m unittest discover -s tests -v
# Optional: use your private reference files in read-only tests.
$env:EXCEL_REFERENCE_ROOT = 'C:\path\to\reference-files'
$env:PLAYWRIGHT_MODULE_PATH = 'C:\path\to\test-tools\node_modules\playwright'
$env:BROWSER_CHANNEL = 'chrome'
python tests/run_browser.py
python tests/run_browser.py --action-center
python tests/run_browser.py --employees
python tests/run_browser.py --excel
python tests/run_browser.py --all-employees
```

Windows startup tests launch both BAT files against disposable synthetic databases in paths containing spaces. The tests stop only their own child processes; restricted environments may require permission for process cleanup. Private Excel-reference tests skip unless `EXCEL_REFERENCE_ROOT` is supplied. Destructive task/bill/demo tests use temporary databases, never the installed database. There is no configured frontend build or lint command: JavaScript is checked with `node --check`, Python with `compileall`, and behavior with the browser/API suites. See `docs/AUDIT_2026-11-10.md` for executed checks and limitations.
