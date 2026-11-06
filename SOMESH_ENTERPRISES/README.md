# SOMESH ENTERPRISES · Monthly Cycle app (v2.0)

A small office web app. It runs the monthly cycle: tasks, alerts, approvals, time tracking, the Pipeline timetable, the Dashboard, and the Data Center storage (Master Tracker, Contract Register, Vault).

- **Backend:** Python 3.9+ standard library plus `openpyxl` (Excel) and ReportLab (PDF). There is no framework, no build step and no database server; SQLite is built in.
- **Frontend:** plain HTML, CSS and JavaScript, with no build step. Edit a file, refresh the browser, and you see the change.

## Run it

| On | Do this |
|---|---|
| Windows | Double-click **`START SOMESH ENTERPRISES.bat`**. It installs Python and the packages if needed, then starts the app and opens the browser. |
| Windows, with demo data | Double-click **`reset_demo_data_windows.bat`**. |
| Mac / Linux | `./start.sh` |
| By hand | `pip install -r backend/requirements.txt`, then `python backend/app.py --open` |
| Docker | `docker compose up -d` |

The app opens at **http://localhost:8080**. Python serves both the frontend and `/api`; there is no React development server, npm install, production build step, or separate API URL. The host and port come from `backend/config.json`. Reuse or stop an existing server before starting another on the same port.

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
- **Keep credentials private.** Exclude `.env`, credentials, caches, logs and test downloads. Config/profile JSON is already tracked in this repository: do not publish deployment credentials or private rosters. This update does not change deployment credentials or profiles.
- **Watch the shared config files.** The Workflow input page rewrites `backend/workflow.json` and `backend/users.json`. Commit those only when the process change is meant for everyone.

See **GIT_SETUP.md** for the branch-and-pull-request routine, so two people can push at the same time without overwriting each other.
