#!/usr/bin/env python3
"""SOMESH ENTERPRISES - Monthly Cycle workflow and alerts app.

Each stage is a task. When a stage is approved, the next team's task is created and its
members get an alert (popup + sound in the browser, and optionally email / ntfy / webhook).
Runs on Python 3.9+ with the standard library only.

    python app.py              start the server (http://localhost:8080)
    python app.py --demo       wipe the database and load dummy bills, then start
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
import shutil, secrets

BASE = os.path.dirname(os.path.abspath(__file__))          # backend/  (code + config.json, users.json, workflow.json)
ROOT = os.path.dirname(BASE)                               # project root (data/, storage/, samples/ live here)
FRONTEND = os.path.join(ROOT, "frontend")                  # the web page: index.html, css/, js/, assets/
def load(name):
    with open(os.path.join(BASE, name), encoding="utf-8") as f:
        return json.load(f)
def save(name, obj):
    path = os.path.join(BASE, name); tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

CONFIG = load("config.json")
FLOW = load("workflow.json")
USERS = load("users.json")["users"]
STAGES = {s["code"]: s for s in FLOW["stages"]}
ORDER = [s["code"] for s in FLOW["stages"]]
USER_NAMES = {u["name"] for u in USERS}
APP_NAME = "SOMESH ENTERPRISES"
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
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, kind TEXT, title TEXT, body TEXT, task_id INTEGER, bill_id TEXT, read INTEGER DEFAULT 0);
"""
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA); migrate(c)
    return c
def migrate(c):
    have = {r[1] for r in c.execute("PRAGMA table_info(bills)")}
    for col in ("contract_no", "contract_status", "vault_folder"):
        if col not in have: c.execute(f"ALTER TABLE bills ADD COLUMN {col} TEXT")
    if "demo" not in have: c.execute("ALTER TABLE bills ADD COLUMN demo INTEGER DEFAULT 0")
    tcols = {r[1] for r in c.execute("PRAGMA table_info(tasks)")}
    for col in ("last_reminded", "ended_at"):
        if col not in tcols: c.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
    c.commit()
DB = connect()
def q(sql, args=()):
    with LOCK:
        return [dict(r) for r in DB.execute(sql, args).fetchall()]
def x(sql, args=()):
    with LOCK:
        cur = DB.execute(sql, args); DB.commit(); return cur.lastrowid

# ------------------------------------------------------------------ live alerts (Server-Sent Events)
SUBS = {}  # user -> [Queue]
def push(user, payload):
    for qu in list(SUBS.get(user, [])):
        try: qu.put_nowait(payload)
        except queue.Full: pass
def broadcast(payload):
    for user in list(SUBS):
        push(user, payload)

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
    if auto_cfg().get("auto_start"):   # line up the next one straight away
        nxt = next((n_ for n_ in q("SELECT * FROM tasks WHERE stage LIKE 'TASK-%' AND status='assigned' ORDER BY id") if actor in json.loads(n_["owners"])), None)
        if nxt:
            x("UPDATE tasks SET status='in_progress', assignee=?, claimed_at=? WHERE id=?", (actor, ts(), nxt["id"])); timer_start(nxt["id"], actor)
            alert([actor], "new_task", f"Next task started for you: {sdef(nxt['stage'])['name']}", "Your timer is running.", get_task(nxt["id"]))
            log(nxt["bill_id"] or None, nxt["id"], "started", "Automation", f"{stage_label(nxt['stage'])} started automatically for {actor}")

def tracker(day, demo=False):
    """Every task with time on 'day' (or running now), with the worked time inside that day and in total. Demo tasks only with demo=True."""
    lo = datetime.combine(day, datetime.min.time()); hi = lo + timedelta(days=1); d0 = day.strftime("%Y-%m-%d")
    ids = {r["task_id"] for r in q("SELECT task_id FROM work_log WHERE start < ? AND (end IS NULL OR end >= ?)", (ts(hi), ts(lo)))}
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
    for w in q("SELECT * FROM work_log WHERE start < ? AND (end IS NULL OR end >= ?) ORDER BY start", (ts(hi), ts(lo))):
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
    return tid

# ------------------------------------------------------------------ automation
def auto_cfg():
    return CONFIG.setdefault("automation", {"auto_start": False, "remind_every_hours": 0, "escalate_to_admins": False,
                                            "monthly_open_day": 0, "monthly_open_hour": 9, "last_monthly_open": ""})
def auto_start(tid):
    """Automation: start a new task straight away for the owner with the fewest tasks in progress."""
    if not auto_cfg().get("auto_start"): return None
    t = get_task(tid); owners = json.loads(t["owners"])
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

def reject(tid, actor, note=""):
    t = get_task(tid); s = sdef(t["stage"])
    if t["status"] != "submitted": raise FlowError("Only submitted work can be rejected")
    if actor != t["validator"]: raise FlowError(f"Only {t['validator']} can reject {t['stage']}")
    if not note.strip(): raise FlowError("Write what needs fixing")
    x("UPDATE tasks SET status='in_progress', decision_note=?, rework_count=rework_count+1, submitted_at=NULL WHERE id=?", (note, tid))
    if t["assignee"]: timer_start(tid, t["assignee"])
    log(t["bill_id"], tid, "rejected", actor, f"{actor} sent {stage_label(t['stage'])} back: {note}")
    alert([t["assignee"]], "rejected", f"Rework: {stage_label(t['stage'])}", f"{actor}: {note}", get_task(tid))

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
    save("workflow.json", {"_about": f"Loaded from {source} on {ts()} by {actor}. Change it with the Workflow input page.", **flow})
    save("users.json", {"_about": f"Loaded from {source} on {ts()}.", "users": users})
    with LOCK:
        FLOW.clear(); FLOW.update(flow)
        STAGES.clear(); STAGES.update({st["code"]: st for st in flow["stages"]})
        ORDER[:] = [st["code"] for st in flow["stages"]]
        USERS[:] = users
        USER_NAMES.clear(); USER_NAMES.update(u["name"] for u in users)
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
def admin_pin_ok(user, pin):
    sec = CONFIG.get("security", {})
    want = str(sec.get("pins", {}).get(user) or sec.get("admin_pin") or "")
    return bool(want) and hmac.compare_digest(str(pin or ""), want)
def is_dc(name):
    return any(u["name"] == name and "data center" in u.get("dept", "").lower() for u in USERS)
def new_session(user):
    tok = secrets.token_urlsafe(24); x("INSERT INTO sessions VALUES (?,?,?)", (tok, user, ts())); return tok
def session_user(tok):
    if not tok: return None
    r = q("SELECT user FROM sessions WHERE token=?", (tok,))
    return r[0]["user"] if r and r[0]["user"] in USER_NAMES else None

class NeedLogin(Exception): pass
class Denied(Exception): pass

class H(BaseHTTPRequestHandler):
    server_version = "SomeshEnterprises/3.0"
    def log_message(self, *a): pass
    def send_json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def send_bytes(self, data, ctype, name=None, inline=False):
        from urllib.parse import quote
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        if name: self.send_header("Content-Disposition", f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name)}")
        self.end_headers(); self.wfile.write(data)
    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}
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
        u = urlparse(self.path); qs = parse_qs(u.query)
        try: return self.get(u, qs)
        except NeedLogin: return self.send_json({"error": "Please sign in again", "login": True}, 401)
        except Denied as e: return self.send_json({"error": str(e)}, 403)
        except FlowError as e: return self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e:
            print("error:", repr(e)); self.send_json({"error": "Server error: " + str(e)}, 500)

    def get(self, u, qs):
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
        if u.path == "/api/meta":
            return self.send_json({"users": [{k: v for k, v in x_.items() if k != "email"} for x_ in USERS], "stages": FLOW["stages"],
                                   "demo_speed": speed(), "app_name": APP_NAME, "server_now": ts(), "start_stage": FLOW.get("start_stage"),
                                   "handoff_base": os.path.join(storage_root(), ST.HANDOFF) if storage_on() else "", "sep": os.sep,
                                   "storage": storage_on(), "email": bool(CONFIG.get("email", {}).get("enabled")), "lunch": lunch_cfg(), "has_demo": bool(demo_ids())})
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
                self.wfile.write(b": connected\n\n"); self.wfile.flush()
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
        if u.path in ("/api/tracker", "/api/tracker/export"):
            self.need_admin(qs)
            try: day = datetime.strptime((qs.get("date") or [""])[0] or now().strftime("%Y-%m-%d"), "%Y-%m-%d").date()
            except ValueError: raise FlowError("Date must look like 2026-11-03")
            if u.path.endswith("export"):
                data = tracker_xlsx(day)
                if storage_on():   # a copy goes into the local storage too
                    daily = os.path.join(storage_root(), ST.TRACKER, day.strftime("%Y"), "Daily Time Tracker"); os.makedirs(daily, exist_ok=True)
                    try:
                        with open(os.path.join(daily, f"Time_Tracker_{day:%Y-%m-%d}.xlsx"), "wb") as f: f.write(data)
                    except PermissionError: pass
                return self.send_bytes(data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"Time_Tracker_{day:%Y-%m-%d}.xlsx")
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
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path); parts = u.path.strip("/").split("/"); qs = parse_qs(u.query)
        try:
            b = self.body()
            if u.path == "/api/login":
                name = b.get("user", "")
                if name not in USER_NAMES: raise FlowError("Pick your name")
                if is_admin(name) and not admin_pin_ok(name, b.get("pin")): raise FlowError("Wrong PIN")
                return self.send_json({"ok": True, "token": new_session(name), "user": name, "admin": is_admin(name)})
            actor = self.who(qs)
            if u.path == "/api/logout":
                x("DELETE FROM sessions WHERE token=?", (self.headers.get("X-Session") or "",)); return self.send_json({"ok": True})
            if u.path == "/api/alerts/read":
                x("UPDATE alerts SET read=1 WHERE user=?", (actor,)); return self.send_json({"ok": True})
            if len(parts) == 4 and parts[:2] == ["api", "tasks"]:
                tid = int(parts[2]); act = parts[3]
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
                tid = int(parts[2])
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
    if "--demo" in sys.argv:     # demo data only when asked for (admins see it; staff never do)
        load_demo()
    if "--gather-test" in sys.argv:
        gather_test(); return
    threading.Thread(target=overdue_loop, daemon=True).start()
    threading.Thread(target=input_loop, daemon=True).start()
    threading.Thread(target=automation_loop, daemon=True).start()
    threading.Thread(target=storage_loop, daemon=True).start(); STORAGE_DIRTY.set()
    if storage_on(): print("Data Center storage:", storage_root())
    if CONFIG.get("gather", {}).get("enabled"):
        threading.Thread(target=gather_loop, daemon=True).start(); GATHER_DIRTY.set()
        print("Gather Smart Objects: on (" + str(len(CONFIG["gather"].get("objects", []))) + " objects)")
    host, port = CONFIG.get("host", "0.0.0.0"), int(CONFIG.get("port", 8080))
    srv = ThreadingHTTPServer((host, port), H); srv.daemon_threads = True
    ip = "<this-PC-IP>"
    try:
        import socket
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sk.connect(("10.255.255.255", 1)); ip = sk.getsockname()[0]; sk.close()
    except Exception: pass
    print("=" * 64)
    print(f"  {APP_NAME} is running")
    print(f"  On this PC:      http://localhost:{port}")
    print(f"  Other office PCs: http://{ip}:{port}")
    print("  Keep this window open. Close it (or press Ctrl+C) to stop the app.")
    print("=" * 64)
    if "--open" in sys.argv:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("Stopped.")

if __name__ == "__main__":
    main()
