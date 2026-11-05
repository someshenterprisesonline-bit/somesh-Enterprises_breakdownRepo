# SOMESH ENTERPRISES · Monthly Cycle

A workflow and alerts app built from the **Monthly Cycle** chart. Every stage on the chart is a task:

1. A bill is opened → **Operations** (Moses, Ramya) get an alert: a banner plus a **double beep**.
2. A member presses **Start**, does the work, and presses **Submit** with what they delivered and where the file is.
3. The **checker** for that stage gets an alert, then **approves** or **sends it back** with a reason.
4. On approval the work is **handed over**: the next team's task is created and **they** get the alert.
5. This repeats through the chart until the final stage (**S16 Vault storage**), and the bill is marked complete.

| Rule | Where |
|---|---|
| Several teams start at once | S02 → S03 Worksheet **and** S04 Attendance check; S03 → S05, S06, S08; S09 → S10 and S13 |
| A stage waits for all its inputs | S06 NEFT waits for S03 + S04 · S09 CEO waits for S07 + S08 · S15 Scan waits for S11 + S14 |
| Decision | S04 asks "New candidates?". **Yes** adds S04A New staff details, and S07 then waits for it |
| CEO approval | S09 is owned and checked by M. Sampath, so submitting it approves it |
| Overdue | When a task passes its time limit, the person doing it **and** the checker get a red alert |

The app has a **Walkthrough** tab that shows every step of the manual process and a live "who does what" table.

---

## New in version 2

**Give repeatable tasks by drag and drop (admins).** Pipeline → Timetable shows a **Repeatable tasks** bar above the people (it stays on screen while you scroll). Hover a task to see what it involves, its time limit and whether documents are needed. Drag it onto anyone's name, in any department, and confirm. You can change the hours, the approver or the note in the popup first. If you can't drag (on a touch screen, say), click the task and then click the person. **Edit list** adds, changes or removes repeatable tasks. They are saved in `config.json` under `task_templates`.

**Dashboard page (admins).** It covers 7, 14 or 30 days, this month, or dates you pick, and you can filter by department and person. It shows:
- Headline numbers: hours worked, tasks finished, share of working hours used, idle time, late tasks and tasks sent back.
- Hours per day, stacked by department.
- A person-by-day heatmap.
- Each person's time used against their available hours.
- Idle gaps of 15 minutes or more.
- **Is the time limit right?** For every task, the average actual time against its limit. Over 1.2× the limit means it needs more time or help. Under half the limit means the limit can be cut. The suggested limit is the median actual time × 1.2.
- A suggestions table, the department split, and the tasks that used the most hours.

Hover any bar or cell for exact figures. **Export CSV** downloads the numbers. Working hours come from `config.json` → `workday` (default 09:30–18:30, Monday–Saturday, lunch excluded).

**Delete.** Admins can delete a task they gave, from Assign tasks or by clicking its block on the Pipeline. They can delete a whole bill from its detail panel. Timer records and alerts go with it; files already in storage are kept.

**Downloads are filed locally.** When an admin downloads a task's documents (Tracker, Assign tasks or the task panel), a copy is also saved to
`storage/03 Vault/<Year>/<MM Month>/Tasks/<Department>/<Person>/<Task code> <Task>/`.
A Tracker export is also saved to `storage/01 Master Tracker/<Year>/Daily Time Tracker/`. When the Google Workspace is ready, this folder tree maps one-to-one onto the shared drive.

**All buttons now have a soft shadow**, like the navigation bar.

## 1. Start it (Windows): just double-click

1. **Extract** the zip first (right-click → Extract All), for example to `C:\SomeshEnterprises`. Double-clicking the .bat while it is still inside the zip will not work.
2. Double-click **`START SOMESH ENTERPRISES.bat`**. It:
   - checks for Python 3.9+, and if it's missing installs Python 3.12 (with `winget`, or straight from python.org),
   - checks for the one package the app needs (`openpyxl`, the Excel reader) and installs it if missing,
   - starts the app and opens **http://localhost:8080** in your browser.

   The first run needs internet and takes 1–3 minutes. After that it starts in a few seconds.
3. Pick your name. Click once anywhere so the browser can play the beep, and allow notifications if asked.
4. Keep the black window open. It shows the address for **other office PCs**, for example `http://192.168.1.25:8080`. If Windows asks, allow Python on **Private networks**.

`reset_demo_data_windows.bat` loads the demo bills (admins only) and starts the app; real data is kept.
Mac / Linux: `./start.sh` · Docker: `docker compose up -d`

## Changing the process: the workflow input file

Stages, people and alerts come from one Excel workbook, **`Workflow_Input_Template.xlsx`** (included, and downloadable from the app). It already holds today's Monthly Cycle.

| Sheet | What it controls |
|---|---|
| **Stages** | One row per stage: code, name, department, **Done by** (gets the *New task* alert), **Checked by** (gets *Please check*), **Time limit (hours)** (then *Overdue*), **Next stages**, **Waits for**, **Also waits for (if it ran)**, a **Decision question** with **If Yes / If No also start**, **Output expected**, **Also alert** (extra names copied on new-task and overdue alerts), **Start stage**, **Final stage** |
| **People** | Name, department, role, email (for mail alerts), Admin (can open bills and load the file), Lead |
| **Bills to open** | Optional: a bill is opened for each client when the file is loaded (once per client per month) |
| **Settings** | Time speed (1 = real time, 60 = demo), overdue alert to checker, bill-complete alert to admins |

Load it in the app as an admin (Somesh or M. Sampath): **Workflow input**, then pick one of these:
- **Google Sheet link.** Upload the template to Google Drive, open it with Google Sheets, then Share → *Anyone with the link: Viewer*. Paste the link. You can have the app **re-read it every 5/15/60 minutes**, so editing the sheet changes the process automatically.
- **File path.** Use any path the app's PC can open, for example `G:\Shared drives\Data Center\Workflow_Input.xlsx`.
- **Upload.** Drag the .xlsx onto the page.

**Longer process:** `Workflow_Input_Extended_Demo.xlsx` splits the Monthly Cycle into **37 tasks** (3–4 per department step, for example S01A collect attendance → S01B verify → S01C scan and upload). Load it, then use **Load demo data** to run the demo bills through all 37 tasks. To use it, open **Workflow input**, upload it, tick **Start fresh**, then **Check** and **Apply**. To go back, load `Workflow_Input_Template.xlsx` the same way.

Press **Check** first. The app lists mistakes (unknown names, missing stage codes, two start stages…) and shows what will change. Then press **Apply**. The old definitions are backed up in `data\backups`. The app won't remove a stage while a task is still open at it, and open tasks switch to the new owners and checker.

## Data Center storage: Master Tracker, Contract Register, Vault

See **STORAGE ARCHITECTURE.png** (also shown in the app's **Storage** tab, visible to Data Center and admins).

```
storage\                                   (or any path in config.json → storage.root, e.g. G:\Shared drives\Data Center\SOMESH Storage)
  00 Handoff\<BILL-ID> <Client>\            each team saves its output here and pastes the path on Submit
  01 Master Tracker\2026\Master_Tracker_2026-11.xlsx    Bills · Stage log · Activity, rewritten by the app on every change
  02 Contract Register\Contract_Register.xlsx            Data Center keeps one row per client contract
  02 Contract Register\Contracts\<Client>\<Contract No>.pdf
  03 Vault\2026\11 November\<BILL-ID> <Client>\        filed automatically when the final stage is approved
  03 Vault\Vault_Index.xlsx                              one row per filed bill
```

- **Master Tracker:** the app rewrites one workbook per month whenever anything happens. Sheets: **Bills** (bill × stage status with colours, contract, overdue, vault folder), **Stage log** (who did and checked each stage, times, file path) and **Activity**. Point Power BI or Looker Studio at it. If someone has it open in Excel, the app keeps the old copy, shows a warning on the Storage tab, and updates it when the file is closed (or press **Update Master Tracker now**).
- **Contract Register:** Data Center edits `Contract_Register.xlsx`. Columns: Contract No, Client, Service, Start date, End date, Headcount, Monthly value, Billing day, GST No, Client contact, Contract file, Notes. When a bill is opened, the app looks up the client. If there's **no contract on file** or the contract has **expired**, Data Center gets an alert and the bill is flagged in the Master Tracker.
- **Vault:** when a bill's final stage is approved, the app creates `03 Vault\<Year>\<MM Month>\<BILL-ID> <Client>` and copies in every stage output whose path this PC can open, plus the contract and a `Bill_Summary.xlsx`. It also adds the bill to `Vault_Index.xlsx`. Paths it can't open (for example another PC's drive) are listed in the summary instead.
- **Permissions:** on a shared drive, give *Contributor* to each team on `00 Handoff`, *Viewer* on `01 Master Tracker` and `03 Vault` to everyone except Data Center and the Vault custodian, and edit rights on `02 Contract Register` to Data Center only. Back up the whole root folder daily.
- **Demo:** the dummy data creates 5 sample contracts (one expired: XYZ Hospital), sample files for every stage (attendance and worksheet .xlsx, NEFT and Tally .csv, an EPF ECR .txt, invoice, acknowledgement and challan .pdf) and one bill already filed in the Vault. The demo reset only wipes the `storage` folder next to the app, never a shared-drive path.

## Admin screen

Admins see **My tasks, To check, Tracker, Overview, Pipeline, Activity, Alerts, Assign tasks, Automation**. **Walkthrough, Storage, New bill** (with the demo controls) and **Workflow input** are hidden until the admin adds them with the **＋** at the end of the tab bar. The choice is remembered for each admin on that computer.

**Documents:** in the **Tracker** and on **Assign tasks**, the 📄 button on a task opens its uploaded documents. Each one can be opened in the browser (PDF, images, text), previewed (Excel, CSV) or downloaded, or use **Download all**.

## Time tracker, lunch lock and the staff screen

- **Staff screen:** staff see only **My tasks**. It shows a **Worked today** clock and these sections: **Working now** (with a live timer), **Approved – add documents and end**, **Waiting for approval**, **Up next** and **Finished today**. A **To check** tab appears only when someone has work to check, and Data Center also sees Storage. Alerts open from the 🔔 button and the guide from the **?** button.
- **Timer:** **Start** starts a timer on the task. **Done** (or Submit) stops it. If work is sent back, the timer runs again until it is resent. The lunch break is never counted.
- **Tasks from the admin**, step by step:
  1. Start (timer runs).
  2. **Done – send for approval** (timer stops; the admin gets an alert).
  3. The admin approves.
  4. Only now does the **Documents** box appear. The person uploads, then presses **End task**.
  5. Only then can they start their next task.

  Tick **Needs docs** on the Assign tasks page to make documents compulsory before ending. With automation's *Start tasks automatically* on, the next task starts by itself after End task.
- **Lunch lock:** 1:00–2:00 PM by default. Staff see a lock screen and can't start, finish, upload or end tasks; admins are not locked. Timers don't count it. Change the times or turn it off on the **Tracker** page (or in `config.json → lunch`).
- **Tracker (admins):**
  - Pick a day to see one card per person (worked time, tasks, finished, what they're on now) and every task with its start, done, approved and ended times, worked time, status and document count. Running timers tick live.
  - **Export day (Excel)** downloads 4 sheets: Tasks, Per person, Time log (every timer start and stop) and Notes.
  - A copy is also saved automatically every day to `storage\01 Master Tracker\<year>\Daily Time Tracker\Time_Tracker_<date>.xlsx`.

## Admin control and automation

**Sign-in:** team members pick their name. **Admins** (People sheet: Admin = Yes) also type a **PIN**. The default is `1234`: change it in `config.json → security.admin_pin`, or give each admin their own PIN under `security.pins` (for example `{"Somesh": "4821"}`), then restart. The server reads who someone is from their sign-in, never from the page. Without an admin sign-in, the pipeline, Overview, Activity, bill details, workflow, automation and demo controls are refused.

| Who | Sees |
|---|---|
| Everyone | My tasks, To check, Alerts, Walkthrough, their own and previous teams' hand-off files |
| Data Center | + Storage (Master Tracker, Contract Register, Vault) |
| Admins | + Overview, Pipeline, Activity, bill details, Assign tasks, Automation, New bill, Workflow input |

- **Assign tasks (admins):** give several tasks at once. Each row has the task, who does it (a person, or *anyone in a department*: the first to start takes it), a checker, hours and an optional bill. They follow the same alerts, checks, overdue alerts and files as stage tasks. They show as TASK-001, TASK-002…
- **Automation (admins):**
  - **Start tasks automatically:** gives each new task to the least-busy person in its team and starts it.
  - **Escalate overdue work:** admins get overdue alerts too.
  - **Repeat reminders:** for overdue work, and for checks still waiting.
  - **Open the month's bills:** on a chosen day and hour, for every active contract in the Contract Register. It can also be done now with a button.
- **New bill:** one client per line opens several bills at once.

**Files from each department:** on a started task, **＋ Attach files** uploads any file (up to 50 MB each) into that bill's hand-off folder. The checker and the next team get download links, and spreadsheets, CSV and text files have a **Preview**. In the workflow sheet, **Accepted files** (for example `xlsx, csv`) limits the types for a stage, and **File required = Yes** makes Submit need a file or a path.

**Each department's own workflow sheet:** the reader accepts the department's own column names, for example *Task / Activity*, *Assigned To / Owner*, *Approver / Checker*, *TAT / SLA / Hours*, *Deliverable*, *Depends on*, and sheet names such as *Tasks* or *Staff*. Codes are made up when missing (for example P-01 for Payroll), and rows run one after another when there is no *Next stages* column. Without a People sheet, new names are added as people. To add or replace just that department's stages and keep everything else, tick **Only update the stages in this file**.

## Interface at a glance

| Tab | Who | What it shows |
|---|---|---|
| **My tasks** | Everyone | Your new, in-progress and waiting tasks. Each card has a time bar: blue, then orange **Due soon** (75% of the time used), then red **Overdue** |
| **To check** | Checkers | Work waiting for your approval |
| **Overview** | Everyone (made for leads and the CEO) | Open, completed and overdue counts, where work is waiting by department, the busiest stages, and a progress bar for every bill |
| **Pipeline** | Admins | **Timetable** (default): one row per employee, the hours of the day across the top, a block for every task they worked on, coloured by status (running, waiting for approval, adding documents, done, sent back). It also shows lunch, the current time, each person's status and what's up next. Pick any day. **Bills × stages**: every bill against the stages of the current workflow (the columns follow the workflow), with search, filters and Export CSV |
| **Activity** | Everyone | Every action with its time, searchable by bill, person or stage |
| **Storage** | Data Center, admins | Master Tracker, Contract Register, Vault |

Click any **bill number** (on a task card, in Overview or in Pipeline) to open its detail panel. It shows a stage-by-stage timeline with who did and checked each stage, outputs, rework notes, the contract status, every file in its hand-off and Vault folders (click to open) and its full history. When you submit, **Use this bill's hand-off folder** fills in the right path. On the login screen, type part of your name and press Enter. If the connection to the app PC drops, an orange banner shows until it reconnects.

## 2. Dummy data for testing and demos

The app starts **empty**. To try it, an admin opens **New bill → Demo → Load demo data**. Demo bills are numbered DEMO-…, run 60× faster and are **seen only by admins**. Staff never get their tasks, alerts or files. They are kept in `storage\_Demo data`, out of the real Master Tracker, Vault and daily export. **Clear demo data** removes them, and real bills are never touched by the demo buttons. The demo loads:

| Bill | Where it is |
|---|---|
| BILL-…-001 ABC Industries | Every step done up to **S09**, waiting for M. Sampath's approval |
| BILL-…-002 XYZ Hospital | S04 Attendance check was **sent back** by Nandha (headcount mismatch); S05 and S08 are open |
| BILL-…-003 PQR Logistics | Just arrived, waiting for Operations to start S01 |
| BILL-…-004 Metro Facility Services | Every stage done, filed in the Vault with all sample documents |

`reset_demo_data_windows.bat` (or `python backend/app.py --demo`) reloads the demo bills; real data is kept.

**Live demo in 2 minutes**
1. Open the app in **three browser windows** side by side and log in as **Ramya**, **Somesh** and **Rupashri**.
2. In a fourth window, log in as **Somesh** or **M. Sampath** (admins), open **New bill**, and open a bill for any client. Ramya hears the double beep and sees the alert banner.
3. As Ramya: **Start → Submit**. Sudharsan is alerted to check it.
4. Press **Move one step forward** (or **Auto-play**) and watch the alerts travel team to team. The **Pipeline** tab shows every bill × stage.

Real bills use real-time limits (**Time speed = 1** on the Settings sheet). Demo bills always run 60× faster (1 hour = 1 minute), so their overdue alerts appear within minutes.

## 3. Alerts: what goes where

| Channel | Status | How to turn it on |
|---|---|---|
| **Alert banner + double beep in the app** | On | Works in any modern browser while the app tab is open |
| **Windows / Mac system popup** | On when allowed | Works on `http://localhost` or over **HTTPS**. Browsers block it on plain `http://192.168…` addresses, but the in-app popup and sound still work there. |
| **Email** | Off | `config.json → email.enabled: true`, plus SMTP details (below) and each person's email on the People sheet of the workflow input file |
| **Phone push (ntfy, open source)** | Off | `config.json → ntfy.enabled: true`; each person subscribes to `topic_prefix + their name` in the ntfy app |
| **Webhook** (to n8n, Node-RED, Activepieces, chat tools) | Off | Add URLs to `config.json → webhooks`; every alert is POSTed as JSON |
| **Gather 2.0 office** (inbox trays + alarm lights at team desks) | Off | See **GATHER SETUP (Gather 2.0).md**; paste each Smart Object's URL + secret into `config.json → gather` |

### Email through Google Workspace / Gmail
- **Simplest:** make an alerts mailbox such as `alerts@yourcompany.com`, turn on 2-Step Verification, create an **App password**, then put `smtp.gmail.com`, port `587`, the address and the app password in `config.json`.
- **Workspace admin option:** Admin console → Apps → Google Workspace → Gmail → Routing → **SMTP relay service**. Allow the office IP, then use host `smtp-relay.gmail.com`, port `587`.
- Fill in `email` for each person in `users.json` and set `app_url` to the address people open, so the mail links back to the app.

## 4. Setting it up as the office workspace

```
 Team browsers (any PC/phone on office Wi-Fi)          Google Workspace
   popup + sound, Start / Submit / Approve              ├─ Gmail: alert emails (SMTP relay / app password)
              │  http(s)://alerts.office:8080            └─ Shared drives: the actual files (paths entered on Submit)
              ▼
 ┌──────────────── one always-on PC or small server ────────────────┐
 │  SOMESH ENTERPRISES app (Python)     ── SQLite: data/monthly_cycle.db
 │    ├─ workflow.json  (stages, owners, checkers, time limits)  ← loaded from the workflow input file
 │    ├─ users.json     (people, emails, admins)
 │    └─ overdue checker (every 20 s)
 │  optional: ntfy (phone push) · Caddy (HTTPS) · Docker
 └──────────────────────────────────────────────────────────────────┘
```

1. **Host:** one PC that stays on during office hours, or a small cloud server. Start it with `START SOMESH ENTERPRISES.bat`, or as a Windows service using NSSM, or with `docker compose up -d`.
2. **Address:** give that PC a **fixed IP** on the router, and bookmark `http://<ip>:8080` on every PC.
3. **People:** put everyone's work email in `users.json`. Mark `"admin": true` for whoever opens bills (Operations or Data Center).
4. **Email:** set up the SMTP details as in section 3.
5. **Files:** the app tracks the work, while the files stay in the Google shared drives. Members paste the drive path or Drive link when they submit, and the next team sees it in their task.
6. **Backup:** copy `data\monthly_cycle.db` every day (for example to the Data Center shared drive).
7. **Security:** login is "pick your name", with **no passwords**. That's fine on the office network only. Before putting it on the internet, put it behind HTTPS with a sign-in (for example Cloudflare Access with Google login, or Tailscale), or add Google sign-in to the app.

## 5. Open-source options we looked at

| Need | Option | Licence | Notes |
|---|---|---|---|
| Workflow + alerts (this app) | **SOMESH ENTERPRISES** | yours | One-click start, follows the chart exactly, process defined in an Excel / Google Sheet |
| General automation, approvals by email | **n8n** | Sustainable Use License ("fair-code") | Free to self-host for internal use; good if you later connect many apps |
| | **Activepieces** | MIT (core) | n8n-like, more permissive licence |
| | **Node-RED** | Apache 2.0 | Flow-based; good for wiring webhooks → chat/email |
| Phone / desktop push | **ntfy** | Apache 2.0 / GPLv2 | Built in here (`config.json → ntfy`) |
| Team chat alerts | **Mattermost**, **Rocket.Chat** | open source editions | Receive alerts via the webhook option |
| Virtual office (Gather-style) | **WorkAdventure** | open source (self-host) | Its scripting API can show popups and chat messages in the map; it can be fed from this app's webhook |
| | **Gather** (gather.town) | proprietary | Chat messages from outside only work in Event spaces, but Gather 2.0 **Smart Objects** (signed webhooks) work in offices, and this app drives them |

## 6. Files

The folder layout and which code drives which page are in **README.md** and **CODE_MAP.md** at the top of the project.
In short: `backend/` is the server (Python), `frontend/` is the web page (HTML, CSS, JavaScript), `samples/` holds the example workbooks, and `docs/` holds the guides. `data/` and `storage/` are created on first start and are never committed to git.

Tested end to end: a bill goes through all 16 stages with the correct joins and the S04 decision. The right people get each alert, a rejection loops back to the doer, overdue alerts reach the doer and the checker, and wrong-person actions are refused. Loading an edited workbook (new stage, new person, extra alert names, a bill to open) by upload and by file path applies cleanly. Bad files are refused with a clear list of what to fix.
