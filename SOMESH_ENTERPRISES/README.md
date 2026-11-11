# SOMESH ENTERPRISES · Monthly Cycle app (v2.0)

A small office web app. It runs the monthly cycle: tasks, alerts, approvals, time tracking, the Pipeline timetable, the Dashboard, and the Data Center storage (Master Tracker, Contract Register, Vault).

- **Backend:** Python 3.9+ standard library plus `openpyxl` (Excel) and ReportLab (PDF). There is no framework, no build step and no database server; SQLite is built in.
- **Frontend:** plain HTML, CSS and JavaScript, with no build step. Edit a file, refresh the browser, and you see the change.

## Run it

| On | Do this |
|---|---|
| Windows, Admin PC (server) | Double-click **`START SOMESH ENTERPRISES.bat`** (SERVER MODE). It finds/installs Python and missing packages, checks settings, the database and ports, backs up the database, then starts the app, prints the office LAN address and opens Chrome. |
| Windows, employee PC | Double-click **`OPEN SOMESH ENTERPRISES (Employee PC).bat`**. It only opens Chrome at the Admin PC's address. See [Shared office setup](#shared-office-setup-one-admin-pc-many-employee-pcs). |
| Windows, with demo data | Double-click **`reset_demo_data_windows.bat`**. |
| Mac / Linux | `./start.sh` |
| By hand | `pip install -r backend/requirements.txt`, then `python backend/app.py --open` |
| Docker | `docker compose up -d` |

The app opens at **http://localhost:8080**. Python serves both the frontend and `/api`; there is no React development server, npm install, production build step, or separate API URL. The host and port come from `backend/config.json`. The BAT launcher reuses a healthy server from this checkout. An occupied port belonging to another checkout or application produces an error; it never kills that process.

Sign in by selecting a profile. Employees retain their existing profile-based sign-in. Admins also enter their configured PIN; **Enter** and **Sign in** submit the same form and open the Dashboard. Credentials are under `backend/config.json` → `security.admin_pin`, with optional per-person overrides in `security.pins`. No credentials are documented here. Existing sessions survive refresh until logout, invalidation, or a role change. The existing application version remains **v2.0**, including the login label and HTTP server banner.

Employee profile selection is the existing trusted-office authentication model, not individual password authentication. Use a trusted network, or authenticated HTTPS access in front of the app for wider access.

Run every command from the **project root** (the folder with the .bat file), not from inside `backend/`.

An optional virtual environment keeps packages separate: `python -m venv .venv`, activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on Mac/Linux), then run `python -m pip install -r backend/requirements.txt` and `python backend/app.py`.

## Shared office setup (one Admin PC, many employee PCs)

The Admin PC is the central host. It runs the single app process, which serves the web page, the API and the live-update stream on one port and keeps the one shared database (`data/monthly_cycle.db`, SQLite) and all Excel Workspace documents. Employee PCs only need **Google Chrome**: no Python, MySQL or Node.js. The app does not use MySQL. Nothing is exposed beyond the office network: the app refuses clients outside private (LAN/VPN) address ranges.

```
Employee PC (Chrome) ──https://ADMIN-IP:8443 or http://ADMIN-IP:8080──▶ Admin PC: backend/app.py
                                                                         ├─ web page + /api + /stream (live updates)
                                                                         ├─ data/monthly_cycle.db (SQLite, WAL)
                                                                         └─ storage/ (Data Center files)
```

### Admin PC: install once

1. Copy or clone the whole project folder to the Admin PC, for example `C:\SOMESH ENTERPRISES`. Keep the existing `data\`, `storage\` and `backend\config.json`, `users.json`, `workflow.json` when upgrading.
2. Set the Admin PIN privately in `backend\config.json` → `security.admin_pin` (or the `SOMESH_ADMIN_PIN` environment variable).
3. Give the Admin PC a fixed LAN address (a DHCP reservation in the office router is easiest) so employee bookmarks keep working.
4. In **Windows Settings → Network & internet → (office Wi-Fi/Ethernet) → Properties**, set the network profile to **Private**. On a *Public* network Windows blocks employee PCs.
5. Firewall (PowerShell **as Administrator**, once):
   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\office_firewall.ps1
   ```
   This allows TCP 8080 and 8443 from the local subnet on Private/Domain networks only. Add `-BlockMySQLFromLan` to also stop other computers reaching any MySQL server on this PC (3306/33060). This app never uses MySQL. If Windows earlier created "python.exe" allow rules for **Public** networks, review them in *Windows Defender Firewall → Inbound Rules*.
6. HTTPS (recommended, so PINs never cross the network unencrypted):
   ```powershell
   python -m pip install --user cryptography
   python tools\make_office_cert.py --enable
   ```
   Run this while the app is stopped. It creates a private office certificate authority and an HTTPS certificate for this PC's name and LAN addresses in `certs\` (excluded from Git), turns on the HTTPS listener (port 8443), and writes `certs\employee-pc-kit\`. Re-run it (without `--enable`) if the Admin PC's IP address changes. The CA is reused, so employee PCs do not need to reinstall it. Never copy `certs\office-ca.key` off the Admin PC.
7. Start the app: double-click **`START SOMESH ENTERPRISES.bat`** (SERVER MODE). It checks Python and packages, settings, HTTPS files, database integrity and ports. It then backs up the database to `data\backups\startup-*` (the newest 14 are kept), starts the server, prints the **employee address** (for example `https://192.168.1.4:8443`) and opens Chrome at `http://localhost:8080`. Keep the window open: closing it stops the app for everyone. It reuses an already running server, never stops other programs, and never resets or reseeds data.

### Employee PCs

Copy `certs\employee-pc-kit\` (USB or a shared folder) to each employee PC and double-click **`OPEN SOMESH ENTERPRISES (Employee PC).bat`** inside it. The first time, it installs `office-ca.crt` for that Windows user (click **Yes** if Windows asks). It then checks the server is reachable and opens Chrome at the saved address. It never starts a server or database. Without the kit, open Chrome at the address shown in the SERVER MODE window and bookmark it. The CA certificate can also be downloaded from `http://ADMIN-IP:8080/office-ca.crt`; install it with `certutil -user -addstore Root office-ca.crt`.

Once every employee PC trusts the office CA, set `network.https.redirect_lan_http` to `true` in `backend\config.json` (app stopped) so other PCs are always sent from `http://…:8080` to HTTPS. `http://localhost:8080` on the Admin PC keeps working.

### Network and security settings (`backend\config.json` → `network`, all optional)

| Setting | Default | Meaning |
|---|---|---|
| `allowed_networks` | loopback, 10/8, 172.16/12, 192.168/16, link-local, IPv6 private | Client addresses allowed to use the app. Add `100.64.0.0/10` for a Tailscale VPN. Everything else gets HTTP 403. |
| `session_days` | `30` | Sign-ins expire after this many days (`0` = never). |
| `https.enabled` / `https.port` | `false` / `8443` | HTTPS listener (certificate from `tools\make_office_cert.py`). |
| `https.redirect_lan_http` | `false` | Send other PCs from HTTP to HTTPS. |
| `public_url` | empty | Address shown at startup, for example `https://somesh-admin:8443`. |
| `allowed_origins` | empty | Extra web origins allowed to POST (normally none). |

Every API call is checked on the server: the person comes from the session token, admin-only routes need an admin session, and Excel documents are visible only to their owner and admins. Browser POSTs from any other web origin are refused (`Cross-site request blocked.`), no CORS headers are sent, and responses carry `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy: no-referrer`. The database is a file used only by the app; there is no database port to expose and no database password. Employee sign-in remains profile selection, the existing trusted-office model, and Admins also need their PIN.

### Live updates between computers

After each successful change, the server pushes a small notice over Server-Sent Events (`/stream`), and each open browser re-reads only what it shows. This covers tasks (create, assign, start, submit, approve, return, delete), employees and admin roles, alerts and the Dynamic Island, the Tracker, Dashboard and Pipeline, lunch, automation settings, rules and templates, and Excel Workspace/NEFT versions. Notices are numbered and applied once. If the connection drops or the server restarts, the page reconnects by itself with back-off and refreshes once to catch up. Excel notices go only to the document's owner and admins (and Excel employees for shared templates). A clean open document reloads in place; one with unsaved edits keeps them and shows a conflict notice, and the next save is still revision-checked, so two people never silently overwrite each other. Large Excel sheets are paged by the server (50 rows a request), and JSON responses over 4 KB are gzip-compressed.

### Backup and recovery

- **Automatic:** every SERVER MODE start makes `data\backups\startup-YYYYMMDD-HHMMSS\` (the newest 14 are kept).
- **Now:** double-click **`BACKUP SOMESH DATA.bat`**, or run `python tools\backup_db.py --dest "E:\SOMESH Backups" --keep 30`. Safe while the app runs.
- **Nightly (recommended):** Task Scheduler → Create Basic Task → Daily → *Start a program* `python`, arguments `tools\backup_db.py --label nightly --keep 30 --dest "E:\SOMESH Backups"`, *Start in* the project folder.
- Each backup folder has a consistent `monthly_cycle.db` (made with SQLite's online backup and integrity-checked), `config.json`, `users.json`, `workflow.json` and a `manifest.json` with row counts. The Data Center `storage\` folder is separate; copy it too, for example `robocopy storage "E:\SOMESH Backups\storage" /MIR`.
- **Restore:** close the SERVER MODE window, then
  ```powershell
  python tools\restore_db.py "data\backups\startup-20261110-090000" --yes
  ```
  Add `--with-settings` to restore the three JSON files too. The current database is saved first as `data\backups\pre-restore-*`. The tool refuses while the app is running.
- Backups contain personal data and the Admin PIN. Keep them on an access-controlled drive, never in Git or a public share (`data\` and `certs\` are excluded by `.gitignore`).

### Troubleshooting

| Symptom | Check |
|---|---|
| Employee PC: "can't be reached" | The SERVER MODE window is open; the network is **Private**; `tools\office_firewall.ps1` was run; the address matches the one printed at startup. |
| "Your connection is not private" | `office-ca.crt` is not installed for that Windows user (run the employee launcher again), or the Admin PC's IP changed (re-run `tools\make_office_cert.py`). |
| HTTP 403 "not on an approved office network" | The client address is outside `network.allowed_networks`. |
| Red banner "connection lost" | The page reconnects automatically when the server is reachable again. |
| Startup says the database check failed | Restore the latest good backup (above). |

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

Shared-host checks: `python -m unittest tests.test_lan_sharing` (network allowlist, cross-site POSTs, sessions, sequenced/targeted live notices, HTTPS, backup/restore) and `python tests/run_browser.py --lan` (four separate Chrome sessions: live task assignment and start, admin settings, reconnection after an outage, Excel version sync and stale-save rejection).

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

The Sun/Moon button on login and in every user header switches themes instantly. Preferences are saved separately for each profile on this browser; the login screen keeps its own preference. Without a saved choice, the app follows the system theme. Switching themes preserves open panels and drafts. Colors for controls, alerts and paper previews are defined in `frontend/css/theme.css`. Attendance registers remain workflow tasks/documents; the application has no separate attendance/leave module. Existing assigned tasks support reassignment, progression and deletion; arbitrary editing of an already assigned task title is not an existing feature. Task templates can be edited before assignment.

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

Theme verification: `python tests/run_browser.py --themes` captures both themes and audits rendered text contrast in `data/theme-audit/`. Use `TEST_THEME=light` or `TEST_THEME=dark` with the core, Action Center and Excel browser suites. The theme suite also checks saved preferences across login/logout/refresh, keyboard access, cross-tab synchronization, storage restrictions and print styling. The generated screenshots and results remain local under ignored `data/`.

The existing Windows BAT launcher already serves the latest tracked frontend and backend from this checkout, including `theme.js`, `theme.css`, Dynamic Island and employee management. No separate compiled frontend folder is used. Restart after backend changes; frontend assets use the existing no-cache static route. Live deployment settings, databases, screenshots and test evidence remain local and excluded from Git.

## NEFT sorting and automatic Worksheet synchronization

In a private NEFT document, use **Sort NEFT by** and **Order**, or click the first three column headers, to sort S.No numerically, Name or Designation alphabetically, ascending/descending, or restore Original Order. Sorting moves complete employee rows. The selection persists in SQLite per document and sheet; current downloads reflect it. Original upload/version bytes remain unchanged.

NEFT edits auto-save after a short pause. Entry, save, completed-file upload, row add/delete and sorting synchronize S.No, Name and Designation into the linked Worksheet in the displayed order. Salary Amount maps only to an editable Net Salary field with matching headers. Existing Net Salary formulas remain formulas. Completed uploads do not receive new formulas when rows are added.

On first entry/import, each NEFT employee sheet gets its own private Worksheet from the configured shared Worksheet template. **Linked Worksheet** can explicitly select an existing private Worksheet belonging to the same owner, or create a new separate counterpart. Another user's files cannot be linked, even by an admin. Multiple NEFT sheets/documents never share a target. Configure an editable Worksheet template with S.No, Name of the Employees and Designation headers before using automatic synchronization.

Stable row UUIDs keep payroll fields associated with employees through edits and sorting. Worksheet-only fields remain editable; saved fields and unsaved payroll drafts move with their employee. Repeated sync does not append duplicate employees. Manual overrides in mapped Worksheet fields block synchronization rather than being overwritten: the NEFT save is retained, the target is rolled back, and an error is shown. Resolve the mapped-cell conflict and choose **Retry sync**. Unsupported formula rearrangements also stop safely. Original files and saved document versions remain available through existing history/download controls. Worksheet edits never trigger reverse synchronization.

The open linked Worksheet refreshes without reloading the page. Use **Open linked Worksheet** when a different document is already open. Status shows **Worksheet Synced** or a retryable error. The existing BAT launcher runs these source changes directly; restart it after backend updates. This application uses its existing plain JavaScript/Python HTTP service and SQLite storage, with no React build, FastAPI service or separate temporary production store.

Run `python tests/run_browser.py --neft` with Playwright/Chrome configured as above; repeat with `$env:TEST_THEME='dark'`. These checks use disposable synthetic databases and verify manual entry, all sorts, unsaved payroll preservation, edits/undo, row addition/deletion, refresh/reopen, 100-row uploads, separate employee documents and both Excel downloads. Screenshots remain under ignored `data/neft-sync-audit/`. Backend/API tests are included in the normal unittest discovery command.


## Excel Workspace order, designations and first employee row

Workspace sections appear as WORKSHEET, NEFT SHEET and COVERING LETTER for every authorized profile. This does not reorder workbook tabs.

NEFT names look up designations in the owner's Worksheets, preferring a matching linked Worksheet. Matching ignores case and repeated/outer whitespace. Unknown names, blank source roles and conflicting duplicates produce non-blocking status messages. Generated roles track stable employee UUIDs, follow source changes and clear when names are removed. Manual roles are preserved; **Use Worksheet designations** explicitly replaces them only for unambiguous matches. Generated mirrors are excluded as independent lookup evidence to prevent circular updates.

The reference TNOU row 7 is an empty spacer; its first employee is row 8. New blank templates compact leading employee-table spacers, translating all original formulas and totals so the first employee is at row 7. Original first-employee J/L cells remain manual, with blank values treated as zero in contribution sums. Legacy manual documents receive a first-row formula/type repair without moving existing employees; saving persists it and current exports include it. Completed uploads and historical version bytes are excluded from template repairs.

For a separate local development database and synthetic employee data, run:

```powershell
python tools/start_workspace_dev.py --port 8081
```

This uses the existing launcher from an isolated source/runtime copy under ignored `data/workspace-dev`, backs up that development database and opens Chrome at http://localhost:8081. Select the synthetic **Nandha** profile. The office server/database are untouched. Repeat startup reuses the healthy development server; stop only that development process before restarting to load backend changes. `--no-browser` suppresses opening Chrome and `--prepare` prepares files without starting the server.

Verification: `python -m unittest discover -s tests -v`, `python tests/run_browser.py --improvements`, `--excel`, `--neft` and `--all-employees`. Set PLAYWRIGHT_MODULE_PATH if Playwright is installed outside Node's module path. See `docs/WORKSPACE_IMPROVEMENTS_REPORT.md` for executed checks and evidence. This frontend has no production compilation step; JavaScript syntax and browser behavior are verified directly.


## Critical sync and profile-store safeguards

Worksheet autosaves now synchronize the linked NEFT employee rows as well as designations. TNOU maps A/B/C and **Take Home Salary (N)** to NEFT S.No/Name/Designation/Salary Amount (H). Basis Salary and gross Net Salary are not paid into NEFT. A reverse-generated take-home value is excluded from the legacy NEFT-to-Worksheet gross salary mapping, including after sorting. Missing pay inputs preserve an existing amount; invalid calculations and conflicting independent edits report a retryable mapping error. Banking fields, remarks, formulas and historical upload bytes remain intact.

Status includes the number of saved employees. Empty data reports No employee records available. **Retry NEFT sync** on Worksheet retries Worksheet-to-NEFT; NEFT's **Retry sync** retries the failed direction. Stable UUIDs keep employee bank details associated through edits, sorting and deletions; a removed employee's banking information remains in its versioned row and is not allocated to a replacement employee.

The existing office is **http://localhost:8080**, using `data/monthly_cycle.db`. The isolated helper uses **http://localhost:8081**, `data/workspace-dev/data/monthly_cycle.db` and explicitly labels its synthetic profiles. The office has its own authoritative roster; development profiles are not substitutes for office accounts. No automatic merging or database recovery occurs.

An established SQLite `employees` table is authoritative. Startup never imports replacement/default users from a stale JSON file into that store. Missing, empty or admin-less stores fail visibly for review. Eligible active profiles retain names, roles, departments and identifiers; archived accounts remain archived. Existing `users.json` continues as the synchronized mirror and initial legacy bootstrap input.

Optional `data_dir` in `backend/config.json` resolves from the project root, independently of the shell's working directory; the database filename remains `monthly_cycle.db`. The backend, launcher and backup tool use the same resolver. Startup logs the absolute database path and environment; health checks verify a storage identifier without disclosing credentials. Existing installations retain their settings.

A **new production installation** now requires explicit initialization after configuring its private PIN and real user profiles:

```powershell
python backend/launcher.py --initialize
# or pass --initialize to START SOMESH ENTERPRISES.bat
```

For an existing installation with a missing database or configuration, review paths and verified backups instead of initializing an empty replacement. A healthy existing instance is reused only when its configured storage identity matches.

See `docs/CRITICAL_SYNC_PROFILE_REPORT.md` for root causes, verified backup/preservation findings, mappings and executed tests.
