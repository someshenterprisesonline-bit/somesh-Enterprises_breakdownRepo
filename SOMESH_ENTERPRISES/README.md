# SOMESH ENTERPRISES · Monthly Cycle app

A small office web app. It runs the monthly cycle: tasks, alerts, approvals, time tracking, the Pipeline timetable, the Dashboard, and the Data Center storage (Master Tracker, Contract Register, Vault).

- **Backend:** Python 3.9+ standard library plus `openpyxl`. There is no framework, no build step and no database server; SQLite is built in.
- **Frontend:** plain HTML, CSS and JavaScript, with no build step. Edit a file, refresh the browser, and you see the change.

## Run it

| On | Do this |
|---|---|
| Windows | Double-click **`START SOMESH ENTERPRISES.bat`**. It installs Python and the packages if needed, then starts the app and opens the browser. |
| Windows, with demo data | Double-click **`reset_demo_data_windows.bat`**. |
| Mac / Linux | `./start.sh` |
| By hand | `pip install -r backend/requirements.txt`, then `python backend/app.py --open` |
| Docker | `docker compose up -d` |

The app opens at **http://localhost:8080**. Sign in by clicking a name. Admins use a PIN, which is `1234` by default; change it in `backend/config.json` → `security`.

Run every command from the **project root** (the folder with the .bat file), not from inside `backend/`.

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
│   ├── requirements.txt           openpyxl
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
3. Live alerts come over `/stream` (Server-Sent Events). When something changes, the frontend calls `load()` and redraws the current page with `render()`.

**CODE_MAP.md** lists every page with its frontend file, the backend routes and functions behind it, and examples of typical tasks.

## Working on it

- **Frontend change:** edit the file under `frontend/` and refresh the browser (Ctrl+F5). No restart is needed.
- **Backend change:** edit the file under `backend/`, close the black window, and start the app again.
- **Check JavaScript before committing:** run `node --check frontend/js/pages/<file>.js`, if Node is installed. Otherwise, open the browser console (F12) and look for red errors.
- **Check Python before committing:** run `python -m py_compile backend/app.py`.
- **Test with demo data:** start with `reset_demo_data_windows.bat`. Demo data is visible to admins only, and New bill → Clear demo data removes it.
- **Never commit `data/` or `storage/`.** `.gitignore` already excludes them. Each PC keeps its own database.
- **Watch the shared config files.** The Workflow input page rewrites `backend/workflow.json` and `backend/users.json`. Commit those only when the process change is meant for everyone.

See **GIT_SETUP.md** for the branch-and-pull-request routine, so two people can push at the same time without overwriting each other.
