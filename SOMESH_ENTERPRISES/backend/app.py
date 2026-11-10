#!/usr/bin/env python3
"""SOMESH ENTERPRISES - Monthly Cycle workflow and alerts app.

Each stage is a task. When a stage is approved, the next team's task is created and its
members get an alert (popup + sound in the browser, and optionally email / ntfy / webhook).
Runs on Python 3.9+ with openpyxl and ReportLab (see requirements.txt).

    python app.py              start the server (http://localhost:8080)
    python app.py --demo       reload dummy bills (keep real bills), then start
    python app.py --template   write samples/Workflow_Input_Template.xlsx from the current definitions

The stages, people and settings can be replaced from an Excel workbook (Google Sheet link, file path,
or upload in the app). See workflow_input.py.
"""
import io, json, os, re, sys, sqlite3, threading, time, queue, smtplib, urllib.request, random, hmac, hashlib, base64, uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import workflow_input as WI
import storage as ST
import excel_workspace as EW
import shutil, secrets, math, gzip, ssl
import lan as LAN

BASE = os.path.dirname(os.path.abspath(__file__))          # backend/  (code + config.json, users.json, workflow.json)
ROOT = os.path.dirname(BASE)                               # project root (data/, storage/, samples/ live here)
FRONTEND = os.path.join(ROOT, "frontend")                  # the web page: index.html, css/, js/, assets/
def load(name):
    path = os.path.join(BASE, name)
    example = os.path.join(BASE, name.replace(".json", ".example.json"))
    if not os.path.isfile(path) and name in ("config.json", "users.json", "workflow.json") and os.path.isfile(example):
        shutil.copyfile(example, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)
def save(name, obj):
    path = os.path.join(BASE, name); tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

CONFIG = load("config.json")
if os.environ.get("SOMESH_ADMIN_PIN"):
    CONFIG.setdefault("security", {})["admin_pin"] = os.environ["SOMESH_ADMIN_PIN"]
NET = LAN.settings(CONFIG)   # office LAN access, sessions and HTTPS (config.json -> network)
FLOW = load("workflow.json")
USERS = load("users.json")["users"]
STAGES = {s["code"]: s for s in FLOW["stages"]}
ORDER = [s["code"] for s in FLOW["stages"]]
USER_NAMES = {u["name"] for u in USERS}
APP_NAME = "SOMESH ENTERPRISES"
APP_VERSION = "2.0"
def speed():
    return max(1, int(FLOW.get("settings", {}).get("demo_speed", CONFIG.get("demo_speed", 1)) or 1))
DEMO_SPEED = 60          # demo bills run 60x faster (1 hour of time limit = 1 minute); real work uses Time speed
DEMO_BUILD = {"on": False}
def is_demo(bill_id):
    if not bill_id: return False
    r = q("SELECT demo FROM bills WHERE id=?", (bill_id,))
    return bool(r and r[0]["demo"])
def demo_ids():
    return {r["id"] for r in q("SELECT id FROM bills WHERE demo=1")}
def setting(key, default=True):
    return FLOW.get("settings", {}).get(key, default)
DB_PATH = os.path.join(ROOT, "data", "monthly_cycle.db")
LOCK = threading.RLock()

def now():
    return datetime.now()
def ts(dt=None):
    return (dt or now()).strftime("%Y-%m-%d %H:%M:%S")

# ------------------------------------------------------------------ database
SCHEMA = """
CREATE TABLE IF NOT EXISTS bills (id TEXT PRIMARY KEY, client TEXT, created_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, bill_id TEXT, stage TEXT, status TEXT,
  owners TEXT, assignee TEXT, validator TEXT, created_at TEXT, due_at TEXT,
  claimed_at TEXT, submitted_at TEXT, decided_at TEXT, output_note TEXT, output_link TEXT,
  branch TEXT, decision_note TEXT, rework_count INTEGER DEFAULT 0, overdue_alerted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, bill_id TEXT, task_id INTEGER, kind TEXT, actor TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS work_log (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, user TEXT, start TEXT, end TEXT);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS adhoc (code TEXT PRIMARY KEY, def TEXT, created_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, kind TEXT, title TEXT, body TEXT, task_id INTEGER, bill_id TEXT, read INTEGER DEFAULT 0, snoozed_until TEXT);
CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, enabled INTEGER DEFAULT 0, trigger TEXT,
  conditions TEXT, actions TEXT, created_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS rule_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id INTEGER, ts TEXT, task_id INTEGER, bill_id TEXT, result TEXT, detail TEXT, trigger TEXT);
"""
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=5000")       # backups and tools may read while the server writes
    c.execute("PRAGMA journal_mode=WAL")        # readers (backup, reports) never block the office's writes
    had_rules = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rules'").fetchone()
    c.executescript(SCHEMA); migrate(c)
    if not had_rules: seed_rules(c)   # first run only: example rules, switched off
    return c
def seed_rules(c):
    by = next((u["name"] for u in USERS if u.get("admin")), "")
    examples = [
        ("Overdue 2 h in any team → alert admins", "task_overdue", {"when": {"minutes": 120}},
         [{"type": "alert", "to": "admins", "message": "{task} for {bill} ({client}) is {minutes} min past its time limit. With: {person}."}]),
        ("Not started after 1 h → start for the least busy person", "task_not_started", {"when": {"hours": 1}},
         [{"type": "start_automatically"}]),
        ("Bill complete → give 'Courier dispatch' to the Operations team", "bill_completed", {},
         [{"type": "give_template", "template": "Courier dispatch", "to": "dept:Operations"}]),
    ]
    for name, trig, cond, acts in examples:
        c.execute("INSERT INTO rules (name,enabled,trigger,conditions,actions,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
                  (name, 0, trig, json.dumps(cond), json.dumps(acts), by, ts()))
    c.commit()
def migrate(c):
    have = {r[1] for r in c.execute("PRAGMA table_info(bills)")}
    for col in ("contract_no", "contract_status", "vault_folder"):
        if col not in have: c.execute(f"ALTER TABLE bills ADD COLUMN {col} TEXT")
    if "demo" not in have: c.execute("ALTER TABLE bills ADD COLUMN demo INTEGER DEFAULT 0")
    tcols = {r[1] for r in c.execute("PRAGMA table_info(tasks)")}
    for col in ("last_reminded", "ended_at"):
        if col not in tcols: c.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
    acols = {r[1] for r in c.execute("PRAGMA table_info(alerts)")}
    if "snoozed_until" not in acols: c.execute("ALTER TABLE alerts ADD COLUMN snoozed_until TEXT")
    rcols = {r[1] for r in c.execute("PRAGMA table_info(rule_runs)")}
    if "trigger" not in rcols: c.execute("ALTER TABLE rule_runs ADD COLUMN trigger TEXT")
    for name, target in INDEXES: c.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")
    c.commit()
# Additive indexes for the queries every signed-in browser repeats (state, tracker, alerts, sessions). Never drop data.
INDEXES = [("ix_tasks_status", "tasks(status)"), ("ix_tasks_bill", "tasks(bill_id)"), ("ix_tasks_assignee", "tasks(assignee)"),
           ("ix_tasks_validator", "tasks(validator, status)"), ("ix_work_log_task", "work_log(task_id)"),
           ("ix_work_log_user", "work_log(user, end)"), ("ix_work_log_start", "work_log(start)"), ("ix_alerts_user", "alerts(user, read)"),
           ("ix_events_bill", "events(bill_id)"), ("ix_events_kind", "events(kind)"), ("ix_sessions_user", "sessions(user)"),
           ("ix_rule_runs_rule", "rule_runs(rule_id)")]
DB = connect()
def q(sql, args=()):
    with LOCK:
        return [dict(r) for r in DB.execute(sql, args).fetchall()]
def x(sql, args=()):
    with LOCK:
        cur = DB.execute(sql, args); DB.commit(); return cur.lastrowid

import employee_management as EM
EM.initialize(globals())

# ------------------------------------------------------------------ live alerts (Server-Sent Events)
SUBS = {}  # user -> [Queue]
BOOT = secrets.token_hex(4)          # lets browsers tell a restarted server's messages apart
_SEQ = [0]; _SEQ_LOCK = threading.Lock()
def stamp(payload):
    if "seq" in payload: return payload
    with _SEQ_LOCK:
        _SEQ[0] += 1; return {**payload, "seq": _SEQ[0], "boot": BOOT}
def push(user, payload):
    payload = stamp(payload)
    for qu in list(SUBS.get(user, [])):
        try: qu.put_nowait(payload)
        except queue.Full: pass
def broadcast(payload):
    payload = stamp(payload)
    for user in list(SUBS):
        push(user, payload)
def push_admins(payload):
    payload = stamp(payload)
    for user in list(SUBS):
        if is_admin(user): push(user, payload)

# Excel Workspace versions written during one POST are announced only after that request succeeds (committed), and
# only to people who can see the document: its owner, admins, and for shared master templates the Excel employees.
EXCEL_TOUCHED = threading.local()
def excel_version_written(book, revision, actor):
    pending = getattr(EXCEL_TOUCHED, "items", None)
    if pending is not None: pending.append((dict(book), int(revision), actor))
def flush_excel_changes(ok):
    items = getattr(EXCEL_TOUCHED, "items", None) or []; EXCEL_TOUCHED.items = None
    if not ok: return
    latest = {}
    for book, rev, actor in items:
        if rev >= latest.get(book["id"], (None, -1, None))[1]: latest[book["id"]] = (book, rev, actor)
    for bid, (book, rev, actor) in latest.items():
        to = {book.get("owner")} | set(admins())
        if book.get("master"): to |= {u["name"] for u in USERS if EW.allowed_employee(globals(), u["name"])}
        msg = stamp({"type": "excel_changed", "id": bid, "revision": rev, "actor": actor})
        for user in to:
            if user: push(user, msg)

# ------------------------------------------------------------------ outside channels
def send_email(user, title, body):
    cfg = CONFIG.get("email", {})
    u = next((u for u in USERS if u["name"] == user), None)
    if not cfg.get("enabled") or not u or not u.get("email"):
        return
    def run():
        try:
            m = EmailMessage(); m["Subject"] = f"[{APP_NAME}] " + title; m["From"] = cfg["from"]; m["To"] = u["email"]
            m.set_content(f"{body}\n\nOpen your tasks: {cfg.get('app_url', '')}\n\n- {APP_NAME}")
            with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=20) as s:
                if cfg.get("use_tls", True): s.starttls()
                if cfg.get("username"): s.login(cfg["username"], cfg["password"])
                s.send_message(m)
        except Exception as e:
            print("email failed:", user, e)
    threading.Thread(target=run, daemon=True).start()

def send_ntfy(user, title, body, priority="default"):
    cfg = CONFIG.get("ntfy", {})
    if not cfg.get("enabled"):
        return
    topic = cfg["topic_prefix"] + "".join(ch for ch in user if ch.isalnum()).lower()
    def run():
        try:
            req = urllib.request.Request(cfg["server"].rstrip("/") + "/" + topic, data=body.encode("utf-8"),
                                         headers={"Title": title.encode("ascii", "ignore").decode(), "Priority": priority, "Tags": "bell"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:
            print("ntfy failed:", user, e)
    threading.Thread(target=run, daemon=True).start()

def send_webhooks(event):
    for url in CONFIG.get("webhooks", []):
        def run(u=url):
            try:
                req = urllib.request.Request(u, data=json.dumps(event).encode(), headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).read()
            except Exception as e:
                print("webhook failed:", u, e)
        threading.Thread(target=run, daemon=True).start()

def alert(users, kind, title, body, task=None, demo=None):
    if demo is None: demo = bool(task and is_demo(task.get("bill_id")))
    for user in dict.fromkeys(users):
        if user not in USER_NAMES:
            continue
        if demo and not is_admin(user): continue      # demo data stays with the admins
        aid = x("INSERT INTO alerts (ts,user,kind,title,body,task_id,bill_id) VALUES (?,?,?,?,?,?,?)",
                (ts(), user, kind, title, body, task["id"] if task else None, task["bill_id"] if task else None))
        push(user, {"type": "alert", "id": aid, "kind": kind, "title": title, "body": body,
                    "task_id": task["id"] if task else None, "ts": ts()})
        send_email(user, title, body)
        send_ntfy(user, title, body, "high" if kind in ("overdue", "rejected") else "default")
    send_webhooks({"kind": kind, "title": title, "body": body, "users": list(users),
                   "task_id": task["id"] if task else None, "bill_id": task["bill_id"] if task else None, "ts": ts()})

def log(bill_id, task_id, kind, actor, text):
    x("INSERT INTO events (ts,bill_id,task_id,kind,actor,text) VALUES (?,?,?,?,?,?)", (ts(), bill_id, task_id, kind, actor, text))
    broadcast({"type": "refresh"}); GATHER_DIRTY.set(); STORAGE_DIRTY.set()


# ------------------------------------------------------------------ Gather 2.0 Smart Objects
# Each Smart Object is one (url, secret) pair copied from the object's menu in Gather. Events are
# Standard Webhooks v1 signed: HMAC-SHA256 over "{webhook-id}.{webhook-timestamp}.{body}".
GATHER_SHOWN = {}          # object name -> set of activity ids currently shown
GATHER_LOCK = threading.Lock()
GATHER_DIRTY = threading.Event()

def gather_send(obj, etype, data=None):
    secret = obj["secret"]
    key = base64.b64decode(secret[6:] if secret.startswith("whsec_") else secret)
    body = json.dumps({"type": etype, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "data": data or {}},
                      separators=(",", ":"))
    if len(body.encode()) > 4096: raise ValueError("Gather caps a message at 4 KB")
    wid = str(uuid.uuid4()); t = str(int(time.time()))
    sig = base64.b64encode(hmac.new(key, f"{wid}.{t}.{body}".encode(), hashlib.sha256).digest()).decode()
    req = urllib.request.Request(obj["url"], data=body.encode(), method="POST", headers={
        "Content-Type": "application/json", "webhook-id": wid, "webhook-timestamp": t, "webhook-signature": "v1," + sig})
    with urllib.request.urlopen(req, timeout=15) as r:
        txt = r.read().decode() or "{}"
        try: return json.loads(txt)
        except ValueError: return {"raw": txt}

def gather_tasks_for(obj):
    open_ = q("SELECT * FROM tasks WHERE status IN ('assigned','in_progress','submitted') ORDER BY due_at")
    out = []
    for t in open_:
        s = sdef(t["stage"]); owners = json.loads(t["owners"])
        if obj.get("dept") and s["dept"] != obj["dept"]: continue
        if obj.get("person"):
            p = obj["person"]
            mine = (t["status"] == "assigned" and p in owners) or (t["status"] == "in_progress" and t["assignee"] == p) or \
                   (t["status"] == "submitted" and t["validator"] == p)
            if not mine: continue
        out.append(t)
    return out

def gather_sync_once():
    cfg = CONFIG.get("gather", {})
    if not cfg.get("enabled"): return
    app_url = CONFIG.get("email", {}).get("app_url", "")
    for obj in cfg.get("objects", []):
        name = obj.get("name") or obj.get("dept") or obj.get("person")
        try:
            tasks = gather_tasks_for(obj)
            late = [t for t in tasks if t["status"] in ("assigned", "in_progress") and t["due_at"] < ts()]
            kind = obj.get("kind", "inbox")
            if kind == "inbox":
                want = {}
                for t in tasks[:20]:
                    st = {"assigned": "NEW", "in_progress": "DOING", "submitted": "TO CHECK"}[t["status"]]
                    who = t["assignee"] or ", ".join(json.loads(t["owners"]))
                    if t["status"] == "submitted": who = "checker " + t["validator"]
                    text = f"{'⚠ LATE · ' if t in late else ''}{st} · {stage_label(t['stage'])} · {t['bill_id']} · {who}"
                    entry = {"id": f"task-{t['id']}-{t['status']}{'-late' if t in late else ''}", "text": text[:500]}
                    if app_url.startswith("http"): entry["url"] = app_url
                    want[entry["id"]] = entry
                with GATHER_LOCK:
                    shown = GATHER_SHOWN.setdefault(name, None)
                if shown is None:      # first sync after start: clear whatever an earlier run left
                    gather_send(obj, "activity.clear"); shown = set()
                for aid in [a for a in shown if a not in want]:
                    gather_send(obj, "activity.remove", {"id": aid}); shown.discard(aid)
                for aid, entry in want.items():
                    if aid not in shown:
                        gather_send(obj, "activity.add", entry); shown.add(aid)
                gather_send(obj, "counter.set", {"count": len(tasks)})
                with GATHER_LOCK: GATHER_SHOWN[name] = shown
            elif kind in ("signal", "status"):
                state = "alert" if late else ("on" if tasks else "off")
                gather_send(obj, kind + ".set", {"state": state})
            elif kind == "switch":
                gather_send(obj, "switch.set_state", {"on": bool(late)})
        except Exception as e:
            print("gather update failed:", name, e)

def gather_loop():
    while True:
        GATHER_DIRTY.wait(timeout=60); GATHER_DIRTY.clear()
        time.sleep(1.0)        # gather bursts of changes into one update
        gather_sync_once()

def gather_test():
    cfg = CONFIG.get("gather", {})
    objs = cfg.get("objects", [])
    if not objs: print("No Gather objects in config.json (gather.objects)."); return
    for obj in objs:
        name = obj.get("name") or obj.get("dept") or obj.get("person")
        try: print("OK  ", name, "->", gather_send(obj, "webhook.ping"))
        except Exception as e: print("FAIL", name, "->", e)

# ------------------------------------------------------------------ Data Center storage (Master Tracker, Contract Register, Vault)
STORAGE_DIRTY = threading.Event()
STORAGE_STATUS = {"tracker_at": "", "error": "", "locked": []}
def storage_on():
    return bool(CONFIG.get("storage", {}).get("enabled", True))
def storage_root():
    r = CONFIG.get("storage", {}).get("root") or "storage"
    return r if os.path.isabs(r) else os.path.join(ROOT, r)
DEMO_DIR = "_Demo data"
def sroot(bill_id=None):
    """Where a bill's files live: demo bills get their own folder, so real storage never holds demo files."""
    return os.path.join(storage_root(), DEMO_DIR) if is_demo(bill_id) else storage_root()
def storage_sync():
    if not storage_on(): return
    try:
        root = storage_root(); ST.ensure(root)
        res = ST.write_master_tracker(root, q("SELECT * FROM bills WHERE demo=0 OR demo IS NULL"), q("SELECT * FROM tasks"),
                                      q("SELECT * FROM events ORDER BY id"), STAGES, ORDER, ts())
        if demo_ids():
            droot = os.path.join(root, DEMO_DIR); ST.ensure(droot)
            ST.write_master_tracker(droot, q("SELECT * FROM bills WHERE demo=1"), q("SELECT * FROM tasks"), q("SELECT * FROM events ORDER BY id"), STAGES, ORDER, ts())
        daily = os.path.join(root, ST.TRACKER, now().strftime("%Y"), "Daily Time Tracker"); os.makedirs(daily, exist_ok=True)
        fp = os.path.join(daily, f"Time_Tracker_{now():%Y-%m-%d}.xlsx"); tmp = fp + ".tmp.xlsx"
        with open(tmp, "wb") as f: f.write(tracker_xlsx(now().date()))
        try: os.replace(tmp, fp)
        except PermissionError: os.remove(tmp); res = list(res) + [(fp, False)]
        STORAGE_STATUS.update(tracker_at=ts(), error="", locked=[os.path.basename(p) for p, ok in res if not ok])
    except Exception as e:
        STORAGE_STATUS["error"] = str(e); print("storage update failed:", e)
def storage_loop():
    while True:
        STORAGE_DIRTY.wait(timeout=120); STORAGE_DIRTY.clear()
        time.sleep(1.5)        # one rewrite for a burst of changes
        storage_sync()
def storage_contract_check(bill_id, client):
    if not storage_on(): return
    try:
        root = sroot(bill_id); ST.ensure(root)
        c, status = ST.contract_for(root, client)
        x("UPDATE bills SET contract_no=?, contract_status=? WHERE id=?", ((c or {}).get("Contract No", ""), status, bill_id))
        if status != "Active":
            dc = [u["name"] for u in USERS if "data center" in u.get("dept", "").lower()]
            alert(dc, "rejected", f"Contract check: {client}",
                  f"{bill_id} was opened for {client}, but the Contract Register shows: {status}. Update {ST.REG_FILE}.", demo=is_demo(bill_id))
            log(bill_id, None, "contract", "System", f"Contract check for {client}: {status}")
    except Exception as e:
        print("contract check failed:", e)
def storage_archive(bill_id):
    if not storage_on(): return
    try:
        root = sroot(bill_id); ST.ensure(root)
        b = q("SELECT * FROM bills WHERE id=?", (bill_id,))[0]
        c, _ = ST.contract_for(root, b["client"])
        folder, copied, missing = ST.archive_bill(root, b, bill_tasks(bill_id), STAGES, c)
        rel = os.path.relpath(folder, storage_root()).replace(os.sep, "/")
        x("UPDATE bills SET vault_folder=? WHERE id=?", (rel, bill_id))
        log(bill_id, None, "vault", "System", f"{bill_id} filed in the Vault: {rel} ({len(copied)} files"
            + (f", {len(missing)} not reachable" if missing else "") + ")")
    except Exception as e:
        print("vault filing failed:", e); log(bill_id, None, "vault", "System", f"Vault filing failed: {e}")
def demo_link(bill_id, code):
    if not storage_on(): return rf"G:\Shared drives\00 Handoff\To_next\{bill_id}_{code}"
    if code not in STAGES or not bill_id:   # a task the admin gave: a small sample note in its own hand-off folder
        d = sdef(code); folder = task_folder({"bill_id": bill_id, "stage": code}); os.makedirs(folder, exist_ok=True)
        ST.pdf(os.path.join(folder, f"{code} {ST.safe(d['name'])}.pdf"), d["name"], [f"Done for: {d.get('given_by', 'admin')}", f"Output: {d['output']}"])
        return folder
    client = q("SELECT client FROM bills WHERE id=?", (bill_id,))[0]["client"]
    return ST.sample_output(sroot(bill_id), bill_id, client, code, STAGES[code])

# ------------------------------------------------------------------ time tracking (timer per task, lunch excluded)
# Each Start opens a time segment in work_log; Done (submit) closes it; a rework reopens one. Worked time = the segments
# minus the lunch break (config.json -> lunch, 13:00-14:00 by default), which is also locked for everyone except admins.
def lunch_cfg():
    return CONFIG.setdefault("lunch", {"enabled": True, "start": "13:00", "end": "14:00"})
def lunch_window(day):
    c = lunch_cfg()
    if not c.get("enabled", True): return None
    a = datetime.combine(day, datetime.strptime(c.get("start", "13:00"), "%H:%M").time())
    b = datetime.combine(day, datetime.strptime(c.get("end", "14:00"), "%H:%M").time())
    return (a, b) if b > a else None
def is_lunch(dt=None):
    dt = dt or now(); w = lunch_window(dt.date())
    return bool(w and w[0] <= dt < w[1])
def pdt(v):
    return datetime.strptime(v, "%Y-%m-%d %H:%M:%S") if isinstance(v, str) else v
def net_seconds(a, b, lo=None, hi=None):
    """Seconds between a and b (clipped to lo..hi when given), minus every lunch break inside."""
    a, b = pdt(a), pdt(b)
    if lo: a = max(a, lo)
    if hi: b = min(b, hi)
    if b <= a: return 0
    total = (b - a).total_seconds(); d = a.date()
    while d <= b.date():
        w = lunch_window(d)
        if w: total -= max(0, (min(b, w[1]) - max(a, w[0])).total_seconds())
        d += timedelta(days=1)
    return max(0, int(total))
def timer_start(tid, user):
    if not q("SELECT id FROM work_log WHERE task_id=? AND end IS NULL", (tid,)):
        x("INSERT INTO work_log (task_id,user,start) VALUES (?,?,?)", (tid, user, ts()))
def timer_stop(tid):
    x("UPDATE work_log SET end=? WHERE task_id=? AND end IS NULL", (ts(), tid))
def worked(tid, lo=None, hi=None):
    """(closed seconds, start of the running segment or None) for a task, optionally only inside lo..hi."""
    done, running = 0, None
    for w in q("SELECT * FROM work_log WHERE task_id=?", (tid,)):
        if w["end"]: done += net_seconds(w["start"], w["end"], lo, hi)
        else: running = w["start"]
    return done, running
def is_tracked_adhoc(t):
    return bool(sdef(t["stage"]).get("adhoc"))
def adhoc_busy(user, except_id=None):
    """The admin-given task this person must finish (end) before starting another, if any."""
    for t in q("SELECT * FROM tasks WHERE stage LIKE 'TASK-%' AND assignee=? AND (status IN ('in_progress','submitted') "
               "OR (status='approved' AND ended_at IS NULL)) ORDER BY id", (user,)):
        if t["id"] != except_id: return t
    return None
def end_task(tid, actor):
    t = get_task(tid); d = sdef(t["stage"])
    if not d.get("adhoc"): raise FlowError("Only tasks given by an admin are ended this way")
    if t["assignee"] != actor: raise FlowError("Only the person who did this task can end it")
    if t["status"] != "approved" or t["ended_at"]: raise FlowError("The admin has to approve it first")
    if d.get("needs_docs") and not task_files(t): raise FlowError("Upload the documents first; this task needs them")
    x("UPDATE tasks SET ended_at=? WHERE id=?", (ts(), tid))
    n = len(task_files(t))
    log(t["bill_id"] or None, tid, "ended", actor, f"{actor} ended {stage_label(t['stage'])}" + (f" with {n} document{'s' if n != 1 else ''}" if n else ""))
    alert([d.get("given_by") or t["validator"]], "complete", f"Task ended: {d['name']}", f"{actor} ended {t['stage']} {d['name']}" + (f" and uploaded {n} document{'s' if n != 1 else ''}." if n else "."), get_task(tid))
    fire_rules("task_ended", t)
    if auto_cfg().get("auto_start"):   # line up the next one straight away
        nxt = next((n_ for n_ in q("SELECT * FROM tasks WHERE stage LIKE 'TASK-%' AND status='assigned' ORDER BY id") if actor in json.loads(n_["owners"])), None)
        if nxt:
            x("UPDATE tasks SET status='in_progress', assignee=?, claimed_at=? WHERE id=?", (actor, ts(), nxt["id"])); timer_start(nxt["id"], actor)
            alert([actor], "new_task", f"Next task started for you: {sdef(nxt['stage'])['name']}", "Your timer is running.", get_task(nxt["id"]))
            log(nxt["bill_id"] or None, nxt["id"], "started", "Automation", f"{stage_label(nxt['stage'])} started automatically for {actor}")
            fire_rules("task_started", get_task(nxt["id"]))

def tracker(day, demo=False):
    """Every task with time on 'day' (or running now), with the worked time inside that day and in total. Demo tasks only with demo=True."""
    lo = datetime.combine(day, datetime.min.time()); hi = lo + timedelta(days=1); d0 = day.strftime("%Y-%m-%d")
    ids = {r["task_id"] for r in q("SELECT w.task_id FROM work_log w JOIN tasks t ON t.id=w.task_id WHERE w.start < ? AND (w.end IS NULL OR w.end >= ?)", (ts(hi), ts(lo)))}
    ids |= {r["id"] for r in q("SELECT id FROM tasks WHERE substr(submitted_at,1,10)=? OR substr(decided_at,1,10)=? OR substr(ended_at,1,10)=?", (d0, d0, d0))}
    rows, nowdt = [], now()
    for tid in sorted(ids):
        t = get_task(tid); d = sdef(t["stage"])
        if str(t["bill_id"] or "").startswith("DEMO-") and not demo: continue
        day_done, running = worked(tid, lo, hi); tot_done, _ = worked(tid)
        live_day = net_seconds(running, nowdt, lo, hi) if running else 0
        live_tot = net_seconds(running, nowdt) if running else 0
        first = q("SELECT MIN(start) s FROM work_log WHERE task_id=?", (tid,))[0]["s"]
        st = ("Ended" if t["ended_at"] else "Approved - waiting for documents") if d.get("adhoc") and t["status"] == "approved" else \
             {"assigned": "Not started", "in_progress": "Running" if running else "In progress", "submitted": "Waiting for approval",
              "approved": "Approved"}.get(t["status"], t["status"])
        rows.append({"id": tid, "code": t["stage"], "task": d["name"], "type": "Given by " + d.get("given_by", "admin") if d.get("adhoc") else "Workflow stage",
                     "bill": t["bill_id"], "client": (q("SELECT client FROM bills WHERE id=?", (t["bill_id"],)) or [{"client": ""}])[0]["client"] if t["bill_id"] else "",
                     "person": t["assignee"] or ", ".join(json.loads(t["owners"])), "dept": d.get("dept", ""), "checker": t["validator"],
                     "assigned_at": t["created_at"], "started_at": first or t["claimed_at"], "done_at": t["submitted_at"],
                     "approved_at": t["decided_at"] if t["status"] == "approved" else None, "ended_at": t["ended_at"],
                     "status": st, "running_since": running, "day_seconds": day_done + live_day, "total_seconds": tot_done + live_tot,
                     "day_closed": day_done, "total_closed": tot_done, "reworks": t["rework_count"], "files": len(task_files(t)), "docs": task_files(t) or link_files(t["output_link"]), "demo": str(t["bill_id"] or "").startswith("DEMO-")})
    people = {}
    for r in rows:
        p = people.setdefault(r["person"], {"person": r["person"], "dept": r["dept"], "seconds": 0, "tasks": 0, "finished": 0, "running": None})
        p["seconds"] += r["day_seconds"]; p["tasks"] += 1
        if r["status"] in ("Ended", "Approved") or (r["status"].startswith("Approved") and not r["code"].startswith("TASK-")): p["finished"] += 1
        if r["running_since"]: p["running"] = r["task"]
    return {"date": d0, "rows": rows, "people": sorted(people.values(), key=lambda p: -p["seconds"]), "lunch": lunch_cfg(), "server_now": ts(),
            "has_demo": bool(demo_ids())}

def timetable(day, demo=False):
    """Who worked on what, hour by hour, for one day: a row per person with a block per timer segment."""
    lo = datetime.combine(day, datetime.min.time()); hi = lo + timedelta(days=1); nowdt = now(); is_today = day == nowdt.date()
    people = {u["name"]: {"name": u["name"], "dept": u.get("dept", ""), "role": u.get("role", ""), "admin": bool(u.get("admin")),
                          "blocks": [], "seconds": 0, "now": None, "queued": [], "waiting": [], "docs": []} for u in USERS}
    for w in q("SELECT w.*, t.stage, t.bill_id, t.status, t.ended_at FROM work_log w JOIN tasks t ON t.id=w.task_id "
               "WHERE w.start < ? AND (w.end IS NULL OR w.end >= ?) ORDER BY w.start", (ts(hi), ts(lo))):
        dm = str(w["bill_id"] or "").startswith("DEMO-")
        if dm and not demo or w["user"] not in people: continue
        d = sdef(w["stage"]); end = pdt(w["end"]) if w["end"] else min(nowdt, hi)
        if w["end"] is None: st = "Running"
        elif w["status"] == "submitted": st = "Waiting for approval"
        elif w["status"] == "approved": st = "Approved - add documents" if d.get("adhoc") and not w["ended_at"] else "Done"
        elif w["status"] == "in_progress": st = "Sent back"
        else: st = w["status"]
        people[w["user"]]["blocks"].append({"task_id": w["task_id"], "code": w["stage"], "task": d["name"], "bill": w["bill_id"], "demo": dm,
                                            "start": ts(max(pdt(w["start"]), lo)), "end": ts(min(end, hi)), "running": w["end"] is None, "status": st,
                                            "seconds": net_seconds(w["start"], end, lo, hi)})
        people[w["user"]]["seconds"] += net_seconds(w["start"], end, lo, hi)
    for t in q("SELECT * FROM tasks WHERE status IN ('assigned','in_progress','submitted') OR (status='approved' AND stage LIKE 'TASK-%' AND ended_at IS NULL) ORDER BY id"):
        if str(t["bill_id"] or "").startswith("DEMO-") and not demo: continue
        d = sdef(t["stage"]); item = {"code": t["stage"], "task": d["name"], "bill": t["bill_id"]}
        if t["status"] == "assigned":
            for o in json.loads(t["owners"]):
                if o in people: people[o]["queued"].append(item)
        elif t["assignee"] in people:
            p_ = people[t["assignee"]]
            if t["status"] == "in_progress" and q("SELECT id FROM work_log WHERE task_id=? AND end IS NULL", (t["id"],)): p_["now"] = item
            elif t["status"] == "submitted": p_["waiting"].append(item)
            elif t["status"] == "approved": p_["docs"].append(item)
            elif t["status"] == "in_progress": p_["queued"].insert(0, {**item, "sent_back": True})
    rows = list(people.values())
    hours = [pdt(b["start"]).hour for r in rows for b in r["blocks"]] + [pdt(b["end"]).hour + 1 for r in rows for b in r["blocks"]]
    start_h = min([9] + hours); end_h = max([19] + hours + ([nowdt.hour + 1] if is_today else []))
    order = {u["dept"]: i for i, u in enumerate(USERS)}
    rows.sort(key=lambda r: (r["admin"] and r["dept"] == "Executive Office", order.get(r["dept"], 99), r["name"]))
    lw = lunch_window(day)
    return {"date": day.strftime("%Y-%m-%d"), "people": rows, "start_hour": max(0, start_h), "end_hour": min(24, end_h), "today": is_today,
            "lunch": [ts(lw[0]), ts(lw[1])] if lw else None, "server_now": ts(), "has_demo": bool(demo_ids())}

def hm(sec):
    sec = int(sec or 0); return f"{sec // 3600}:{sec % 3600 // 60:02d}"
# ------------------------------------------------------------------ v2: templates, delete, filing, dashboard
DEFAULT_TEMPLATES = [
    {"name": "Scan and upload documents", "hours": 1, "docs": True, "about": "Scan the papers given and upload them as PDF."},
    {"name": "Data entry in master tracker", "hours": 1.5, "docs": False, "about": "Enter the day's bills and payments in the Master Tracker."},
    {"name": "File physical copies", "hours": 1, "docs": False, "about": "Sort and file the paper copies in the right box or cabinet."},
    {"name": "Photocopy and bind bill set", "hours": 0.5, "docs": False, "about": "Copy, bind and label the bill set for delivery."},
    {"name": "Courier dispatch", "hours": 1, "docs": True, "about": "Book the courier, hand over, upload the receipt."},
    {"name": "Follow-up call to client", "hours": 0.5, "docs": False, "about": "Call the client about payment or pending papers; note the outcome."},
    {"name": "Update attendance register", "hours": 1, "docs": False, "about": "Bring the attendance register up to date from the latest sheets."},
    {"name": "Email daily report", "hours": 0.5, "docs": False, "about": "Send the day's summary report to the lead."},
]
def templates():
    return CONFIG.setdefault("task_templates", [dict(t) for t in DEFAULT_TEMPLATES])

def delete_task(tid, actor):
    """Admins delete a task they gave (any status). Its time records and alerts go; uploaded files stay in storage."""
    t = get_task(tid)
    if not t["stage"].startswith("TASK-"):
        raise FlowError("This is a stage of a bill. Delete the whole bill from its detail panel instead.")
    with LOCK:
        for sql in ("DELETE FROM work_log WHERE task_id=?", "DELETE FROM alerts WHERE task_id=?", "DELETE FROM tasks WHERE id=?"):
            DB.execute(sql, (tid,))
        DB.commit()
    log(t["bill_id"] or None, None, "deleted", actor, f"{actor} deleted {stage_label(t['stage'])}" + (f" ({t['assignee']})" if t["assignee"] else ""))
    who = [t["assignee"]] if t["assignee"] else json.loads(t["owners"])
    for u in who: push(u, {"type": "refresh"})

def delete_bill(bill_id, actor):
    if not q("SELECT id FROM bills WHERE id=?", (bill_id,)): raise FlowError("Bill not found")
    tids = [r["id"] for r in q("SELECT id FROM tasks WHERE bill_id=?", (bill_id,))]
    with LOCK:
        for tid in tids:
            DB.execute("DELETE FROM work_log WHERE task_id=?", (tid,)); DB.execute("DELETE FROM alerts WHERE task_id=?", (tid,))
        DB.execute("DELETE FROM tasks WHERE bill_id=?", (bill_id,)); DB.execute("DELETE FROM alerts WHERE bill_id=?", (bill_id,))
        DB.execute("DELETE FROM bills WHERE id=?", (bill_id,)); DB.commit()
    log(None, None, "deleted", actor, f"{actor} deleted bill {bill_id} and its {len(tids)} tasks")
    broadcast({"type": "refresh"})

def file_task_docs(tid):
    """Copy a task's documents into the local storage, by department and person (until the Google workspace is set up):
    03 Vault/<Year>/<MM Month>/Tasks/<Department>/<Person>/<code> <task>/"""
    if not storage_on(): raise FlowError("Storage is turned off")
    t = get_task(tid); d = sdef(t["stage"]); files = task_files(t) or link_files(t["output_link"])
    if not files: raise FlowError("This task has no documents")
    when = pdt(t["ended_at"] or t["decided_at"] or t["submitted_at"] or ts())
    person = t["assignee"] or (json.loads(t["owners"]) or ["Unassigned"])[0]
    dept = next((u.get("dept") for u in USERS if u["name"] == person), d.get("dept", "")) or "No department"
    root = sroot(t["bill_id"])
    folder = os.path.join(root, ST.VAULT, when.strftime("%Y"), when.strftime("%m %B"), "Tasks", ST.safe(dept), ST.safe(person),
                          f"{t['stage']} {ST.safe(d['name'])}")
    os.makedirs(folder, exist_ok=True)
    for f in files: shutil.copy2(os.path.join(storage_root(), f["path"]), os.path.join(folder, f["name"]))
    rel = os.path.relpath(folder, storage_root()).replace(os.sep, "/")
    log(t["bill_id"] or None, tid, "filed", "System", f"Documents of {stage_label(t['stage'])} saved to {rel}")
    return rel, len(files)

def workday_cfg():
    return CONFIG.setdefault("workday", {"start": "09:30", "end": "18:30", "days": [0, 1, 2, 3, 4, 5]})
def available_seconds(day):
    c = workday_cfg()
    if day.weekday() not in c.get("days", [0, 1, 2, 3, 4, 5]): return 0
    a = datetime.combine(day, datetime.strptime(c["start"], "%H:%M").time()); b = datetime.combine(day, datetime.strptime(c["end"], "%H:%M").time())
    return net_seconds(a, b)

def dashboard(d_from, d_to, demo=False):
    """Day-by-day breakdown of everyone's work, and the gaps: tasks over / well under their time limit, and idle time."""
    lo = datetime.combine(d_from, datetime.min.time()); hi = datetime.combine(d_to, datetime.min.time()) + timedelta(days=1)
    nowdt = now(); days = [d_from + timedelta(days=i) for i in range((d_to - d_from).days + 1)]
    segs = []
    for w in q("SELECT w.*, t.stage, t.bill_id, t.status, t.rework_count, t.created_at, t.due_at, t.submitted_at, t.decided_at, t.ended_at "
               "FROM work_log w JOIN tasks t ON t.id=w.task_id WHERE w.start < ? AND (w.end IS NULL OR w.end >= ?) ORDER BY w.start", (ts(hi), ts(lo))):
        if str(w["bill_id"] or "").startswith("DEMO-") and not demo: continue
        segs.append(w)
    people = {u["name"]: {"name": u["name"], "dept": u.get("dept", ""), "admin": bool(u.get("admin")), "days": {d.strftime("%Y-%m-%d"): 0 for d in days},
                          "worked": 0, "tasks": set(), "finished": 0, "gaps": [], "active_days": set()} for u in USERS}
    by_task = {}
    for w in segs:
        if w["user"] not in people: continue
        p = people[w["user"]]; end = pdt(w["end"]) if w["end"] else nowdt
        for d in days:
            a = datetime.combine(d, datetime.min.time()); sec = net_seconds(w["start"], end, a, a + timedelta(days=1))
            if sec: p["days"][d.strftime("%Y-%m-%d")] += sec; p["worked"] += sec; p["active_days"].add(d.strftime("%Y-%m-%d"))
        p["tasks"].add(w["task_id"])
    # per task (whole task, not only inside the period) for the time-limit comparison
    tids = {w["task_id"] for w in segs}
    for tid in tids:
        t = get_task(tid); d = sdef(t["stage"]); done, running = worked(tid)
        total = done + (net_seconds(running, nowdt) if running else 0)
        finished = t["status"] == "approved" and (t["ended_at"] or not d.get("adhoc"))
        late = bool(t["due_at"] and (t["submitted_at"] or ts()) > t["due_at"])
        k = d["name"]; e = by_task.setdefault(k, {"task": k, "dept": d.get("dept", ""), "limit_h": float(d.get("sla_hours") or 0), "n": 0, "secs": [], "late": 0, "rework": 0, "adhoc": bool(d.get("adhoc"))})
        e["n"] += 1; e["rework"] += t["rework_count"] or 0; e["late"] += 1 if late else 0
        if finished: e["secs"].append(total)
        if t["assignee"] in people and finished: people[t["assignee"]]["finished"] += 1
    gaps = []
    for e in by_task.values():
        if not e["secs"]: continue
        srt = sorted(e["secs"]); med = srt[len(srt) // 2]; avg = sum(srt) / len(srt)
        ratio = (avg / 3600) / e["limit_h"] if e["limit_h"] else None
        verdict = "over" if ratio and ratio > 1.2 else "generous" if ratio is not None and ratio < 0.5 else "ok"
        gaps.append({"task": e["task"], "dept": e["dept"], "count": len(srt), "avg_h": round(avg / 3600, 2), "median_h": round(med / 3600, 2),
                     "limit_h": e["limit_h"], "ratio": round(ratio, 2) if ratio else None, "verdict": verdict,
                     "suggest_h": max(0.25, round(med / 3600 * 1.2 * 4) / 4), "late": e["late"], "rework": e["rework"], "total_h": round(sum(srt) / 3600, 2)})
    gaps.sort(key=lambda g: -(g["ratio"] or 0))
    # idle gaps inside the working window, per person per worked day
    c = workday_cfg()
    for name, p in people.items():
        mine = [w for w in segs if w["user"] == name]
        for ds in p["active_days"]:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            a = datetime.combine(d, datetime.strptime(c["start"], "%H:%M").time()); b = datetime.combine(d, datetime.strptime(c["end"], "%H:%M").time())
            if d == nowdt.date(): b = min(b, nowdt)
            iv = sorted((max(pdt(w["start"]), a), min(pdt(w["end"]) if w["end"] else nowdt, b)) for w in mine
                        if pdt(w["start"]) < b and (pdt(w["end"]) if w["end"] else nowdt) > a)
            cur = a
            for s0, e0 in iv + [(b, b)]:
                if s0 > cur:
                    g = net_seconds(cur, s0)
                    if g >= 15 * 60: p["gaps"].append({"day": ds, "from": ts(cur)[11:16], "to": ts(s0)[11:16], "secs": g})
                cur = max(cur, e0)
    out_people = []
    for p in people.values():
        avail = sum(available_seconds(datetime.strptime(ds, "%Y-%m-%d").date()) for ds in p["active_days"])
        idle = sum(g["secs"] for g in p["gaps"])
        out_people.append({"name": p["name"], "dept": p["dept"], "admin": p["admin"], "worked": p["worked"], "tasks": len(p["tasks"]), "finished": p["finished"],
                           "active_days": len(p["active_days"]), "available": avail, "utilisation": round(p["worked"] / avail, 3) if avail else 0,
                           "idle": idle, "days": p["days"], "longest_gap": max(p["gaps"], key=lambda g: g["secs"]) if p["gaps"] else None})
    depts = {}
    for p in out_people: depts[p["dept"]] = depts.get(p["dept"], 0) + p["worked"]
    late = sum(e["late"] for e in by_task.values()); rework = sum(e["rework"] for e in by_task.values())
    finished = sum(p["finished"] for p in out_people); worked_total = sum(p["worked"] for p in out_people)
    return {"from": d_from.strftime("%Y-%m-%d"), "to": d_to.strftime("%Y-%m-%d"), "days": [d.strftime("%Y-%m-%d") for d in days],
            "people": out_people, "gaps": gaps, "depts": [{"dept": k, "secs": v} for k, v in sorted(depts.items(), key=lambda x: -x[1]) if v],
            "totals": {"worked": worked_total, "finished": finished, "tasks": len(tids), "late": late, "rework": rework,
                       "avg_task": (sum(sum(e["secs"]) for e in by_task.values()) / max(1, sum(len(e["secs"]) for e in by_task.values()))),
                       "available": sum(p["available"] for p in out_people), "idle": sum(p["idle"] for p in out_people)},
            "workday": c, "has_demo": bool(demo_ids())}

def tracker_xlsx(day):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    tr = tracker(day); wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Tasks"
    head = ["Date", "Person", "Department", "Task code", "Task", "Type", "Bill", "Client", "Checker", "Assigned", "Started", "Done (sent for approval)",
            "Approved", "Ended", "Worked this day (h:mm)", "Worked this day (minutes)", "Worked in total (h:mm)", "Status", "Reworks", "Documents"]
    ws.append(head)
    for r in tr["rows"]:
        ws.append([tr["date"], r["person"], r["dept"], r["code"], r["task"], r["type"], r["bill"], r["client"], r["checker"], r["assigned_at"],
                   r["started_at"], r["done_at"], r["approved_at"], r["ended_at"], hm(r["day_seconds"]), round(r["day_seconds"] / 60),
                   hm(r["total_seconds"]), r["status"], r["reworks"], r["files"]])
    ws2 = wb.create_sheet("Per person"); ws2.append(["Date", "Person", "Department", "Tasks worked on", "Finished", "Worked (h:mm)", "Worked (minutes)", "Working on now"])
    for p_ in tr["people"]:
        ws2.append([tr["date"], p_["person"], p_["dept"], p_["tasks"], p_["finished"], hm(p_["seconds"]), round(p_["seconds"] / 60), p_["running"] or ""])
    ws3 = wb.create_sheet("Time log"); ws3.append(["Task code", "Task", "Person", "Timer started", "Timer stopped", "Minutes (lunch excluded)"])
    lo = datetime.combine(day, datetime.min.time()); hi = lo + timedelta(days=1)
    for w in q("SELECT w.* FROM work_log w JOIN tasks t ON t.id=w.task_id WHERE w.start < ? AND (w.end IS NULL OR w.end >= ?) ORDER BY w.start", (ts(hi), ts(lo))):
        t = get_task(w["task_id"])
        ws3.append([t["stage"], sdef(t["stage"])["name"], w["user"], w["start"], w["end"] or "running", round(net_seconds(w["start"], w["end"] or now(), lo, hi) / 60)])
    lw = lunch_window(day)
    ws4 = wb.create_sheet("Notes"); ws4.append(["Lunch break", f"{lw[0]:%H:%M}-{lw[1]:%H:%M}, not counted and locked" if lw else "off"]); ws4.append(["Exported", ts()])
    for sh in (ws, ws2, ws3):
        for c in sh[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1D1D1F"); c.alignment = Alignment(wrap_text=True, vertical="center")
        sh.freeze_panes = "A2"
        for col in sh.columns: sh.column_dimensions[col[0].column_letter].width = min(40, max(11, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

# ------------------------------------------------------------------ workflow engine
class FlowError(Exception):
    pass

def get_task(tid):
    r = q("SELECT * FROM tasks WHERE id=?", (tid,))
    if not r: raise FlowError("Task not found")
    return r[0]
def bill_tasks(bill_id):
    return q("SELECT * FROM tasks WHERE bill_id=? ORDER BY id", (bill_id,))
ADHOC = {}   # code -> definition of a task the admin gave directly (TASK-001 ...)
def load_adhoc():
    ADHOC.clear(); ADHOC.update({r["code"]: json.loads(r["def"]) for r in q("SELECT * FROM adhoc")})
def sdef(code):
    return STAGES.get(code) or ADHOC.get(code) or {"code": code, "name": code, "dept": "", "owners": [], "validator": "", "sla_hours": 1,
                                                   "next": [], "output": ""}
def stage_label(code):
    s = sdef(code); return f"{code} {s['name']}"

def create_task(bill_id, code, actor="System"):
    s = STAGES[code]
    if q("SELECT id FROM tasks WHERE bill_id=? AND stage=? AND status!='cancelled'", (bill_id, code)):
        return None
    due = now() + timedelta(seconds=s["sla_hours"] * 3600 / (DEMO_SPEED if is_demo(bill_id) else max(1, speed())))
    tid = x("INSERT INTO tasks (bill_id,stage,status,owners,validator,created_at,due_at) VALUES (?,?,?,?,?,?,?)",
            (bill_id, code, "assigned", json.dumps(s["owners"]), s["validator"], ts(), ts(due)))
    started = auto_start(tid)
    t = get_task(tid)
    client = q("SELECT client FROM bills WHERE id=?", (bill_id,))[0]["client"]
    inputs = [f"{stage_label(p['stage'])}: {p['output_note'] or sdef(p['stage'])['output']}"
              for p in bill_tasks(bill_id) if p["status"] == "approved" and code in next_codes(p)]
    body = f"{bill_id} ({client}) is ready for {stage_label(code)}. Time limit {s['sla_hours']} h."
    if inputs: body += " Input: " + "; ".join(inputs)
    if started:
        alert([started] + s.get("cc", []), "new_task", f"New task (started for you): {stage_label(code)}", body, t)
        log(bill_id, tid, "started", "Automation", f"{stage_label(code)} started automatically for {started} (least busy)")
    else:
        alert(s["owners"] + s.get("cc", []), "new_task", f"New task: {stage_label(code)}", body, t)
        log(bill_id, tid, "assigned", actor, f"{stage_label(code)} assigned to {', '.join(s['owners'])}")
    fire_rules("task_assigned", t)
    if started: fire_rules("task_started", t)
    return tid

# ------------------------------------------------------------------ automation
def auto_cfg():
    return CONFIG.setdefault("automation", {"auto_start": False, "remind_every_hours": 0, "escalate_to_admins": False,
                                            "monthly_open_day": 0, "monthly_open_hour": 9, "last_monthly_open": ""})
def auto_start(tid, force=False):
    """Automation: start a new task straight away for the owner with the fewest tasks in progress.
    force=True is used by a rule's "start automatically" action, even when the Auto-start setting is off."""
    if not force and not auto_cfg().get("auto_start"): return None
    t = get_task(tid); owners = [o for o in json.loads(t["owners"]) if o in USER_NAMES]
    if not owners: return None
    if is_tracked_adhoc(t):
        owners = [o for o in owners if not adhoc_busy(o, tid)]   # people still on another admin task wait
        if not owners: return None
    load = {o: q("SELECT COUNT(*) n FROM tasks WHERE status='in_progress' AND assignee=?", (o,))[0]["n"] for o in owners}
    who = min(owners, key=lambda o: (load[o], owners.index(o)))
    x("UPDATE tasks SET status='in_progress', assignee=?, claimed_at=? WHERE id=?", (who, ts(), tid))
    timer_start(tid, who)
    return who
def admins():
    return [u["name"] for u in USERS if u.get("admin")]
def open_bills_for_contracts(actor="Automation"):
    """Open this month's bill for every active contract in the Contract Register (once per client per month)."""
    if not storage_on(): raise FlowError("Storage is turned off, so there is no Contract Register to read")
    month = now().strftime("%Y-%m"); opened = []
    for c in ST.load_register(storage_root()):
        client = str(c.get("Client") or "").strip()
        _, status = ST.contract_for(storage_root(), client)
        if not client or status != "Active": continue
        if q("SELECT id FROM bills WHERE client=? AND created_at LIKE ?", (client, month + "%")): continue
        opened.append(new_bill(client, actor))
    log(None, None, "automation", actor, f"Opened {len(opened)} bills for active contracts" + (": " + ", ".join(opened) if opened else ""))
    return opened
def automation_loop():
    while True:
        time.sleep(30)
        try:
            a = auto_cfg(); day = int(a.get("monthly_open_day") or 0); n = now()
            if day and n.day >= day and n.hour >= int(a.get("monthly_open_hour") or 0) and a.get("last_monthly_open") != n.strftime("%Y-%m"):
                a["last_monthly_open"] = n.strftime("%Y-%m"); save("config.json", CONFIG)
                opened = open_bills_for_contracts()
                alert(admins(), "complete", "Monthly bills opened", f"Automation opened {len(opened)} bills for active contracts.")
        except Exception as e:
            print("automation failed:", e)
        try: rules_tick()          # time-based rules: overdue, not started, every day at
        except Exception as e: print("rules check failed:", e)

# ------------------------------------------------------------------ tasks the admin gives directly
def create_adhoc(title, owners, validator, hours, output, actor, bill_id="", dept="", needs_docs=False):
    owners = [o for o in owners if o in USER_NAMES]
    if not title.strip(): raise FlowError("Write what the task is")
    if not owners: raise FlowError(f"Pick who does '{title}'")
    if validator not in USER_NAMES: raise FlowError(f"Pick who checks '{title}'")
    try:
        hours = float(hours); assert hours > 0
    except Exception: raise FlowError(f"Time limit for '{title}' must be hours above 0")
    if bill_id and not q("SELECT id FROM bills WHERE id=?", (bill_id,)): raise FlowError(f"Bill {bill_id} doesn't exist")
    n = (q("SELECT COUNT(*) n FROM adhoc")[0]["n"] or 0) + 1
    code = f"TASK-{n:03d}"
    while q("SELECT code FROM adhoc WHERE code=?", (code,)): n += 1; code = f"TASK-{n:03d}"
    dept = dept or next((u["dept"] for u in USERS if u["name"] == owners[0]), "")
    d = {"code": code, "name": title.strip(), "dept": dept, "owners": owners, "validator": validator, "sla_hours": hours,
         "next": [], "output": output.strip() or title.strip(), "adhoc": True, "given_by": actor, "needs_docs": bool(needs_docs)}
    x("INSERT INTO adhoc VALUES (?,?,?,?)", (code, json.dumps(d), actor, ts())); ADHOC[code] = d
    due = now() + timedelta(seconds=hours * 3600 / max(1, speed()))
    tid = x("INSERT INTO tasks (bill_id,stage,status,owners,validator,created_at,due_at) VALUES (?,?,?,?,?,?,?)",
            (bill_id or "", code, "assigned", json.dumps(owners), validator, ts(), ts(due)))
    started = auto_start(tid); t = get_task(tid)
    body = f"{actor} gave you: {d['name']}." + (f" Bill {bill_id}." if bill_id else "") + f" Time limit {hours:g} h. Checker: {validator}."
    alert([started] if started else owners, "new_task", f"New task from {actor}: {d['name']}", body, t)
    log(bill_id or None, tid, "assigned", actor, f"{actor} gave {code} {d['name']} to {', '.join([started] if started else owners)}")
    fire_rules("task_assigned", t)
    if started: fire_rules("task_started", t)
    return code

def next_codes(t):
    s = STAGES.get(t["stage"]) or ADHOC.get(t["stage"])
    if not s: return []
    nxt = list(s.get("next", []))
    br = s.get("branch")
    if br and t.get("branch"):
        nxt += br["options"].get(t["branch"], [])
    return nxt

def ready(bill_id, code):
    s = STAGES[code]; tasks = {t["stage"]: t for t in bill_tasks(bill_id) if t["status"] != "cancelled"}
    for r in s.get("requires", []):
        if tasks.get(r, {}).get("status") != "approved": return False, r
    for r in s.get("optional_requires", []):
        if r in tasks and tasks[r]["status"] != "approved": return False, r
    return True, None

def new_bill(client, actor):
    month = now().strftime("%y%m"); pre = "DEMO" if DEMO_BUILD["on"] else "BILL"
    n = len(q("SELECT id FROM bills WHERE id LIKE ?", (f"{pre}-{month}-%",))) + 1
    bill_id = f"{pre}-{month}-{n:03d}"
    while q("SELECT id FROM bills WHERE id=?", (bill_id,)): n += 1; bill_id = f"{pre}-{month}-{n:03d}"
    x("INSERT INTO bills (id, client, created_at, status, demo) VALUES (?,?,?,?,?)", (bill_id, client, ts(), "open", 1 if DEMO_BUILD["on"] else 0))
    log(bill_id, None, "bill", actor, f"{bill_id} opened for {client}")
    storage_contract_check(bill_id, client)
    create_task(bill_id, FLOW["start_stage"], actor)
    fire_rules("bill_opened", bill_id=bill_id)
    return bill_id

def claim(tid, actor):
    t = get_task(tid)
    if actor not in json.loads(t["owners"]): raise FlowError(f"{actor} is not an owner of {t['stage']}")
    if t["status"] not in ("assigned", "rejected"): raise FlowError("This task is not waiting to be started")
    if is_tracked_adhoc(t):
        busy = adhoc_busy(actor, tid)
        if busy: raise FlowError(f"Finish '{sdef(busy['stage'])['name']}' first: once the admin approves it, upload its documents and press End task.")
    x("UPDATE tasks SET status='in_progress', assignee=?, claimed_at=? WHERE id=?", (actor, ts(), tid))
    timer_start(tid, actor)
    others = [o for o in json.loads(t["owners"]) if o != actor]
    if others:
        for o in others: push(o, {"type": "refresh"})
    log(t["bill_id"], tid, "started", actor, f"{actor} started {stage_label(t['stage'])}")
    fire_rules("task_started", t)

def submit(tid, actor, note="", link="", branch=None):
    t = get_task(tid); s = sdef(t["stage"])
    if t["status"] != "in_progress" or t["assignee"] != actor: raise FlowError("Only the person working on this task can submit it")
    if s.get("branch") and branch not in s["branch"]["options"]:
        raise FlowError("Answer: " + s["branch"]["question"])
    files = task_files(t)
    if s.get("file_required") and not s.get("adhoc") and not files and not (link or "").strip():
        raise FlowError(f"{stage_label(t['stage'])} needs a file: attach it, or give the path where it is saved")
    if files and not (link or "").strip(): link = task_folder(t)
    x("UPDATE tasks SET status='submitted', submitted_at=?, output_note=?, output_link=?, branch=? WHERE id=?",
      (ts(), note, link, branch, tid))
    timer_stop(tid)
    log(t["bill_id"], tid, "submitted", actor, f"{actor} submitted {stage_label(t['stage'])} for checking" + (f" (new candidates: {branch})" if branch else ""))
    t = get_task(tid)
    fire_rules("task_submitted", t)
    if t["validator"] == actor:   # e.g. CEO approval: the owner is also the checker
        approve(tid, actor, "Self-approved")
    else:
        alert([t["validator"]], "validate", f"Please check: {stage_label(t['stage'])}",
              f"{actor} finished {stage_label(t['stage'])}" + (f" for {t['bill_id']}" if t['bill_id'] else "") + ". Approve or send it back.", t)

def approve(tid, actor, note=""):
    t = get_task(tid); s = sdef(t["stage"])
    if t["status"] != "submitted": raise FlowError("Only submitted work can be approved")
    if actor != t["validator"]: raise FlowError(f"Only {t['validator']} can approve {t['stage']}")
    x("UPDATE tasks SET status='approved', decided_at=?, decision_note=? WHERE id=?", (ts(), note, tid))
    log(t["bill_id"], tid, "approved", actor, f"{actor} approved {stage_label(t['stage'])}")
    if t["assignee"] and t["assignee"] != actor:
        alert([t["assignee"]], "approved", f"Approved: {stage_label(t['stage'])}",
              (f"{actor} approved it. Upload the documents and press End task to move on." if s.get("adhoc") else f"{actor} approved your work on {t['bill_id']}. A copy goes to the next team."), get_task(tid))
    t = get_task(tid)
    fire_rules("task_approved", t)
    for code in next_codes(t):
        ok, wait = ready(t["bill_id"], code)
        if ok: create_task(t["bill_id"], code, actor)
        else: log(t["bill_id"], None, "waiting", "System", f"{stage_label(code)} waits for {stage_label(wait)}")
    if t["stage"] in FLOW.get("final_stages", []):
        x("UPDATE bills SET status='complete' WHERE id=?", (t["bill_id"],))
        log(t["bill_id"], None, "complete", "System", f"{t['bill_id']} complete - {stage_label(t['stage'])} approved")
        storage_archive(t["bill_id"])
        if setting("complete_to_admins"): alert([u["name"] for u in USERS if u.get("admin")], "complete", f"Bill complete: {t['bill_id']}",
              f"{t['bill_id']} went through every stage and is in the Vault.", t)
        fire_rules("bill_completed", t, bill_id=t["bill_id"])

def reject(tid, actor, note=""):
    t = get_task(tid); s = sdef(t["stage"])
    if t["status"] != "submitted": raise FlowError("Only submitted work can be rejected")
    if actor != t["validator"]: raise FlowError(f"Only {t['validator']} can reject {t['stage']}")
    if not note.strip(): raise FlowError("Write what needs fixing")
    x("UPDATE tasks SET status='in_progress', decision_note=?, rework_count=rework_count+1, submitted_at=NULL WHERE id=?", (note, tid))
    if t["assignee"]: timer_start(tid, t["assignee"])
    log(t["bill_id"], tid, "rejected", actor, f"{actor} sent {stage_label(t['stage'])} back: {note}")
    alert([t["assignee"]], "rejected", f"Rework: {stage_label(t['stage'])}", f"{actor}: {note}", get_task(tid))
    fire_rules("task_sent_back", t)

# ------------------------------------------------------------------ overdue watcher
def overdue_loop():
    while True:
        time.sleep(CONFIG.get("overdue_check_seconds", 20))
        try:
            for t in q("SELECT * FROM tasks WHERE status IN ('assigned','in_progress') AND overdue_alerted=0 AND due_at < ?", (ts(),)):
                s = sdef(t["stage"])
                who = [t["assignee"]] if t["assignee"] else json.loads(t["owners"])
                leads = ([t["validator"]] if setting("overdue_to_checker") else []) + s.get("cc", []) + \
                        (admins() if auto_cfg().get("escalate_to_admins") else [])
                x("UPDATE tasks SET overdue_alerted=1 WHERE id=?", (t["id"],))
                alert(who + leads, "overdue", f"Overdue: {stage_label(t['stage'])}",
                      f"{t['bill_id']} has passed its {s['sla_hours']} h time limit at {stage_label(t['stage'])}.", t)
                log(t["bill_id"], t["id"], "overdue", "System", f"{stage_label(t['stage'])} is overdue")
            remind_loop_once()
        except Exception as e:
            print("overdue check failed:", e)

def remind_loop_once():
    """Automation: repeat a reminder every N hours (demo-scaled) for overdue work and for work waiting for its checker."""
    hrs = float(auto_cfg().get("remind_every_hours") or 0)
    if hrs <= 0: return
    gap = timedelta(seconds=hrs * 3600 / max(1, speed())); cut = ts(now() - gap)
    for t in q("SELECT * FROM tasks WHERE ((status IN ('assigned','in_progress') AND overdue_alerted=1) OR (status='submitted' AND submitted_at < ?)) "
               "AND (last_reminded IS NULL OR last_reminded < ?)", (cut, cut)):
        if t["status"] != "submitted" and not t["last_reminded"] and t["due_at"] > cut: continue   # just went overdue: give it one gap
        x("UPDATE tasks SET last_reminded=? WHERE id=?", (ts(), t["id"]))
        if t["status"] == "submitted":
            alert([t["validator"]], "validate", f"Reminder - please check: {stage_label(t['stage'])}",
                  f"{t['assignee']} is still waiting for your check on {t['bill_id'] or 'this task'}.", t)
        else:
            who = [t["assignee"]] if t["assignee"] else json.loads(t["owners"])
            alert(who, "overdue", f"Reminder - overdue: {stage_label(t['stage'])}", f"{t['bill_id'] or 'This task'} is still overdue.", t)

# ------------------------------------------------------------------ automation rules: When -> If -> Then
# A rule is stored in the rules table: trigger (one of TRIGGERS), conditions JSON (the If part, plus "when" = the
# trigger's own value such as {"minutes": 120}), and actions JSON (the Then part, run in order).
# fire_rules() is called from the workflow (claim, submit, approve, ...) and from automation_loop for the time-based
# triggers. It never raises: a broken rule is written to rule_runs as an error and the normal workflow carries on.
TRIGGERS = {   # id -> (label, scope, value the trigger needs)
    "task_assigned": ("A task is assigned", "task", None),
    "task_started": ("A task is started", "task", None),
    "task_submitted": ("A task is submitted for checking", "task", None),
    "task_approved": ("A task is approved", "task", None),
    "task_sent_back": ("A task is sent back", "task", None),
    "task_ended": ("A task given by an admin is ended", "task", None),
    "task_overdue": ("A task is overdue", "task", {"key": "minutes", "label": "minutes past the limit", "type": "number", "default": 0}),
    "task_not_started": ("A task is not started", "task", {"key": "hours", "label": "hours since assigned", "type": "number", "default": 1}),
    "bill_opened": ("A bill is opened", "bill", None),
    "bill_completed": ("A bill is complete", "bill", None),
    "daily_at": ("Every day at", "time", {"key": "at", "label": "time (HH:MM)", "type": "time", "default": "09:00"}),
}
CONDITIONS = {   # id -> (label, type, which trigger scopes it makes sense for)
    "dept": ("Department is", "dept", ("task",)),
    "person": ("Person is", "person", ("task",)),
    "task_contains": ("Task name contains", "text", ("task",)),
    "stage": ("Stage code is", "stage", ("task",)),
    "client_contains": ("Client contains", "text", ("task", "bill")),
    "rework_min": ("Sent back at least N times", "number", ("task",)),
    "include_demo": ("Include demo data", "bool", ("task", "bill", "time")),
}
ACTIONS = {   # id -> (label, params, needs a task)
    "alert": ("Send an alert", ["to", "message"], False),
    "reassign_least_busy": ("Move it to the least busy person in the same department", [], True),
    "reassign_to": ("Move it to a person", ["person"], True),
    "escalate_admins": ("Escalate to the admins", [], True),
    "give_template": ("Give a repeatable task", ["template", "to"], False),
    "extend_limit": ("Extend the time limit", ["hours"], True),
    "start_automatically": ("Start it for the least busy owner", [], True),
}
PLACEHOLDERS = ("task", "person", "bill", "client", "dept", "minutes")
RULE_LOCK = threading.RLock()
RULE_CTX = threading.local()   # .on is True while a rule's actions run, so they don't fire rules again

def depts():
    return list(dict.fromkeys(u.get("dept", "") for u in USERS if u.get("dept")))
def rule_row(r):
    cond = json.loads(r["conditions"] or "{}")
    return {"id": r["id"], "name": r["name"], "enabled": bool(r["enabled"]), "trigger": r["trigger"], "when": cond.pop("when", {}) or {},
            "conditions": cond, "actions": json.loads(r["actions"] or "[]"), "created_by": r["created_by"], "created_at": r["created_at"]}
def validate_rule(b):
    """Check a rule from the API and return the cleaned version. Raises FlowError with a clear message."""
    if not isinstance(b, dict): raise FlowError("Rule must be an object")
    for key in ("conditions", "when"):
        if key in b and not isinstance(b[key], dict): raise FlowError(f"{key} must be an object")
    if "enabled" in b and not isinstance(b["enabled"], bool): raise FlowError("enabled must be true or false")
    name = str(b.get("name") or "").strip()
    if not name: raise FlowError("Give the rule a name")
    if len(name) > 80: raise FlowError("Keep the rule name under 80 characters")
    trig = b.get("trigger")
    if not isinstance(trig, str) or trig not in TRIGGERS: raise FlowError(f"Unknown trigger '{trig}'. Pick one of: {', '.join(TRIGGERS)}")
    scope, need = TRIGGERS[trig][1], TRIGGERS[trig][2]
    when = {}
    if need:
        raw = (b.get("when") or {}).get(need["key"], need["default"])
        if need["type"] == "time":
            try: datetime.strptime(str(raw), "%H:%M"); assert re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", str(raw))
            except (ValueError, AssertionError): raise FlowError("The daily time must look like 09:30")
            when["at"] = str(raw)
        else:
            try: v = float(raw); assert math.isfinite(v) and v >= 0
            except Exception: raise FlowError(f"'{need['label']}' must be a number of 0 or more")
            if need["key"] == "hours" and v <= 0: raise FlowError("'hours since assigned' must be more than 0")
            when[need["key"]] = v
    cond = {}
    for k, v in (b.get("conditions") or {}).items():
        if v in (None, "", False) and k != "include_demo": continue
        if k not in CONDITIONS: raise FlowError(f"Unknown condition '{k}'. Use: {', '.join(CONDITIONS)}")
        label, typ, scopes = CONDITIONS[k]
        if scope not in scopes and not (k == "include_demo"):
            raise FlowError(f"'{label}' doesn't apply to '{TRIGGERS[trig][0]}': that trigger has no {'task' if scope == 'bill' else 'task or bill'}")
        if typ == "dept":
            if v not in depts(): raise FlowError(f"There is no department called '{v}'. Departments: {', '.join(depts())}")
        elif typ == "person":
            if v not in USER_NAMES: raise FlowError(f"There is nobody called '{v}' in the people list")
        elif typ == "stage":
            v = str(v).strip().upper()
            if v not in STAGES and v not in ADHOC: raise FlowError(f"There is no stage '{v}'. Use a code like {ORDER[0] if ORDER else 'S01'} or TASK-001")
        elif typ == "number":
            try: number = float(v); v = int(number); assert math.isfinite(number) and number == v and v >= 0
            except Exception: raise FlowError(f"'{label}' must be a whole number of 0 or more")
        elif typ == "bool":
            if not isinstance(v, bool): raise FlowError(f"'{label}' must be true or false")
        else:
            v = str(v).strip()[:80]
            if not v: continue
        cond[k] = v
    acts = b.get("actions") or []
    if not isinstance(acts, list) or not acts: raise FlowError("Add at least one action (the Then part)")
    if len(acts) > 10: raise FlowError("Use 10 actions or fewer in one rule")
    clean = []
    for i, a in enumerate(acts, 1):
        if not isinstance(a, dict): raise FlowError(f"Action {i} must be an object")
        typ = a.get("type")
        if not isinstance(typ, str) or typ not in ACTIONS: raise FlowError(f"Action {i}: unknown action '{typ}'. Use: {', '.join(ACTIONS)}")
        label, _, needs_task = ACTIONS[typ]
        if needs_task and scope != "task": raise FlowError(f"Action {i} ('{label}') needs a task, but '{TRIGGERS[trig][0]}' has none")
        c = {"type": typ}
        if typ == "alert":
            to = str(a.get("to") or "").strip(); c["to"] = check_target(to, i, allow=("assignee", "approver", "admins", "department:", "person:"))
            if to in ("assignee", "approver") and scope != "task": raise FlowError(f"Action {i}: '{to}' needs a task, but '{TRIGGERS[trig][0]}' has none")
            msg = str(a.get("message") or "").strip()
            if not msg: raise FlowError(f"Action {i}: write the alert message")
            bad = [p for p in re.findall(r"\{(\w+)\}", msg) if p not in PLACEHOLDERS]
            if bad: raise FlowError(f"Action {i}: unknown placeholder {{{bad[0]}}}. You can use " + " ".join("{" + p + "}" for p in PLACEHOLDERS))
            c["message"] = msg[:500]
        elif typ == "reassign_to":
            p = str(a.get("person") or "").strip()
            if p not in USER_NAMES: raise FlowError(f"Action {i}: there is nobody called '{p}' to move the task to")
            c["person"] = p
        elif typ == "give_template":
            name_ = str(a.get("template") or "").strip()
            if not any(t["name"] == name_ for t in templates()):
                raise FlowError(f"Action {i}: there is no repeatable task called '{name_}'. Repeatable tasks: {', '.join(t['name'] for t in templates())}")
            c["template"] = name_
            to = str(a.get("to") or "").strip().replace("department:", "dept:")
            if to.startswith("person:") and to[7:] in USER_NAMES: c["to"] = to
            elif to.startswith("dept:") and to[5:] in depts(): c["to"] = to
            else: raise FlowError(f"Action {i}: give it to 'person:<name>' or 'dept:<department>' (got '{to or 'nothing'}')")
        elif typ == "extend_limit":
            try: h = float(a.get("hours")); assert 0 < h <= 1000
            except Exception: raise FlowError(f"Action {i}: extend the limit by a number of hours above 0")
            c["hours"] = h
        clean.append(c)
    return {"name": name, "trigger": trig, "when": when, "conditions": cond, "actions": clean}
def check_target(to, i, allow):
    if to in ("assignee", "approver", "admins"): return to
    if to.startswith("department:"):
        if to[11:] not in depts(): raise FlowError(f"Action {i}: there is no department called '{to[11:]}'")
        return to
    if to.startswith("person:"):
        if to[7:] not in USER_NAMES: raise FlowError(f"Action {i}: there is nobody called '{to[7:]}'")
        return to
    raise FlowError(f"Action {i}: send the alert to assignee, approver, admins, department:<name> or person:<name> (got '{to or 'nothing'}')")
def save_rule(b, actor):
    r = validate_rule(b); rid = b.get("id")
    cond = json.dumps(dict(r["conditions"], when=r["when"])); acts = json.dumps(r["actions"])
    if rid:
        if not q("SELECT id FROM rules WHERE id=?", (rid,)): raise FlowError("That rule no longer exists")
        x("UPDATE rules SET name=?, trigger=?, conditions=?, actions=?, enabled=? WHERE id=?",
          (r["name"], r["trigger"], cond, acts, 1 if b.get("enabled") else 0, rid))
        log(None, None, "rule", actor, f"{actor} changed rule '{r['name']}'")
    else:
        rid = x("INSERT INTO rules (name,enabled,trigger,conditions,actions,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
                (r["name"], 1 if b.get("enabled") else 0, r["trigger"], cond, acts, actor, ts()))
        log(None, None, "rule", actor, f"{actor} created rule '{r['name']}'")
    return rule_row(q("SELECT * FROM rules WHERE id=?", (rid,))[0])

def rule_ctx(task=None, bill_id=None, extra=None):
    """The facts a rule looks at: task, person, department, bill, client, demo, minutes past the limit."""
    t = task or {}; bill_id = bill_id or t.get("bill_id") or None
    s = sdef(t["stage"]) if t.get("stage") else {}
    owners = json.loads(t["owners"]) if t.get("owners") else []
    b = q("SELECT client, demo FROM bills WHERE id=?", (bill_id,)) if bill_id else []
    mins = ""
    if t.get("due_at"):
        late = (now() - datetime.strptime(t["due_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
        if late > 0: mins = str(int(late * (DEMO_SPEED if b and b[0]["demo"] else max(1, speed())) // 60))   # in "work" minutes
    c = {"task": stage_label(t["stage"]) if t.get("stage") else "", "task_name": s.get("name", ""), "stage": t.get("stage", ""),
         "person": t.get("assignee") or ", ".join(owners), "assignee": t.get("assignee") or "", "owners": owners,
         "approver": t.get("validator") or "", "dept": s.get("dept", ""), "bill": bill_id or "", "client": b[0]["client"] if b else "",
         "demo": bool(b and b[0]["demo"]), "rework": int(t.get("rework_count") or 0), "minutes": mins}
    c.update(extra or {}); return c
def rule_matches(cond, c):
    if c["demo"] and not cond.get("include_demo"): return False
    if cond.get("dept") and cond["dept"].lower() != (c["dept"] or "").lower(): return False
    if cond.get("person") and not (c["assignee"] == cond["person"] or (not c["assignee"] and cond["person"] in c["owners"])): return False
    if cond.get("task_contains") and cond["task_contains"].lower() not in (c["task_name"] + " " + c["task"]).lower(): return False
    if cond.get("stage") and cond["stage"].upper() != (c["stage"] or "").upper(): return False
    if cond.get("client_contains") and cond["client_contains"].lower() not in (c["client"] or "").lower(): return False
    if cond.get("rework_min") and c["rework"] < int(cond["rework_min"]): return False
    return True
def rule_text(msg, c):
    return re.sub(r"\{(\w+)\}", lambda m: str(c.get(m.group(1), "")) or "-", msg)
def rule_targets(to, c):
    if to == "assignee": return [c["assignee"]] if c["assignee"] else c["owners"]
    if to == "approver": return [c["approver"]] if c["approver"] else []
    if to == "admins": return admins()
    if to.startswith("department:"): return [u["name"] for u in USERS if u.get("dept") == to[11:]]
    if to.startswith("person:"): return [to[7:]]
    return []
def rule_move(t, who, why):
    """Hand a task to someone else (rule actions). Returns a short description."""
    if t["status"] not in ("assigned", "in_progress"): return f"left {t['stage']} with {t['assignee'] or 'its owners'} (it is {t['status']})"
    if is_tracked_adhoc(t) and adhoc_busy(who, t["id"]): raise FlowError(f"{who} must finish their current task before reassignment")
    if t["assignee"] == who: return f"{who} already has it"
    if t["status"] == "in_progress":
        timer_stop(t["id"]); x("UPDATE tasks SET assignee=?, owners=? WHERE id=?", (who, json.dumps([who]), t["id"])); timer_start(t["id"], who)
    else:
        x("UPDATE tasks SET owners=? WHERE id=?", (json.dumps([who]), t["id"]))
    nt = get_task(t["id"])
    alert([who], "new_task", f"Task moved to you: {stage_label(t['stage'])}", f"{why} moved {stage_label(t['stage'])}" + (f" for {t['bill_id']}" if t["bill_id"] else "") + " to you.", nt)
    return f"moved {t['stage']} to {who}"
def least_busy(dept, exclude=None, adhoc_task=None):
    people = [u["name"] for u in USERS if u.get("dept") == dept and u["name"] != exclude]
    if adhoc_task: people = [p for p in people if not adhoc_busy(p, adhoc_task)]
    if not people: return None
    load = {p: q("SELECT COUNT(*) n FROM tasks WHERE status='in_progress' AND assignee=?", (p,))[0]["n"] for p in people}
    return min(people, key=lambda p: (load[p], people.index(p)))
def run_action(a, rule, t, c):
    """Do one action. t is the task row (or None). Returns a short text for the log."""
    why = f"Rule '{rule['name']}'"; typ = a["type"]
    if typ == "alert":
        to = rule_targets(a["to"], c)
        if not to: return f"no one to alert ({a['to']})"
        alert(to, "rule", rule["name"], rule_text(a["message"], c), t or ({"id": None, "bill_id": c["bill"]} if c["bill"] else None), demo=c["demo"])
        return f"alerted {', '.join(dict.fromkeys(to))}"
    if typ == "escalate_admins":
        alert(admins(), "overdue", f"Escalated: {c['task']}", f"{why}: {c['task']}" + (f" for {c['bill']} ({c['client']})" if c["bill"] else "") + f" is with {c['person'] or 'nobody'}" + (f", {c['minutes']} min past its limit" if c["minutes"] else "") + ".", t, demo=c["demo"])
        return "escalated to the admins"
    if typ == "reassign_least_busy":
        who = least_busy(c["dept"], exclude=t["assignee"], adhoc_task=t["id"] if is_tracked_adhoc(t) else None)
        return rule_move(t, who, why) if who else f"nobody else free in {c['dept'] or 'the department'}"
    if typ == "reassign_to": return rule_move(t, a["person"], why)
    if typ == "extend_limit":
        if t["status"] not in ("assigned", "in_progress", "submitted"): return f"{t['stage']} is already {t['status']}"
        scale = DEMO_SPEED if c["demo"] else max(1, speed())
        due = datetime.strptime(t["due_at"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=a["hours"] * 3600 / scale)
        x("UPDATE tasks SET due_at=?, overdue_alerted=0 WHERE id=?", (ts(due), t["id"]))
        return f"extended the time limit by {a['hours']:g} h"
    if typ == "start_automatically":
        if t["status"] != "assigned": return f"{t['stage']} was already {t['status']}"
        who = auto_start(t["id"], force=True)
        if not who: return "nobody free to start it"
        alert([who], "new_task", f"Task started for you: {stage_label(t['stage'])}", f"{why} started it for you. Your timer is running.", get_task(t["id"]))
        return f"started it for {who}"
    if typ == "give_template":
        tpl = next((x_ for x_ in templates() if x_["name"] == a["template"]), None)
        if not tpl: raise FlowError(f"the repeatable task '{a['template']}' no longer exists")
        to = a["to"]; owners = [to[7:]] if to.startswith("person:") else [u["name"] for u in USERS if u.get("dept") == to[5:]]
        by = rule["created_by"] if rule["created_by"] in USER_NAMES else (admins() or [""])[0]
        bill = c["bill"] if c["bill"] and q("SELECT id FROM bills WHERE id=?", (c["bill"],)) else ""
        code = create_adhoc(tpl["name"], owners, by, tpl["hours"], tpl.get("about", ""), by, bill, to[5:] if to.startswith("dept:") else "", tpl.get("docs"))
        return f"gave {code} {tpl['name']} to {to.replace('dept:', 'anyone in ').replace('person:', '')}"
    raise FlowError(f"unknown action {typ}")
def rule_already(rule_id, scope, task_id, bill_id, trigger):
    if scope == "task": return bool(q("SELECT 1 FROM rule_runs WHERE rule_id=? AND task_id=? AND trigger=? LIMIT 1", (rule_id, task_id, trigger)))
    if scope == "bill": return bool(q("SELECT 1 FROM rule_runs WHERE rule_id=? AND bill_id=? AND task_id IS NULL LIMIT 1", (rule_id, bill_id)))
    return bool(q("SELECT 1 FROM rule_runs WHERE rule_id=? AND ts LIKE ? LIMIT 1", (rule_id, now().strftime("%Y-%m-%d") + "%")))
def fire_rules(trigger, task=None, bill_id=None, extra=None, only=None):
    # Serialize the check, actions and run record across workflow and scheduler threads.
    with RULE_LOCK:
        return _fire_rules(trigger, task, bill_id, extra, only)

def _fire_rules(trigger, task=None, bill_id=None, extra=None, only=None):
    """Run every enabled rule for this trigger. Never raises. only = a list of rules (used by the time-based check)."""
    if getattr(RULE_CTX, "on", False): return 0     # actions done by a rule don't trigger rules again
    fired = 0
    try:
        rules = only if only is not None else q("SELECT * FROM rules WHERE enabled=1 AND trigger=? ORDER BY id", (trigger,))
        if not rules: return 0
        scope = TRIGGERS[trigger][1]
        t = get_task(task["id"]) if task and task.get("id") else None    # fresh row
        c = rule_ctx(t, bill_id, extra); bid = c["bill"] or None
        for r in rules:
            tid = t["id"] if (t and scope == "task") else None
            try:
                rr = rule_row(r)
                if rule_already(r["id"], scope, tid, bid, trigger): continue
                if not rule_matches(rr["conditions"], c): continue
                RULE_CTX.on = True
                try: done = [run_action(a, rr, get_task(t["id"]) if t else None, c) for a in rr["actions"]]
                finally: RULE_CTX.on = False
                detail = "; ".join(done); fired += 1
                x("INSERT INTO rule_runs (rule_id,ts,task_id,bill_id,result,detail,trigger) VALUES (?,?,?,?,?,?,?)", (r["id"], ts(), tid, bid, "fired", detail, trigger))
                log(bid, tid, "rule", "Automation", f"Rule '{r['name']}' " + (f"on {c['task']}: " if c["task"] else (f"on {bid}: " if bid else ": ")) + detail)
            except Exception as e:
                RULE_CTX.on = False
                print(f"rule {r['id']} failed:", repr(e))
                try:
                    x("INSERT INTO rule_runs (rule_id,ts,task_id,bill_id,result,detail,trigger) VALUES (?,?,?,?,?,?,?)", (r["id"], ts(), tid, bid, "error", str(e)[:300], trigger))
                    log(bid, tid, "rule", "Automation", f"Rule '{r['name']}' failed: {str(e)[:300]}")
                except Exception: pass
    except Exception as e:
        print("rules failed:", repr(e))
    return fired
def rules_tick():
    """Time-based triggers, checked from automation_loop: task_overdue, task_not_started, daily_at."""
    rules = q("SELECT * FROM rules WHERE enabled=1 AND trigger IN ('task_overdue','task_not_started','daily_at') ORDER BY id")
    if not rules: return
    n = now(); open_tasks = None
    for r in rules:
        try:
            when = json.loads(r["conditions"] or "{}").get("when") or {}
            if r["trigger"] == "daily_at":
                if n.strftime("%H:%M") >= when.get("at", "09:00"): fire_rules("daily_at", only=[r])
                continue
            if open_tasks is None: open_tasks = q("SELECT * FROM tasks WHERE status IN ('assigned','in_progress')")
            demo = demo_ids()
            for t in open_tasks:
                scale = DEMO_SPEED if t["bill_id"] in demo else max(1, speed())
                if r["trigger"] == "task_overdue":
                    due = datetime.strptime(t["due_at"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=float(when.get("minutes") or 0) * 60 / scale)
                    if n < due: continue
                else:
                    if t["status"] != "assigned": continue
                    since = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=float(when.get("hours") or 1) * 3600 / scale)
                    if n < since: continue
                fire_rules(r["trigger"], t, only=[r])
        except Exception as e:
            print(f"rule timer {r['id']} failed:", repr(e))

def rule_test(rid):
    """Dry run: how often would this rule have fired in the last 7 days? Does NOT do any action."""
    r = q("SELECT * FROM rules WHERE id=?", (rid,))
    if not r: raise FlowError("That rule no longer exists")
    rr = rule_row(r[0]); trig = rr["trigger"]; since = now() - timedelta(days=7); hits = []
    kinds = {"task_assigned": ("assigned",), "task_started": ("started",), "task_submitted": ("submitted",), "task_approved": ("approved",),
             "task_sent_back": ("rejected",), "task_ended": ("ended",), "bill_opened": ("bill",), "bill_completed": ("complete",)}
    def add(key, when, c, text):
        if key in seen: return
        seen.add(key); hits.append({"ts": when, "task": c["task"], "person": c["person"], "bill": c["bill"], "client": c["client"], "text": text})
    seen = set()
    if trig in kinds:
        for e in q(f"SELECT * FROM events WHERE ts >= ? AND kind IN ({','.join('?' * len(kinds[trig]))}) ORDER BY id DESC", (ts(since),) + kinds[trig]):
            t = q("SELECT * FROM tasks WHERE id=?", (e["task_id"],)) if e["task_id"] else []
            if TRIGGERS[trig][1] == "task" and not t: continue
            c = rule_ctx(t[0] if t else None, e["bill_id"])
            if rule_matches(rr["conditions"], c): add(e["task_id"] if TRIGGERS[trig][1] == "task" else e["bill_id"], e["ts"], c, e["text"])
    elif trig in ("task_overdue", "task_not_started"):
        demo = demo_ids()
        for t in q("SELECT * FROM tasks ORDER BY id DESC"):
            scale = DEMO_SPEED if t["bill_id"] in demo else max(1, speed())
            if trig == "task_overdue":
                limit = datetime.strptime(t["due_at"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=float(rr["when"].get("minutes") or 0) * 60 / scale)
                done = t["submitted_at"] or t["decided_at"] or ts()
                if datetime.strptime(done, "%Y-%m-%d %H:%M:%S") < limit: continue
                when, text = ts(limit), f"{stage_label(t['stage'])} went {rr['when'].get('minutes', 0):g} min past its limit"
            else:
                limit = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S") + timedelta(seconds=float(rr["when"].get("hours") or 1) * 3600 / scale)
                started = t["claimed_at"] or ts()
                if datetime.strptime(started, "%Y-%m-%d %H:%M:%S") < limit: continue
                when, text = ts(limit), f"{stage_label(t['stage'])} was not started {rr['when'].get('hours', 1):g} h after it was assigned"
            if not ts(since) <= when <= ts(): continue
            c = rule_ctx(t)
            if rule_matches(rr["conditions"], c): add(t["id"], when, c, text)
    elif trig == "daily_at":
        at = rr["when"].get("at", "09:00")
        for i in range(7, -1, -1):
            d = (now() - timedelta(days=i)).strftime("%Y-%m-%d")
            if d + " " + at + ":00" <= ts() and d + " " + at + ":00" >= ts(since): add(d, f"{d} {at}:00", rule_ctx(), f"Every day at {at}")
    hits.sort(key=lambda h: h["ts"], reverse=True)
    return {"rule": rr["name"], "would_fire": len(hits), "examples": hits[:5], "days": 7,
            "note": "Checked against the last 7 days with each task's current details. Nothing was changed."}
def workflow_model(demo=False):
    """Stages with their links, live counts and the rules that apply to each stage."""
    skip = set() if demo else demo_ids(); cur = ts()
    open_ = [t for t in q("SELECT * FROM tasks WHERE status IN ('assigned','in_progress','submitted')") if t["bill_id"] not in skip]
    rules = [rule_row(r) for r in q("SELECT * FROM rules ORDER BY id")]
    out = []
    for s in FLOW["stages"]:
        mine = [t for t in open_ if t["stage"] == s["code"]]
        applies = []
        for r in rules:
            if TRIGGERS.get(r["trigger"], ("", ""))[1] != "task": continue
            cnd = r["conditions"]
            if cnd.get("stage") and cnd["stage"] != s["code"]: continue
            if cnd.get("dept") and cnd["dept"].lower() != s.get("dept", "").lower(): continue
            if cnd.get("person") and cnd["person"] not in s.get("owners", []): continue
            if cnd.get("task_contains") and cnd["task_contains"].lower() not in (s["code"] + " " + s["name"]).lower(): continue
            applies.append({"id": r["id"], "name": r["name"], "enabled": r["enabled"], "trigger": r["trigger"]})
        out.append({"code": s["code"], "name": s["name"], "dept": s.get("dept", ""), "next": s.get("next", []), "branch": s.get("branch"),
                    "owners": s.get("owners", []), "validator": s.get("validator", ""), "sla_hours": s.get("sla_hours"),
                    "counts": {"open": sum(t["status"] in ("assigned", "in_progress") for t in mine),
                               "overdue": sum(t["status"] in ("assigned", "in_progress") and t["due_at"] < cur for t in mine),
                               "waiting_check": sum(t["status"] == "submitted" for t in mine)},
                    "rules": applies})
    return {"start_stage": FLOW.get("start_stage"), "final_stages": FLOW.get("final_stages", []), "stages": out,
            "bill_rules": [{"id": r["id"], "name": r["name"], "enabled": r["enabled"], "trigger": r["trigger"]} for r in rules if TRIGGERS.get(r["trigger"], ("", ""))[1] != "task"]}
def rules_meta():
    return {"rules": [rule_row(r) for r in q("SELECT * FROM rules ORDER BY id")],
            "triggers": [{"id": k, "label": v[0], "scope": v[1], "value": v[2]} for k, v in TRIGGERS.items()],
            "actions": [{"id": k, "label": v[0], "params": v[1], "needs_task": v[2]} for k, v in ACTIONS.items()],
            "conditions": [{"id": k, "label": v[0], "type": v[1], "scopes": list(v[2])} for k, v in CONDITIONS.items()],
            "placeholders": list(PLACEHOLDERS), "alert_targets": ["assignee", "approver", "admins", "department:<name>", "person:<name>"],
            "people": [{"name": u["name"], "dept": u.get("dept", ""), "admin": bool(u.get("admin"))} for u in USERS],
            "departments": depts(), "stages": [{"code": s["code"], "name": s["name"], "dept": s.get("dept", "")} for s in FLOW["stages"]],
            "templates": [t["name"] for t in templates()]}

# ------------------------------------------------------------------ views
def task_folder(t):
    client = (q("SELECT client FROM bills WHERE id=?", (t["bill_id"],)) or [{"client": ""}])[0]["client"] if t["bill_id"] else ""
    s = sdef(t["stage"]); base = f"{t['bill_id']} {ST.safe(client)}" if t["bill_id"] else "Tasks"
    return os.path.join(sroot(t["bill_id"]), ST.HANDOFF, base, f"{t['stage']} {ST.safe(s['name'])}")
def task_files(t):
    if not storage_on(): return []
    d = task_folder(t); root = storage_root()
    if not os.path.isdir(d): return []
    return [{"name": f, "size": os.path.getsize(os.path.join(d, f)), "path": os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/")}
            for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f)) and not f.startswith("~$")]
def link_files(link):
    """Files behind a submitted path, when that path is inside the storage folder (so the next team can open them)."""
    if not storage_on() or not link: return []
    root = os.path.realpath(storage_root()); p = os.path.realpath(link.strip().strip('"'))
    if not p.startswith(root + os.sep): return []
    items = [p] if os.path.isfile(p) else [os.path.join(p, f) for f in sorted(os.listdir(p))] if os.path.isdir(p) else []
    return [{"name": os.path.basename(f), "size": os.path.getsize(f), "path": os.path.relpath(f, root).replace(os.sep, "/")} for f in items if os.path.isfile(f)]
def save_upload(t, name, data):
    if not storage_on(): raise FlowError("Uploads need storage turned on (config.json -> storage.enabled)")
    s = sdef(t["stage"]); ext = os.path.splitext(name)[1].lower().lstrip(".")
    if s.get("accept") and ext not in s["accept"]:
        raise FlowError(f"{stage_label(t['stage'])} takes {', '.join(s['accept'])} files; '{name}' is .{ext or '?'}")
    if len(data) > 50 * 1024 * 1024: raise FlowError("Files up to 50 MB")
    d = task_folder(t); os.makedirs(d, exist_ok=True)
    base, e = os.path.splitext(ST.safe(name)); fn = base + e; i = 2
    while os.path.exists(os.path.join(d, fn)): fn = f"{base} ({i}){e}"; i += 1
    with open(os.path.join(d, fn), "wb") as f: f.write(data)
    return fn

def task_view(t):
    s = sdef(t["stage"])
    d = dict(t); d["owners"] = json.loads(t["owners"]); d["stage_name"] = s["name"]; d["dept"] = s["dept"]
    d["expected_output"] = s["output"]; d["sla_hours"] = s["sla_hours"]
    d["branch_question"] = s.get("branch", {}).get("question"); d["branch_options"] = list(s.get("branch", {}).get("options", {}).keys())
    d["client"] = (q("SELECT client FROM bills WHERE id=?", (t["bill_id"],)) or [{"client": ""}])[0]["client"]
    d["inputs"] = [{"stage": p["stage"], "name": sdef(p["stage"])["name"], "by": p["assignee"], "note": p["output_note"], "link": p["output_link"],
                    "files": link_files(p["output_link"])}
                   for p in bill_tasks(t["bill_id"]) if t["bill_id"] and p["status"] == "approved" and t["stage"] in next_codes(p)]
    d["files"] = task_files(t) or link_files(t["output_link"]); d["accept"] = s.get("accept", []); d["file_required"] = bool(s.get("file_required"))
    d["adhoc"] = bool(s.get("adhoc")); d["given_by"] = s.get("given_by", ""); d["needs_docs"] = bool(s.get("needs_docs"))
    d["worked_seconds"], d["timer_from"] = worked(t["id"])
    return d

def action_center_report(actor, qs):
    from action_center import build_report
    value = lambda key, default="": (qs.get(key) or [default])[0]
    try: day = datetime.strptime(value("date", now().date().isoformat()), "%Y-%m-%d").date()
    except ValueError: raise FlowError("Choose a date in YYYY-MM-DD format")
    if day > now().date(): raise FlowError("Choose today or an earlier date")
    department, person = value("department"), value("person")
    if department and department not in depts(): raise FlowError("Choose an existing department")
    if person and person not in USER_NAMES: raise FlowError("Choose an existing employee")
    workload, sort = value("workload", "all"), value("sort", "attention")
    if workload not in ("all", "overloaded", "no_activity", "open"): raise FlowError("Choose a valid workload filter")
    if sort not in ("attention", "name", "time", "pending"): raise FlowError("Choose a valid workload sort")
    with LOCK:
        return build_report(q("SELECT * FROM tasks"), q("SELECT * FROM work_log"),
                            q("SELECT ts,actor,task_id FROM events WHERE substr(ts,1,10)=?", (day.isoformat(),)),
                            [dict(u) for u in USERS], {t["stage"]: sdef(t["stage"]) for t in q("SELECT DISTINCT stage FROM tasks")},
                            now(), day, dict(workday_cfg()), lunch_window(day), net_seconds, actor,
                            department, person, value("q")[:200], workload, sort)


def action_center_reassign(actor, body):
    if not is_admin(actor): raise Denied("Only admins can reassign tasks")
    if body.get("confirmed") is not True: raise FlowError("Confirm the reassignment first")
    if type(body.get("task_id")) is not int or not 0 < body["task_id"] <= 9223372036854775807:
        raise FlowError("Choose an existing task")
    person, expected = body.get("person"), body.get("expected")
    if not isinstance(person, str) or person not in USER_NAMES: raise FlowError("Choose an existing employee")
    if not isinstance(expected, dict): raise FlowError("Reload the task before reassigning")
    with LOCK:
        t = get_task(body["task_id"])
        current = {k: t[k] for k in ("status", "assignee", "claimed_at")}
        current["owners"] = json.loads(t["owners"])
        if expected != current: raise FlowError("This task changed. Reload it before reassigning")
        if str(t["bill_id"] or "").startswith("DEMO-"): raise FlowError("Demo tasks are excluded from Action Center")
        if t["status"] not in ("assigned", "in_progress"): raise FlowError("Only assigned or running tasks can be reassigned")
        if not any(u["name"] == person and u.get("dept") == sdef(t["stage"]).get("dept") for u in USERS):
            raise FlowError("Choose an employee in this task's department")
        if t["assignee"] == person or (not t["assignee"] and current["owners"] == [person]): raise FlowError("This employee already owns the task")
        detail = rule_move(t, person, actor)
        log(t["bill_id"] or None, t["id"], "reassigned", actor, f"{actor} {detail}")
    return {"ok": True}


# Alert Center: recipient-scoped history, current workflow facts and non-destructive preferences.
def alert_center(user):
    rows = q("SELECT * FROM alerts WHERE user=? AND (bill_id IS NULL OR bill_id NOT LIKE 'DEMO-%') ORDER BY id DESC", (user,))
    tasks = {t["id"]: t for t in q("SELECT * FROM tasks WHERE id IN (SELECT task_id FROM alerts WHERE user=?)", (user,))}
    bills = {b["id"]: b for b in q("SELECT id,client,contract_no,contract_status FROM bills WHERE demo=0 OR demo IS NULL")}
    groups = {}; stamp = ts(); urgent_keys = set(); approval_keys = set()
    counts = {"unread": 0, "total_unread": 0, "urgent": 0, "approvals": 0, "updates": 0, "snoozed": 0, "total": 0}
    for a in rows:
        t = tasks.get(a["task_id"])
        if t and str(t["bill_id"] or "").startswith("DEMO-"): continue
        counts["total"] += 1
        definition = sdef(t["stage"]) if t else {}
        bid = a["bill_id"] or (t["bill_id"] if t else None)
        if not bid and (a["title"] or "").startswith("Contract check:"):
            match = re.search(r"\bBILL-\d{4}-\d+\b", a["body"] or "")
            if match and match[0] in bills: bid = match[0]
        bill = bills.get(bid, {})
        overdue = bool(t and t["status"] in ("assigned", "in_progress") and t["due_at"] and t["due_at"] < stamp)
        workflow_error = bool(a["title"] == "Workflow file has problems" and globals().get("INPUT", {}).get("error"))
        pending = bool(t and t["status"] == "submitted" and t["validator"] == user)
        contract_issue = bool(bill.get("contract_status") and bill["contract_status"] != "Active")
        contract_alert = (a["title"] or "").startswith("Contract check:") and bool(bill)
        compliance = bool(t and "compliance" in definition.get("dept", "").lower() and t["status"] == "in_progress" and t["rework_count"] and t["decision_note"])
        if overdue or workflow_error:
            priority, category, reason = 0, "urgent", ("Past the current task deadline" if overdue else "Workflow input currently has an error")
        elif pending:
            priority, category, reason = 1, "approvals", "Submitted work awaiting your approval"
        elif (contract_alert and contract_issue) or compliance:
            priority, category, reason = 2, "updates", ("Contract status: " + bill["contract_status"] if contract_alert else "Compliance correction requested")
        elif t and a["kind"] == "new_task" and t["status"] in ("assigned", "in_progress"):
            priority, category, reason = 3, "updates", "Task assignment"
        else:
            priority, category, reason = 4, "updates", "Activity update"
        urgent = priority == 0
        snoozed = bool(not urgent and a.get("snoozed_until") and a["snoozed_until"] > stamp)
        key = f"task:{t['id']}:{a['kind']}" if t else f"alert:{a['id']}"
        record = {k: a[k] for k in ("id", "ts", "kind", "title", "body", "read", "snoozed_until")}
        record["snoozed"] = snoozed
        g = groups.setdefault(key, {"key": key, "records": [], "priority": priority, "category": category, "reason": reason,
            "urgent": urgent, "can_review": pending, "is_contract": contract_alert, "bill_id": bid,
            "client": bill.get("client", ""), "contract_no": bill.get("contract_no", ""), "contract_status": bill.get("contract_status", ""),
            "task": {"id": t["id"], "stage": t["stage"], "name": definition.get("name", t["stage"]), "dept": definition.get("dept", ""),
                     "person": t["assignee"] or ", ".join(json.loads(t["owners"])), "validator": t["validator"], "status": t["status"], "due_at": t["due_at"]} if t else None})
        g["records"].append(record)
        if not a["read"]: counts["total_unread"] += 1
        if snoozed: counts["snoozed"] += 1
        else:
            if not a["read"]:
                counts["unread"] += 1
                if category == "updates": counts["updates"] += 1
            if urgent: urgent_keys.add(f"task:{t['id']}" if t else key)
            if pending: approval_keys.add(t["id"])
    result = []
    for g in groups.values():
        g["unread"] = sum(not a["read"] and not a["snoozed"] for a in g["records"])
        g["snoozed"] = all(a["snoozed"] for a in g["records"])
        g["latest"] = next((a for a in g["records"] if not a["snoozed"]), g["records"][0])
        result.append(g)
    result.sort(key=lambda g: (g["priority"], not bool(g["unread"]), -g["latest"]["id"]))
    counts["urgent"], counts["approvals"] = len(urgent_keys), len(approval_keys)
    return {"groups": result, "counts": counts, "server_now": stamp}

def owned_alert_ids(user, body):
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500 or any(type(i) is not int or not 0 < i <= 9223372036854775807 for i in ids):
        raise FlowError("Choose between 1 and 500 alert IDs")
    ids = list(dict.fromkeys(ids)); marks = ",".join("?" for _ in ids)
    if len(q(f"SELECT id FROM alerts WHERE user=? AND id IN ({marks})", (user, *ids))) != len(ids):
        raise Denied("These alerts are not available to your account")
    return ids

def read_alerts(user, body):
    if "ids" not in body:
        x("UPDATE alerts SET read=1 WHERE user=?", (user,))
    else:
        ids = owned_alert_ids(user, body)
        x(f"UPDATE alerts SET read=1 WHERE user=? AND id IN ({','.join('?' for _ in ids)})", (user, *ids))
    push(user, {"type": "alerts_changed"})

def snooze_alerts(user, body):
    if not is_admin(user): raise Denied("Only admins can snooze alerts")
    ids = owned_alert_ids(user, body); minutes = body.get("minutes", 60)
    if type(minutes) is not int or minutes not in (0, 15, 60, 240): raise FlowError("Snooze for 15, 60 or 240 minutes, or use 0 to undo")
    with LOCK:
        center = alert_center(user)
        if minutes and any(g["urgent"] and any(a["id"] in ids for a in g["records"]) for g in center["groups"]):
            raise FlowError("Urgent alerts cannot be snoozed")
        until = ts(now() + timedelta(minutes=minutes)) if minutes else None
        x(f"UPDATE alerts SET snoozed_until=? WHERE user=? AND id IN ({','.join('?' for _ in ids)})", (until, user, *ids))
    push(user, {"type": "alerts_changed"})


def state(user):
    mine = [task_view(t) for t in q("SELECT * FROM tasks WHERE bill_id NOT LIKE 'DEMO-%' AND (status IN ('assigned','in_progress','submitted') OR "
                                    "(status='approved' AND stage LIKE 'TASK-%' AND ended_at IS NULL)) ORDER BY id")
            if user in json.loads(t["owners"]) and (t["status"] == "assigned" or t["assignee"] == user)]
    today = now().date(); lo = datetime.combine(today, datetime.min.time()); d0 = today.strftime("%Y-%m-%d")
    secs = 0
    for w in q("SELECT w.* FROM work_log w JOIN tasks t ON t.id=w.task_id WHERE w.user=? AND t.bill_id NOT LIKE 'DEMO-%' AND (w.end IS NULL OR w.end >= ?)", (user, ts(lo))):
        secs += net_seconds(w["start"], w["end"] or now(), lo, lo + timedelta(days=1))
    finished = [{"code": t["stage"], "name": sdef(t["stage"])["name"], "at": t["ended_at"] or t["decided_at"], "seconds": worked(t["id"])[0]}
                for t in q("SELECT * FROM tasks WHERE assignee=? AND bill_id NOT LIKE 'DEMO-%' AND status='approved' AND (substr(ended_at,1,10)=? OR (ended_at IS NULL AND stage NOT LIKE 'TASK-%' AND substr(decided_at,1,10)=?)) ORDER BY id DESC", (user, d0, d0))]
    busy = adhoc_busy(user)
    check = [task_view(t) for t in q("SELECT * FROM tasks WHERE status='submitted' AND validator=? AND bill_id NOT LIKE 'DEMO-%' ORDER BY submitted_at", (user,))]
    alerts = q("SELECT * FROM alerts WHERE user=? AND (bill_id IS NULL OR bill_id NOT LIKE 'DEMO-%') ORDER BY id DESC LIMIT 40", (user,))
    return {"user": user, "server_now": ts(), "mine": mine, "check": check, "alerts": alerts, "today_seconds": secs, "finished_today": finished,
            "busy_with": busy["id"] if busy else None, "lunch": lunch_cfg(), "lunch_now": is_lunch(),
            "unread": q("SELECT COUNT(*) n FROM alerts WHERE user=? AND read=0 AND (bill_id IS NULL OR bill_id NOT LIKE 'DEMO-%')", (user,))[0]["n"]}

def pipeline():
    bills = q("SELECT * FROM bills ORDER BY created_at DESC")
    out = []
    for b in bills:
        cells = {}
        for t in bill_tasks(b["id"]):
            late = t["status"] in ("assigned", "in_progress") and t["due_at"] < ts()
            cells[t["stage"]] = {"id": t["id"], "status": t["status"], "who": t["assignee"] or ", ".join(json.loads(t["owners"])),
                                 "late": late, "rework": t["rework_count"]}
        out.append({**b, "cells": cells})
    return {"stages": [{"code": c, "name": STAGES[c]["name"], "dept": STAGES[c]["dept"]} for c in ORDER], "bills": out,
            "events": q("SELECT * FROM events ORDER BY id DESC LIMIT 60")}

# ------------------------------------------------------------------ demo data + simulator
CLIENTS = ["ABC Industries", "XYZ Hospital", "PQR Logistics", "Sri Lakshmi Textiles", "Metro Facility Services"]
def simulate_step():
    """Moves the most urgent open task one step, acting as the right person. For live demos."""
    # Only demo bills are moved: real work is never touched by the demo buttons.
    for t in q("SELECT t.* FROM tasks t JOIN bills b ON b.id=t.bill_id WHERE b.demo=1 AND t.status IN ('submitted','in_progress','assigned') "
               "ORDER BY CASE t.status WHEN 'submitted' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, t.id"):
        s = sdef(t["stage"]); owners = json.loads(t["owners"])
        if t["status"] == "assigned":
            who = next((o for o in owners if not (is_tracked_adhoc(t) and adhoc_busy(o, t["id"]))), None)
            if not who: continue
            claim(t["id"], who); return f"{who} started {stage_label(t['stage'])} on {t['bill_id'] or 'an admin task'}"
        if t["status"] == "in_progress":
            br = None
            if s.get("branch"): br = random.choice(list(s["branch"]["options"]))
            submit(t["id"], t["assignee"], f"{s['output']} - done", demo_link(t['bill_id'], t['stage']), br)
            return f"{t['assignee']} submitted {stage_label(t['stage'])} on {t['bill_id']}"
        if t["status"] == "submitted":
            approve(t["id"], t["validator"], "Checked"); return f"{t['validator']} approved {stage_label(t['stage'])} on {t['bill_id']}"
    return "Nothing to move - press Load demo data first" if not demo_ids() else "Every demo bill is complete - press Load demo data to start again"

def clear_demo():
    """Remove every demo bill with its tasks, time, alerts, history and files. Real data is not touched."""
    ids = list(demo_ids())
    if ids:
        ph = ",".join("?" * len(ids)); tids = [r["id"] for r in q(f"SELECT id FROM tasks WHERE bill_id IN ({ph})", ids)]
        with LOCK:
            if tids:
                tp = ",".join("?" * len(tids))
                DB.execute(f"DELETE FROM work_log WHERE task_id IN ({tp})", tids); DB.execute(f"DELETE FROM alerts WHERE task_id IN ({tp})", tids)
            DB.execute(f"DELETE FROM alerts WHERE bill_id IN ({ph})", ids); DB.execute(f"DELETE FROM events WHERE bill_id IN ({ph})", ids)
            DB.execute(f"DELETE FROM tasks WHERE bill_id IN ({ph})", ids); DB.execute(f"DELETE FROM bills WHERE id IN ({ph})", ids); DB.commit()
    if storage_on(): shutil.rmtree(os.path.join(storage_root(), DEMO_DIR), ignore_errors=True)
    broadcast({"type": "refresh"})
    return len(ids)

def wipe_all():
    """Start fresh: clear all bills, tasks, alerts, time and history (people, workflow, contracts and Vault files stay)."""
    with LOCK:
        DB.executescript("DROP TABLE IF EXISTS bills; DROP TABLE IF EXISTS tasks; DROP TABLE IF EXISTS events; DROP TABLE IF EXISTS alerts; DROP TABLE IF EXISTS adhoc; DROP TABLE IF EXISTS work_log;")
        DB.executescript(SCHEMA); migrate(DB)
        DB.execute("DELETE FROM rule_runs"); DB.commit()   # task ids start again from 1; the rules themselves stay
    ADHOC.clear()
    if storage_on(): shutil.rmtree(os.path.join(storage_root(), DEMO_DIR), ignore_errors=True)

def load_demo():
    """Demo bills for admins: marked as demo, kept out of staff screens, alerts and the real storage files."""
    clear_demo()
    if storage_on():
        droot = os.path.join(storage_root(), DEMO_DIR); ST.ensure(droot)
        if not os.path.exists(os.path.join(droot, ST.REGISTER, ST.REG_FILE)): ST.write_sample_register(droot)
    DEMO_BUILD["on"] = True
    try: _build_demo()
    finally: DEMO_BUILD["on"] = False

def _build_demo():
    random.seed(11)
    def drive(bill, stop_stage, stop_status):
        """Run every open task of this bill until stop_stage reaches stop_status."""
        for _ in range(200):
            target = next((t for t in bill_tasks(bill) if t["stage"] == stop_stage), None)
            if target and target["status"] == stop_status: return
            open_ = [t for t in bill_tasks(bill) if t["status"] in ("assigned", "in_progress", "submitted")]
            if not open_: return
            t = open_[0]; s = STAGES[t["stage"]]
            if t["status"] == "assigned": claim(t["id"], s["owners"][0])
            elif t["status"] == "in_progress":
                br = "Yes" if s.get("branch") else None
                submit(t["id"], t["assignee"], f"{s['output']} - done", demo_link(bill, t['stage']), br)
            else: approve(t["id"], s["validator"], "Checked")
    # Pick the demo stops from whatever workflow is loaded (S09 / S04 in the standard Monthly Cycle).
    approval = next((c for c in ORDER if STAGES[c]["owners"] == [STAGES[c]["validator"]]), ORDER[len(ORDER) // 2])
    checked = next((c for c in ORDER if STAGES[c].get("branch") and STAGES[c]["validator"] not in STAGES[c]["owners"]),
                   next((c for c in ORDER[1:] if STAGES[c]["validator"] not in STAGES[c]["owners"]), ORDER[0]))
    b1 = new_bill("ABC Industries", "Ramya"); drive(b1, approval, "assigned")             # waiting for the CEO
    b2 = new_bill("XYZ Hospital", "Moses"); drive(b2, checked, "submitted")               # check sent back
    t = next((t for t in bill_tasks(b2) if t["stage"] == checked and t["status"] == "submitted"), None)
    if t: reject(t["id"], STAGES[checked]["validator"], "Headcount is 46 but the register shows 48 - recheck the attendance")
    b3 = new_bill("PQR Logistics", "Ramya")                                               # just arrived, nobody has started
    b4 = new_bill("Metro Facility Services", "Moses"); drive(b4, "-", "-")                # finished and filed in the Vault
    hist = _demo_history()
    x("UPDATE alerts SET read=1 WHERE bill_id LIKE 'DEMO-%' OR task_id IN (SELECT id FROM tasks WHERE bill_id LIKE 'DEMO-%')")
    print("Demo loaded:", b1, b2, b3, b4, f"+ {hist} finished demo bills from the last four weeks (for the Dashboard)"); storage_sync()

def _demo_history():
    """Finished demo bills over the last ~4 working weeks, with realistic timer records, so the Dashboard has something to show.
    Some stages run over their time limit and some finish well inside it, so the gap analysis has findings."""
    rnd = random.Random(5); c = workday_cfg(); workdays = c.get("days", [0, 1, 2, 3, 4, 5])
    t_start = datetime.strptime(c["start"], "%H:%M").time(); t_end = datetime.strptime(c["end"], "%H:%M").time()
    days, d = [], now().date() - timedelta(days=1)
    while len(days) < 24:
        if d.weekday() in workdays: days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    factor = {code: random.Random(code).choice([0.35, 0.8, 0.95, 1.0, 1.05, 1.45, 1.7]) for code in ORDER}
    cursor = {}   # person -> next free moment
    def nextday(dt):
        d = dt.date() + timedelta(days=1)
        while d.weekday() not in workdays: d += timedelta(days=1)
        return datetime.combine(d, t_start) + timedelta(minutes=rnd.randint(0, 20))
    def fit(start, hours):
        """Timer segments for `hours` of work from `start`: skips lunch, carries over to the next working morning."""
        segs, left = [], hours * 3600
        while left > 0:
            if start.time() < t_start: start = datetime.combine(start.date(), t_start)
            if start.time() >= t_end or start.date().weekday() not in workdays: start = nextday(start); continue
            lw = lunch_window(start.date())
            if lw and lw[0] <= start < lw[1]: start = lw[1]
            stop = datetime.combine(start.date(), t_end)
            if lw and start < lw[0]: stop = lw[0]
            take = min(left, (stop - start).total_seconds())
            if take < 600 and left > 600: start = stop; continue
            segs.append((start, start + timedelta(seconds=take))); left -= take; start = start + timedelta(seconds=take)
        return segs
    clients = ["Sunrise Textiles", "Green Valley School", "Kaveri Motors", "Lotus Hospitals", "Bluewave Logistics", "Annai Foods", "Coastal Ceramics", "Vel Engineering"]
    made = 0; last = now() - timedelta(minutes=5)
    for i, client in enumerate(clients):
        bid = f"DEMO-H{i + 1:02d}"
        if q("SELECT id FROM bills WHERE id=?", (bid,)): continue
        t0 = datetime.combine(days[i * 2], t_start) + timedelta(minutes=rnd.randint(0, 90))
        x("INSERT INTO bills (id,client,created_at,status,demo) VALUES (?,?,?,?,1)", (bid, client, ts(t0), "open"))
        prev_end = t0; complete = True
        for code in ORDER:
            s = STAGES[code]
            if not s.get("owners"): continue
            if any(code in v for st in STAGES.values() for v in ((st.get("branch") or {}).get("options") or {}).values()) and \
               not any(code in (st.get("next") or []) for st in STAGES.values()) and rnd.random() < 0.6: continue   # optional branch stage
            who = s["owners"][rnd.randrange(len(s["owners"]))]
            limit = float(s.get("sla_hours") or 1)
            hours = max(0.2, min(7.0, (limit if limit <= 4 else 2.5) * factor[code] * rnd.gauss(1, 0.1)))   # long limits include waiting time
            start = max(prev_end, cursor.get(who, prev_end)) + timedelta(minutes=rnd.choice([5, 10, 15, 20, 30, 45]))
            segs = fit(start, hours); start, end = segs[0][0], segs[-1][1]
            if end > last: complete = False; break
            decided = end + timedelta(minutes=rnd.randint(5, 30)); rework = 1 if rnd.random() < 0.07 else 0
            tid = x("INSERT INTO tasks (bill_id,stage,status,owners,validator,assignee,created_at,due_at,claimed_at,submitted_at,decided_at,output_note,rework_count) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (bid, code, "approved", json.dumps(s["owners"]), s["validator"], who, ts(prev_end), ts(prev_end + timedelta(hours=limit)),
                     ts(start), ts(end), ts(decided), f"{s.get('output', s['name'])} - done", rework))
            for a_, b_ in segs: x("INSERT INTO work_log (task_id,user,start,end) VALUES (?,?,?,?)", (tid, who, ts(a_), ts(b_)))
            cursor[who] = end; prev_end = decided
        if not complete:   # ran into today: leave it out rather than show a stuck bill
            for r in q("SELECT id FROM tasks WHERE bill_id=?", (bid,)): x("DELETE FROM work_log WHERE task_id=?", (r["id"],))
            x("DELETE FROM tasks WHERE bill_id=?", (bid,)); x("DELETE FROM bills WHERE id=?", (bid,)); continue
        x("UPDATE bills SET status='complete' WHERE id=?", (bid,)); made += 1
    return made

# ------------------------------------------------------------------ workflow input (Excel / Google Sheet / upload)
# The process can be replaced from a workbook: Stages, People, Bills to open, Settings (see workflow_input.py).
INPUT = {"loaded_at": "", "source": "", "error": "", "hash": "", "checked_at": ""}

def fetch_location(loc):
    """Google Sheet link, any https link to an .xlsx, or a file path on this PC / a shared drive -> bytes."""
    loc = (loc or "").strip().strip('"').strip()
    if not loc: raise WI.InputError("Paste a Google Sheet link or a file path first.")
    if loc.lower().startswith(("http://", "https://")):
        url = WI.sheet_export_url(loc)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SomeshEnterprises"})
            with urllib.request.urlopen(req, timeout=30) as r: data = r.read()
        except Exception as e:
            raise WI.InputError(f"Couldn't download the sheet ({e}). Check the link and that this PC is online.")
        if data[:2] != b"PK":
            raise WI.InputError("Google sent a sign-in page instead of the file. In the sheet: Share -> General access -> "
                                "'Anyone with the link' -> Viewer, then try again.")
        return data
    path = os.path.expandvars(os.path.expanduser(loc))
    if not os.path.isabs(path): path = os.path.join(ROOT, path)
    if os.path.isdir(path): raise WI.InputError(f"{loc} is a folder. Give the full path to the .xlsx file.")
    if not os.path.exists(path):
        raise WI.InputError(f"File not found: {loc}. The path must be reachable from the PC running the app "
                            "(for example G:\\Shared drives\\Data Center\\Workflow_Input.xlsx).")
    if path.lower().endswith(".xls"): raise WI.InputError("Old .xls files aren't supported. Save it as .xlsx (Excel Workbook).")
    with open(path, "rb") as f: return f.read()

def summarise(parsed):
    new = {s["code"]: s for s in parsed["flow"]["stages"]}
    newp = {u["name"] for u in parsed["users"]}
    keys = ("name", "dept", "owners", "validator", "sla_hours", "next", "requires", "optional_requires", "branch", "cc", "output")
    changed = [c for c in new if c in STAGES and any(new[c].get(k) != STAGES[c].get(k) for k in keys)]
    month = now().strftime("%Y-%m")
    bills = [{"client": b["client"], "skip": bool(q("SELECT id FROM bills WHERE client=? AND created_at LIKE ?", (b["client"], month + "%")))}
             for b in parsed["bills"]]
    return {"stages": len(new), "people": len(newp), "start": parsed["flow"]["start_stage"], "final": parsed["flow"]["final_stages"],
            "added_stages": [c for c in new if c not in STAGES], "removed_stages": [c for c in ORDER if c not in new],
            "changed_stages": changed, "added_people": sorted(newp - USER_NAMES), "removed_people": sorted(USER_NAMES - newp),
            "bills": bills, "speed": parsed["flow"]["settings"]["demo_speed"],
            "table": [{"code": s["code"], "name": s["name"], "dept": s["dept"], "owners": s["owners"], "validator": s["validator"],
                       "sla_hours": s["sla_hours"], "next": s["next"], "requires": s.get("requires", []), "cc": s.get("cc", []),
                       "question": (s.get("branch") or {}).get("question", "")} for s in parsed["flow"]["stages"]]}

def check_live(parsed):
    errors = list(parsed["errors"])
    codes = {s["code"] for s in parsed["flow"]["stages"]}
    stuck = sorted({r["stage"] for r in q("SELECT stage FROM tasks WHERE status IN ('assigned','in_progress','submitted') AND bill_id NOT LIKE 'DEMO-%'")
                    if not r["stage"].startswith("TASK-")} - codes)
    if stuck: errors.append("Open tasks are still at " + ", ".join(stuck) + ". Keep those stage rows until the tasks are finished, "
                            "or tick 'Start fresh' to clear the current bills and start the new workflow empty.")
    return errors

def apply_definitions(parsed, actor, source, open_bills=True):
    flow, users = parsed["flow"], parsed["users"]
    bdir = os.path.join(ROOT, "data", "backups"); os.makedirs(bdir, exist_ok=True); stamp = now().strftime("%Y%m%d-%H%M%S")
    for name in ("workflow.json", "users.json"):
        try:
            with open(os.path.join(BASE, name), "rb") as a, open(os.path.join(bdir, f"{stamp}-{name}"), "wb") as b: b.write(a.read())
        except OSError: pass
    with LOCK:
        EM.validate_roster(globals(), users)
        if not any(u.get("admin") for u in users): raise FlowError("Keep at least one active Admin")
        previous_roles = {u["name"]: bool(u.get("admin")) for u in USERS}
        changed_roles = {u["name"] for u in users if bool(u.get("admin")) != previous_roles.get(u["name"], False)}
        changed_roles.update(set(previous_roles) - {u["name"] for u in users})
        save("workflow.json", {"_about": f"Loaded from {source} on {ts()} by {actor}. Change it with the Workflow input page.", **flow})
        save("users.json", {"_about": f"Loaded from {source} on {ts()}.", "users": users})
        for name in changed_roles: DB.execute("DELETE FROM sessions WHERE user=?", (name,))
        FLOW.clear(); FLOW.update(flow)
        STAGES.clear(); STAGES.update({st["code"]: st for st in flow["stages"]})
        ORDER[:] = [st["code"] for st in flow["stages"]]
        USERS[:] = users
        EM.sync(globals())
        USER_NAMES.clear(); USER_NAMES.update(u["name"] for u in USERS)
        for st in flow["stages"]:   # open tasks follow the new owners and checker
            DB.execute("UPDATE tasks SET owners=?, validator=? WHERE stage=? AND status IN ('assigned','in_progress','submitted')",
                       (json.dumps(st["owners"]), st["validator"], st["code"]))
        DB.commit()
    if any(r["stage"] not in STAGES for r in q("SELECT stage FROM tasks WHERE bill_id LIKE 'DEMO-%' AND status IN ('assigned','in_progress','submitted')")):
        clear_demo()   # demo bills on the old stages can't continue
    log(None, None, "workflow", actor, f"Workflow updated from {source}: {len(ORDER)} stages, {len(USERS)} people")
    opened = open_sheet_bills(parsed, actor) if open_bills else []
    broadcast({"type": "reload"})
    return opened

def open_sheet_bills(parsed, actor):
    opened = []
    month = now().strftime("%Y-%m")
    for b in parsed["bills"]:
        if q("SELECT id FROM bills WHERE client=? AND created_at LIKE ?", (b["client"], month + "%")): continue
        opened.append(new_bill(b["client"], actor if actor in USER_NAMES else "System"))
    return opened

def process_input(data, actor, source, do_apply, fresh=False, merge=False):
    """fresh=True: clear every bill, task and alert and start the new workflow empty (no open-task check needed).
    merge=True: the file holds only some stages (e.g. one department's); they are added or updated, the rest stay."""
    parsed = WI.parse(data, FLOW, USERS, merge=merge)
    errors = list(parsed["errors"]) if fresh else check_live(parsed)
    res = {"ok": not errors, "errors": errors, "warnings": parsed["warnings"], "summary": summarise(parsed), "applied": False,
           "merged": parsed.get("merged")}
    INPUT["checked_at"] = ts()
    if do_apply and not errors:
        if fresh:
            apply_definitions(parsed, actor, source, open_bills=False)
            wipe_all()
            log(None, None, "workflow", actor, f"Started fresh on the new workflow from {source}")
            res["opened"] = open_sheet_bills(parsed, actor if actor in USER_NAMES else "System"); storage_sync()
            broadcast({"type": "reload"})
        else:
            res["opened"] = apply_definitions(parsed, actor, source)
        res["applied"] = True; res["fresh"] = fresh
        INPUT.update(loaded_at=ts(), source=source, error="", hash=hashlib.sha256(data).hexdigest())
    return res

def input_settings():
    return CONFIG.setdefault("workflow_input", {"location": "", "auto_reload_minutes": 0})

def input_loop():
    """Re-reads the saved Google Sheet / file every N minutes and applies it when it has changed and is valid."""
    last = 0
    while True:
        time.sleep(20)
        cfg = input_settings(); mins = float(cfg.get("auto_reload_minutes") or 0)
        if not mins or not cfg.get("location") or time.time() - last < mins * 60: continue
        last = time.time()
        try:
            data = fetch_location(cfg["location"])
            if hashlib.sha256(data).hexdigest() == INPUT.get("hash"): continue
            res = process_input(data, "Auto reload", cfg["location"], True)
            if not res["ok"]:
                msg = "; ".join(res["errors"][:3])
                if msg != INPUT.get("error"):
                    INPUT["error"] = msg
                    alert([u["name"] for u in USERS if u.get("admin")], "rejected", "Workflow file has problems",
                          "The saved workflow file was not applied: " + msg)
        except Exception as e:
            if str(e) != INPUT.get("error"):
                INPUT["error"] = str(e); print("workflow reload failed:", e)

def is_admin(name):
    return any(u["name"] == name and u.get("admin") for u in USERS)

# ------------------------------------------------------------------ HTTP
# ------------------------------------------------------------------ sign-in
# Admins sign in with a PIN (config.json -> security). Everyone gets a session token; the server takes the person from the
# token, never from the request, and admin-only data (pipeline, bills, workflow, automation) needs an admin session.
PIN_ATTEMPTS = {}

def admin_pin_ok(user, pin):
    sec = CONFIG.get("security", {})
    want = str(sec.get("pins", {}).get(user) or sec.get("admin_pin") or "")
    return bool(want) and hmac.compare_digest(str(pin or "").encode("utf-8"), want.encode("utf-8"))

def verify_admin_pin(user, pin):
    """Rate-limit PIN checks without changing existing credentials or session formats."""
    with LOCK:
        cut = time.monotonic() - 300
        attempts = [t for t in PIN_ATTEMPTS.get(user, []) if t > cut]
        PIN_ATTEMPTS[user] = attempts
        if len(attempts) >= 5: raise FlowError("Too many PIN attempts. Try again in 5 minutes.")
        if not admin_pin_ok(user, pin):
            attempts.append(time.monotonic())
            raise FlowError("Wrong PIN")
        PIN_ATTEMPTS.pop(user, None)

def admin_management():
    return {"users": [{k: v for k, v in u.items() if k in ("name", "dept", "role", "admin")} for u in USERS],
            "admin_count": len(admins()),
            "audit": q("SELECT ts,actor,text FROM events WHERE kind='admin_access' ORDER BY id DESC LIMIT 20")}

def change_admin_role(actor, body):
    if not isinstance(body, dict): raise FlowError("Role change must be an object")
    target, enabled = body.get("user"), body.get("admin")
    if not isinstance(target, str) or target not in USER_NAMES: raise FlowError("Choose an existing employee")
    if not isinstance(enabled, bool): raise FlowError("Admin permission must be true or false")
    with LOCK:
        if not is_admin(actor): raise Denied("Only admins can manage admin permissions")
        if target not in USER_NAMES: raise FlowError("Choose an existing employee")
        if target == actor and enabled: raise FlowError("You cannot promote yourself")
        current = is_admin(target)
        if current == enabled: raise FlowError("This employee already has that role. Refresh the list.")
        if current and not enabled and len(admins()) <= 1: raise FlowError("The last active Admin cannot be removed")
        verify_admin_pin(actor, body.get("confirmation_pin"))
        original = load("users.json")
        updated = {**original, "users": [{**u, "admin": enabled} if u["name"] == target else dict(u) for u in USERS]}
        action = "granted Admin access to" if enabled else "revoked Admin access from"
        event = f"{actor} {action} {target}"
        saved = False
        try:
            DB.execute("BEGIN IMMEDIATE")
            DB.execute("DELETE FROM sessions WHERE user=?", (target,))
            DB.execute("INSERT INTO events (ts,bill_id,task_id,kind,actor,text) VALUES (?,NULL,NULL,?,?,?)",
                       (ts(), "admin_access", actor, event))
            save("users.json", updated); saved = True
            DB.commit()
        except Exception:
            DB.rollback()
            if saved: save("users.json", original)
            raise
        USERS[:] = updated["users"]
        EM.sync(globals())
    broadcast({"type": "reload"}); STORAGE_DIRTY.set(); GATHER_DIRTY.set()
    return admin_management()

def is_dc(name):
    return any(u["name"] == name and "data center" in u.get("dept", "").lower() for u in USERS)
def new_session(user):
    tok = secrets.token_urlsafe(24); x("INSERT INTO sessions VALUES (?,?,?)", (tok, user, ts())); return tok
def session_cutoff():
    days = NET["session_days"]
    return ts(now() - timedelta(days=days)) if days > 0 else ""
def session_user(tok):
    if not tok: return None
    r = q("SELECT user, created_at FROM sessions WHERE token=?", (tok,))
    if not r: return None
    if (r[0]["created_at"] or "") < session_cutoff():   # sessions expire after network.session_days (default 30)
        x("DELETE FROM sessions WHERE token=?", (tok,)); return None
    return r[0]["user"] if r[0]["user"] in USER_NAMES else None

def parse_record_id(value):
    try:
        result = int(value)
        if not 0 < result <= 9223372036854775807: raise ValueError()
        return result
    except (ValueError, TypeError): raise FlowError("Choose an existing record")


class NeedLogin(Exception): pass
class Denied(Exception): pass

HTTPS_ON = [False]
ADMIN_SYNC_PATHS = ("/api/rules", "/api/automation", "/api/templates", "/api/demo/clear")

class H(BaseHTTPRequestHandler):
    server_version = f"SomeshEnterprises/{APP_VERSION}"
    secure = False   # True on the HTTPS listener
    def log_message(self, *a): pass

    def handle(self):
        try: super().handle()
        except (ConnectionError, ssl.SSLError, TimeoutError): pass  # Closing a tab can abort an idle keep-alive socket on Windows.
    def send_response(self, code, message=None):
        self._status = code; super().send_response(code, message)
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")   # the live stream URL carries the session token
        super().end_headers()
    def guard(self, write):
        """Office-LAN only, optional HTTP -> HTTPS redirect for other PCs, and same-origin POSTs (no cross-site use)."""
        ip = self.client_address[0]
        if not LAN.client_allowed(ip, NET):
            self.send_json({"error": "This computer is not on an approved office network."}, 403); return False
        path = urlparse(self.path).path
        if (not self.secure and HTTPS_ON[0] and NET["https"]["redirect_lan_http"] and not LAN.is_loopback(ip)
                and path not in ("/office-ca.crt", "/api/health")):
            host = LAN.host_only(self.headers.get("Host")) or (LAN.lan_ipv4() or ["localhost"])[0]
            self.send_response(308); self.send_header("Location", f"https://{host}:{NET['https']['port']}{self.path}")
            self.send_header("Content-Length", "0"); self.end_headers(); return False
        if write and not LAN.origin_ok(self.headers.get("Origin"), self.headers.get("Host"), NET["allowed_origins"]):
            self.send_json({"ok": False, "error": "Cross-site request blocked."}, 403); return False
        return True
    def send_json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        gz = len(b) > 4096 and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz: b = gzip.compress(b, 5)
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        if gz: self.send_header("Content-Encoding", "gzip"); self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def send_bytes(self, data, ctype, name=None, inline=False, private=False):
        from urllib.parse import quote
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if private: self.send_header("Cache-Control", "no-store")
        if name: self.send_header("Content-Disposition", f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name)}")
        self.end_headers(); self.wfile.write(data)
    def body(self):
        try: n = int(self.headers.get("Content-Length") or 0)
        except ValueError: raise FlowError("Invalid request length")
        if not 0 <= n <= 15 * 1024 * 1024: raise FlowError("Request body must be at most 15 MB")
        try: return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, UnicodeError): raise FlowError("Request body must contain valid JSON")
    def who(self, qs):
        tok = self.headers.get("X-Session") or (qs.get("t") or [""])[0]
        u = session_user(tok)
        if not u: raise NeedLogin()
        return u
    def need_admin(self, qs):
        u = self.who(qs)
        if not is_admin(u): raise Denied("Only admins can see this")
        return u
    def storage_file(self, rel, user):
        from urllib.parse import unquote
        root = os.path.realpath(storage_root()); fp = os.path.realpath(os.path.join(root, unquote(rel)))
        if not storage_on() or not fp.startswith(root + os.sep) or not os.path.isfile(fp): return None
        if not (is_admin(user) or is_dc(user)) and not fp.startswith(os.path.realpath(os.path.join(root, ST.HANDOFF)) + os.sep):
            raise Denied("You can open hand-off files only")
        return fp

    def do_GET(self):
        if not self.guard(False): return
        u = urlparse(self.path); qs = parse_qs(u.query)
        try: return self.get(u, qs)
        except NeedLogin: return self.send_json({"error": "Please sign in again", "login": True}, 401)
        except Denied as e: return self.send_json({"error": str(e)}, 403)
        except FlowError as e: return self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e:
            print("error:", repr(e)); self.send_json({"error": "Server error: " + str(e)}, 500)

    def get(self, u, qs):
        parts = u.path.strip("/").split("/")
        if u.path == "/api/excel" or u.path.startswith("/api/excel/"):
            result = EW.get(globals(), self.who(qs), u.path, qs)
            if isinstance(result, tuple):
                return self.send_bytes(result[0], result[2] if len(result)>2 else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", result[1], private=True)
            return self.send_json(result)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(FRONTEND, "index.html"), "rb") as f: b = f.read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b); return
        if u.path.startswith("/static/"):
            sd = os.path.realpath(FRONTEND); fp = os.path.realpath(os.path.join(sd, u.path[8:]))
            if not fp.startswith(sd + os.sep) or not os.path.isfile(fp): return self.send_json({"error": "Not found"}, 404)
            import mimetypes
            with open(fp, "rb") as f: data = f.read()
            self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(fp)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if u.path == "/api/health":
            from launcher import instance_id
            q("SELECT 1")
            return self.send_json({"app": APP_NAME, "version": APP_VERSION, "instance": instance_id(ROOT), "database": "ok",
                                   "https_port": NET["https"]["port"] if HTTPS_ON[0] else None})
        if u.path == "/office-ca.crt":   # public half of the office CA, for employee PCs to trust the HTTPS address
            fp = os.path.join(ROOT, LAN.CA_FILE)
            if not os.path.isfile(fp): return self.send_json({"error": "HTTPS has not been set up on this server"}, 404)
            with open(fp, "rb") as f: return self.send_bytes(f.read(), "application/x-x509-ca-cert", "office-ca.crt")
        if u.path == "/api/meta":
            return self.send_json({"users": [{k: v for k, v in x_.items() if k != "email"} for x_ in USERS], "stages": FLOW["stages"],
                                   "demo_speed": speed(), "app_name": APP_NAME, "server_now": ts(), "start_stage": FLOW.get("start_stage"),
                                   "handoff_base": os.path.join(storage_root(), ST.HANDOFF) if storage_on() else "", "sep": os.sep,
                                   "storage": storage_on(), "email": bool(CONFIG.get("email", {}).get("enabled")), "lunch": lunch_cfg(), "has_demo": bool(demo_ids())})
        if u.path == "/api/alerts":
            user = self.need_admin(qs); return self.send_json(alert_center(user))
        if len(parts) == 4 and parts[:2] == ["api", "alerts"] and parts[3] == "task":
            user = self.need_admin(qs)
            try:
                aid = int(parts[2])
                if not 0 < aid <= 9223372036854775807: raise ValueError()
            except ValueError: raise FlowError("Choose an existing alert")
            alerts_ = q("SELECT task_id FROM alerts WHERE id=? AND user=?", (aid, user))
            if not alerts_: raise Denied("This alert is not available to your account")
            if not alerts_[0]["task_id"]: raise FlowError("This notification has no linked task")
            return self.send_json({"task": task_view(get_task(alerts_[0]["task_id"]))})
        if u.path == "/api/employees":
            self.need_admin(qs); return self.send_json({"users": USERS})
        if u.path == "/api/admins":
            self.need_admin(qs); return self.send_json(admin_management())
        if u.path == "/api/me":
            user = self.who(qs); return self.send_json({"user": user, "admin": is_admin(user)})
        if u.path == "/api/state":
            return self.send_json(state(self.who(qs)))
        if u.path == "/stream":
            user = self.who(qs)
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive"); self.end_headers()
            qu = queue.Queue(maxsize=200); SUBS.setdefault(user, []).append(qu)
            try:
                self.wfile.write(b"retry: 3000\n: connected\n\n"); self.wfile.flush()
                while True:
                    try:
                        msg = qu.get(timeout=15)
                        self.wfile.write(f"data: {json.dumps(msg, default=str)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                if qu in SUBS.get(user, []): SUBS[user].remove(qu)
            return
        if u.path.startswith("/files/"):
            fp = self.storage_file(u.path[7:], self.who(qs))
            if not fp: return self.send_json({"error": "Not found"}, 404)
            import mimetypes
            with open(fp, "rb") as f: data = f.read()
            ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            return self.send_bytes(data, ctype, os.path.basename(fp), inline=ctype in ("application/pdf", "text/plain", "text/csv") or ctype.startswith("image/"))
        if u.path == "/api/preview":
            fp = self.storage_file((qs.get("path") or [""])[0], self.who(qs))
            if not fp: return self.send_json({"error": "File not found"}, 404)
            return self.send_json(preview(fp))
        # ---- admin only from here
        if u.path in ("/api/action-center", "/api/action-center/export.xlsx", "/api/action-center/export.pdf"):
            actor = self.need_admin(qs)
            report = action_center_report(actor, qs)
            if u.path == "/api/action-center": return self.send_json(report)
            from action_center import export_report
            fmt = "pdf" if u.path.endswith(".pdf") else "xlsx"
            content_type = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return self.send_bytes(export_report(report, fmt), content_type, f"Operations_Summary_{report['date']}.{fmt}")
        if len(parts) == 4 and parts[:3] == ["api", "action-center", "task"]:
            self.need_admin(qs)
            try:
                tid = int(parts[3])
                if not 0 < tid <= 9223372036854775807: raise ValueError()
            except ValueError: raise FlowError("Choose an existing task")
            t = get_task(tid)
            if str(t["bill_id"] or "").startswith("DEMO-"): raise FlowError("Demo tasks are excluded from Action Center")
            return self.send_json({"task": task_view(t)})
        if u.path == "/api/pipeline":
            self.need_admin(qs); return self.send_json(pipeline())
        if u.path == "/api/bill":
            self.need_admin(qs); return self.send_json(bill_detail((qs.get("id") or [""])[0]))
        if u.path == "/api/storage":
            user = self.who(qs)
            if not (is_admin(user) or is_dc(user)): raise Denied("Only Data Center and admins can see storage")
            root = storage_root()
            if storage_on(): ST.ensure(root)
            reg = ST.load_register(root) if storage_on() else []
            return self.send_json({"enabled": storage_on(), "root": root, "status": STORAGE_STATUS,
                                   "tree": [f for f in (ST.tree(root) if storage_on() else []) if is_admin(user) or not f["path"].startswith(DEMO_DIR)],
                                   "register": reg,
                                   "bills": q("SELECT id, client, status, contract_no, contract_status, vault_folder FROM bills " + ("" if is_admin(user) else "WHERE demo=0 ") + "ORDER BY id")})
        if u.path == "/api/workflow":
            self.need_admin(qs); cfg = input_settings()
            return self.send_json({"input": {**INPUT, "location": cfg.get("location", ""), "auto_reload_minutes": cfg.get("auto_reload_minutes", 0)},
                                   "start": FLOW.get("start_stage"), "final": FLOW.get("final_stages", []), "speed": speed()})
        if u.path == "/api/workflow/template":
            self.need_admin(qs)
            data = WI.build(FLOW, USERS, [], speed())
            return self.send_bytes(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Workflow_Input_Template.xlsx")
        if u.path == "/api/automation":
            self.need_admin(qs); a = auto_cfg()
            active = [c for c in (ST.load_register(storage_root()) if storage_on() else []) if ST.contract_for(storage_root(), str(c.get("Client") or ""))[1] == "Active"]
            return self.send_json({"settings": a, "active_contracts": len(active)})
        if u.path in ("/api/tracker", "/api/tracker/export", "/api/tracker/export.pdf"):
            self.need_admin(qs)
            try: day = datetime.strptime((qs.get("date") or [""])[0] or now().strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            except ValueError: raise FlowError("Date must look like 2026-11-03")
            if u.path.endswith("export.pdf"):
                from tracker_export import tracker_pdf
                return self.send_bytes(tracker_pdf(tracker(day)), "application/pdf", f"Tracker_{day:%Y-%m-%d}.pdf")
            if u.path.endswith("export"):
                data = tracker_xlsx(day)
                if storage_on():   # a copy goes into the local storage too
                    daily = os.path.join(storage_root(), ST.TRACKER, day.strftime("%Y"), "Daily Time Tracker"); os.makedirs(daily, exist_ok=True)
                    try:
                        with open(os.path.join(daily, f"Time_Tracker_{day:%Y-%m-%d}.xlsx"), "wb") as f: f.write(data)
                    except PermissionError: pass
                return self.send_bytes(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"Tracker_{day:%Y-%m-%d}.xlsx")
            return self.send_json(tracker(day, (qs.get("demo") or ["0"])[0] == "1"))
        if u.path == "/api/templates":
            self.need_admin(qs); return self.send_json({"templates": templates()})
        if u.path == "/api/dashboard":
            self.need_admin(qs)
            try:
                d_to = datetime.strptime((qs.get("to") or [""])[0] or now().strftime("%Y-%m-%d"), "%Y-%m-%d").date()
                d_from = datetime.strptime((qs.get("from") or [""])[0] or (d_to - timedelta(days=6)).strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            except ValueError: raise FlowError("Dates look like 2026-11-03")
            if d_from > d_to: d_from, d_to = d_to, d_from
            if (d_to - d_from).days > 92: raise FlowError("Pick up to 3 months at a time")
            return self.send_json(dashboard(d_from, d_to, (qs.get("demo") or ["0"])[0] == "1"))
        if u.path == "/api/timetable":
            self.need_admin(qs)
            try: day = datetime.strptime((qs.get("date") or [""])[0] or now().strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            except ValueError: raise FlowError("Date must look like 2026-11-03")
            return self.send_json(timetable(day, (qs.get("demo") or ["0"])[0] == "1"))
        if u.path == "/api/adhoc":
            self.need_admin(qs)
            rows = [task_view(t) for t in q("SELECT * FROM tasks WHERE stage LIKE 'TASK-%' ORDER BY id DESC LIMIT 200")]
            return self.send_json({"tasks": rows, "bills": q("SELECT id, client FROM bills WHERE status='open' ORDER BY id")})
        # ---- automation rules (admins)
        if u.path == "/api/rules":
            self.need_admin(qs); return self.send_json(rules_meta())
        if u.path == "/api/rules/log":
            self.need_admin(qs)
            try: limit = min(500, max(1, int((qs.get("limit") or ["50"])[0])))
            except ValueError: raise FlowError("limit must be a number")
            return self.send_json({"runs": q("SELECT rr.*, r.name AS rule FROM rule_runs rr LEFT JOIN rules r ON r.id=rr.rule_id ORDER BY rr.id DESC LIMIT ?", (limit,))})
        if u.path == "/api/workflow-model":
            self.need_admin(qs); return self.send_json(workflow_model((qs.get("demo") or ["0"])[0] == "1"))
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.guard(True): return
        self._status = None; EXCEL_TOUCHED.items = []
        try: self.post()
        finally:
            ok = self._status == 200
            flush_excel_changes(ok)
            if ok and urlparse(self.path).path.startswith(ADMIN_SYNC_PATHS): push_admins({"type": "refresh"})

    def post(self):
        u = urlparse(self.path); parts = u.path.strip("/").split("/"); qs = parse_qs(u.query)
        try:
            if u.path.startswith("/api/excel/"):
                actor = self.who(qs)
                if int(self.headers.get("Content-Length") or 0) > 15 * 1024 * 1024:
                    return self.send_json({"error": "Excel request exceeds 15 MB."}, 413)
                b = self.body()
                if not isinstance(b, dict): raise FlowError("Request body must be an object")
                return self.send_json(EW.post(globals(), actor, u.path, b))
            b = self.body()
            if not isinstance(b, dict): raise FlowError("Request body must be an object")
            if u.path == "/api/login":
                name = b.get("user", "")
                with LOCK:  # Role changes and session issuance must not race.
                    if not isinstance(name, str) or name not in USER_NAMES: raise FlowError("Pick your name")
                    if is_admin(name): verify_admin_pin(name, b.get("pin"))
                    return self.send_json({"ok": True, "token": new_session(name), "user": name, "admin": is_admin(name)})
            actor = self.who(qs)
            if u.path == "/api/logout":
                x("DELETE FROM sessions WHERE token=?", (self.headers.get("X-Session") or "",)); return self.send_json({"ok": True})
            if u.path == "/api/alerts/read":
                read_alerts(actor, b); return self.send_json({"ok": True})
            if u.path == "/api/alerts/snooze":
                snooze_alerts(actor, b); return self.send_json({"ok": True})
            if len(parts) == 4 and parts[:2] == ["api", "tasks"]:
                tid = parse_record_id(parts[2]); act = parts[3]
                if is_lunch() and not is_admin(actor):
                    c = lunch_cfg(); raise FlowError(f"Lunch break {c['start']}-{c['end']}: the app is locked. It opens again at {c['end']}.")
                if act == "claim": claim(tid, actor)
                elif act == "end": end_task(tid, actor)
                elif act == "submit": submit(tid, actor, b.get("note", ""), b.get("link", ""), b.get("branch"))
                elif act == "approve": approve(tid, actor, b.get("note", ""))
                elif act == "reject": reject(tid, actor, b.get("note", ""))
                elif act in ("upload", "unupload"):
                    t = get_task(tid)
                    if is_tracked_adhoc(t):
                        if t["assignee"] != actor or t["status"] != "approved" or t["ended_at"]:
                            raise FlowError("Documents can be added once the admin has approved the task, before you end it")
                    elif t["status"] != "in_progress" or t["assignee"] != actor: raise FlowError("Start the task first; only the person working on it can attach files")
                    if act == "upload":
                        try: data = base64.b64decode(b.get("data") or "")
                        except Exception: raise FlowError("The upload was damaged. Try again.")
                        fn = save_upload(t, b.get("name") or "file", data)
                        log(t["bill_id"] or None, tid, "file", actor, f"{actor} attached {fn} to {stage_label(t['stage'])}")
                    else:
                        fp = os.path.join(task_folder(t), os.path.basename(b.get("name") or ""))
                        if os.path.isfile(fp): os.remove(fp)
                        broadcast({"type": "refresh"})
                    return self.send_json({"ok": True, "files": task_files(get_task(tid))})
                else: raise FlowError("Unknown action")
                return self.send_json({"ok": True})
            if u.path == "/api/storage/sync":
                if not (is_admin(actor) or is_dc(actor)): raise FlowError("Only Data Center or admins can do this")
                storage_sync(); return self.send_json({"ok": True, "status": STORAGE_STATUS})
            # ---- admin only from here
            if not is_admin(actor): raise Denied("Only admins can do this")
            if u.path == "/api/action-center/reassign":
                return self.send_json(action_center_reassign(actor, b))
            if u.path == "/api/employees":
                return self.send_json(EM.change(globals(), actor, b))
            if u.path == "/api/admins/role":
                return self.send_json({"ok": True, **change_admin_role(actor, b)})
            if u.path == "/api/bills":
                clients = [c.strip() for c in re.split(r"[\n,]+", b.get("client") or "") if c.strip()]
                if not clients: raise FlowError("Type the client name")
                ids = [new_bill(c, actor) for c in clients]
                return self.send_json({"ok": True, "bill_id": ", ".join(ids), "bills": ids})
            if u.path == "/api/assign":
                made = []
                for i, r in enumerate(b.get("tasks") or [], 1):
                    if not (r.get("title") or "").strip() and not r.get("who"): continue
                    who = r.get("who") or ""
                    owners = [m["name"] for m in USERS if m.get("dept") == who[5:]] if who.startswith("dept:") else [who]
                    made.append(create_adhoc(r.get("title") or "", owners, r.get("checker") or "", r.get("hours") or 0,
                                             r.get("output") or "", actor, r.get("bill") or "", who[5:] if who.startswith("dept:") else "",
                                             bool(r.get("docs"))))
                if not made: raise FlowError("Add at least one task")
                return self.send_json({"ok": True, "codes": made})
            if u.path == "/api/automation":
                a = auto_cfg(); v = b.get("settings") or {}
                a["auto_start"] = bool(v.get("auto_start")); a["escalate_to_admins"] = bool(v.get("escalate_to_admins"))
                a["remind_every_hours"] = max(0.0, float(v.get("remind_every_hours") or 0))
                a["monthly_open_day"] = min(28, max(0, int(v.get("monthly_open_day") or 0))); a["monthly_open_hour"] = min(23, max(0, int(v.get("monthly_open_hour") or 0)))
                save("config.json", CONFIG); log(None, None, "automation", actor, f"{actor} changed the automation settings")
                return self.send_json({"ok": True, "settings": a})
            if u.path == "/api/templates":
                rows = []
                for t in b.get("templates") or []:
                    name = str(t.get("name") or "").strip()
                    if not name: continue
                    try: hours = max(0.25, float(t.get("hours") or 1))
                    except ValueError: raise FlowError(f"Hours for '{name}' must be a number")
                    rows.append({"name": name[:80], "hours": hours, "docs": bool(t.get("docs")), "about": str(t.get("about") or "")[:200]})
                CONFIG["task_templates"] = rows; save("config.json", CONFIG); return self.send_json({"ok": True, "templates": rows})
            if len(parts) == 4 and parts[:2] == ["api", "admin-task"]:
                tid = parse_record_id(parts[2])
                if parts[3] == "delete": delete_task(tid, actor); return self.send_json({"ok": True})
                if parts[3] == "file":
                    rel, n = file_task_docs(tid); return self.send_json({"ok": True, "folder": rel, "files": n})
            if len(parts) == 4 and parts[:2] == ["api", "bill"] and parts[3] == "delete":
                delete_bill(parts[2], actor); return self.send_json({"ok": True})
            if u.path == "/api/lunch":
                c = lunch_cfg(); v = b.get("lunch") or {}
                for k in ("start", "end"):
                    try: datetime.strptime(v.get(k, c[k]), "%H:%M")
                    except ValueError: raise FlowError("Times look like 13:00")
                c.update(enabled=bool(v.get("enabled", True)), start=v.get("start", c["start"]), end=v.get("end", c["end"]))
                save("config.json", CONFIG); log(None, None, "lunch", actor, f"{actor} set lunch to {c['start']}-{c['end']}" + ("" if c["enabled"] else " (off)"))
                broadcast({"type": "refresh"}); return self.send_json({"ok": True, "lunch": c})
            if u.path == "/api/automation/open-now":
                return self.send_json({"ok": True, "bills": open_bills_for_contracts(actor)})
            if u.path == "/api/rules":
                return self.send_json({"ok": True, "rule": save_rule(b.get("rule") or b, actor)})
            if len(parts) == 4 and parts[:2] == ["api", "rules"]:
                try: rid = int(parts[2])
                except ValueError: raise FlowError("Unknown rule")
                r = q("SELECT * FROM rules WHERE id=?", (rid,))
                if not r: raise FlowError("That rule no longer exists")
                if parts[3] == "toggle":
                    on = 0 if r[0]["enabled"] else 1
                    if "enabled" in b: on = 1 if b.get("enabled") else 0
                    x("UPDATE rules SET enabled=? WHERE id=?", (on, rid))
                    log(None, None, "rule", actor, f"{actor} turned rule '{r[0]['name']}' {'on' if on else 'off'}")
                    return self.send_json({"ok": True, "rule": rule_row(q("SELECT * FROM rules WHERE id=?", (rid,))[0])})
                if parts[3] == "delete":
                    x("DELETE FROM rules WHERE id=?", (rid,)); x("DELETE FROM rule_runs WHERE rule_id=?", (rid,))
                    log(None, None, "rule", actor, f"{actor} deleted rule '{r[0]['name']}'"); return self.send_json({"ok": True})
                if parts[3] == "test":
                    return self.send_json(dict(rule_test(rid), ok=True))
                raise FlowError("Unknown rule action")
            if u.path in ("/api/workflow/upload", "/api/workflow/load"):
                if u.path == "/api/workflow/upload":
                    try: data = base64.b64decode(b.get("file") or "")
                    except Exception: raise FlowError("The upload was damaged. Try again.")
                    if not data: raise FlowError("Choose an .xlsx file first")
                    source = "upload " + (b.get("name") or "file.xlsx")
                else:
                    loc = (b.get("location") or "").strip()
                    data = fetch_location(loc); source = loc
                res = process_input(data, actor, source, bool(b.get("apply")), bool(b.get("fresh")), bool(b.get("merge")))
                if u.path == "/api/workflow/load" and res["applied"] and not b.get("merge"):
                    cfg = input_settings(); cfg["location"] = source
                    cfg["auto_reload_minutes"] = max(0, float(b.get("auto_reload_minutes") or 0)); save("config.json", CONFIG)
                return self.send_json(res)
            if u.path == "/api/demo/simulate":
                return self.send_json({"ok": True, "did": simulate_step()})
            if u.path == "/api/demo/reset":
                load_demo(); broadcast({"type": "refresh"}); return self.send_json({"ok": True, "bills": sorted(demo_ids())})
            if u.path == "/api/demo/clear":
                n = clear_demo(); log(None, None, "demo", actor, f"{actor} cleared the demo data ({n} bills)"); return self.send_json({"ok": True, "cleared": n})
            raise FlowError("Not found")
        except NeedLogin:
            self.send_json({"ok": False, "error": "Please sign in again", "login": True}, 401)
        except Denied as e:
            self.send_json({"ok": False, "error": str(e)}, 403)
        except (FlowError, WI.InputError) as e:
            self.send_json({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            print("error:", repr(e)); self.send_json({"ok": False, "error": "Server error: " + str(e)}, 500)

class HS(H):
    secure = True
    def setup(self):
        self.request.settimeout(15); self.request.do_handshake(); self.request.settimeout(None)   # SSE streams stay open
        super().setup()

def preview(fp):
    """First rows of a spreadsheet / CSV / text file, so a checker can glance at it without downloading."""
    ext = os.path.splitext(fp)[1].lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(fp, read_only=True, data_only=True); ws = wb.worksheets[0]
            rows = [["" if v is None else str(v) for v in r[:15]] for r in ws.iter_rows(max_row=30, values_only=True)]
            out = {"kind": "table", "sheet": ws.title, "sheets": [w.title for w in wb.worksheets], "rows": rows}; wb.close(); return out
        if ext in (".csv", ".tsv"):
            import csv as _csv
            with open(fp, newline="", encoding="utf-8-sig", errors="replace") as f:
                rows = [r[:15] for _, r in zip(range(30), _csv.reader(f, delimiter="\t" if ext == ".tsv" else ","))]
            return {"kind": "table", "rows": rows}
        if ext in (".txt", ".log", ".json", ".xml", ".md"):
            with open(fp, encoding="utf-8", errors="replace") as f: return {"kind": "text", "text": f.read(6000)}
    except Exception as e:
        return {"kind": "error", "text": f"Can't preview this file: {e}"}
    return {"kind": "none", "text": "No preview for this file type. Download it to open it."}

def bill_detail(bid):
    b = q("SELECT * FROM bills WHERE id=?", (bid,))
    if not b: raise FlowError("Bill not found")
    b = b[0]; files = []; contract = None
    if storage_on():
        root = storage_root(); broot = sroot(bid)
        for area, d in (("Hand-off", os.path.join(broot, ST.HANDOFF, f"{bid} {ST.safe(b['client'])}")), ("Vault", os.path.join(root, b["vault_folder"]) if b.get("vault_folder") else "")):
            if d and os.path.isdir(d):
                for dp, _, fns in os.walk(d):
                    for fn in sorted(fns):
                        fp = os.path.join(dp, fn)
                        if not fn.startswith("~$"):
                            files.append({"area": area, "name": os.path.relpath(fp, d).replace(os.sep, "/"), "size": os.path.getsize(fp),
                                          "path": os.path.relpath(fp, root).replace(os.sep, "/")})
        try: contract, _ = ST.contract_for(broot, b["client"])
        except Exception: contract = None
    tasks = []
    for t in bill_tasks(bid):
        s_ = sdef(t["stage"])
        tasks.append({**{k: t[k] for k in ("id", "stage", "status", "assignee", "validator", "created_at", "claimed_at", "submitted_at",
                                           "decided_at", "due_at", "output_note", "output_link", "rework_count", "decision_note", "branch")},
                      "name": s_.get("name", t["stage"]), "dept": s_.get("dept", ""), "owners": json.loads(t["owners"]), "adhoc": bool(s_.get("adhoc"))})
    return {"bill": b, "tasks": tasks, "files": files, "contract": contract, "events": q("SELECT * FROM events WHERE bill_id=? ORDER BY id DESC", (bid,))}

def main():
    load_adhoc()
    if "--template" in sys.argv:
        out = os.path.join(ROOT, "samples", "Workflow_Input_Template.xlsx")
        with open(out, "wb") as f: f.write(WI.build(FLOW, USERS, [], speed()))
        print("Wrote", out); return
    if "--gather-test" in sys.argv:
        gather_test(); return
    host, port = CONFIG.get("host", "0.0.0.0"), int(CONFIG.get("port", 8080))
    srv = ThreadingHTTPServer((host, port), H); srv.daemon_threads = True
    x("DELETE FROM sessions WHERE created_at < ?", (session_cutoff(),))   # expired sign-ins
    https = NET["https"]
    if https["enabled"]:
        try:
            ctx = LAN.tls_context(LAN.resolve(ROOT, https["cert"]), LAN.resolve(ROOT, https["key"]))
            tls = LAN.TLSServer((host, https["port"]), HS, ctx)
            threading.Thread(target=tls.serve_forever, daemon=True).start(); HTTPS_ON[0] = True
        except (OSError, ssl.SSLError, ValueError) as e:
            print(f"HTTPS is enabled in config.json but could not start on port {https['port']}: {e}")
    if "--demo" in sys.argv:     # demo data only when asked for (admins see it; staff never do)
        load_demo()
    threading.Thread(target=overdue_loop, daemon=True).start()
    threading.Thread(target=input_loop, daemon=True).start()
    threading.Thread(target=automation_loop, daemon=True).start()
    threading.Thread(target=storage_loop, daemon=True).start(); STORAGE_DIRTY.set()
    if storage_on(): print("Data Center storage:", storage_root())
    if CONFIG.get("gather", {}).get("enabled"):
        threading.Thread(target=gather_loop, daemon=True).start(); GATHER_DIRTY.set()
        print("Gather Smart Objects: on (" + str(len(CONFIG["gather"].get("objects", []))) + " objects)")
    ips = LAN.lan_ipv4() or ["<this-PC-IP>"]
    print("=" * 64)
    print(f"  {APP_NAME} is running")
    print(f"  On this PC:      http://localhost:{port}")
    for ip in ips:
        if HTTPS_ON[0]: print(f"  Other office PCs: https://{ip}:{https['port']}" + ("" if https["redirect_lan_http"] else f"   (or http://{ip}:{port})"))
        else: print(f"  Other office PCs: http://{ip}:{port}")
    if NET["public_url"]: print(f"  Office address:   {NET['public_url']}")
    print("  Keep this window open. Close it (or press Ctrl+C) to stop the app.")
    print("=" * 64)
    if "--open" in sys.argv:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("Stopped.")
    finally: srv.server_close()

if __name__ == "__main__":
    main()
