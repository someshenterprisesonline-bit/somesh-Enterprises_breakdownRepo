"""Isolated synthetic app instances. Never opens the installed application's database."""
import json
import secrets
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class AppFixture:
    def __init__(self, legacy=False):
        self.temp = tempfile.TemporaryDirectory(prefix="somesh-audit-")
        self.root = Path(self.temp.name)
        base = self.root / "backend"
        base.mkdir()
        self.pin = secrets.token_urlsafe(16)
        users = [
            {"name": "Admin One", "dept": "Management", "role": "Manager", "admin": True},
            {"name": "Admin Two", "dept": "Finance", "role": "Controller", "admin": True},
            {"name": "Worker One", "dept": "Operations", "role": "Executive"},
            {"name": "Worker Two", "dept": "Payroll", "role": "Analyst"},
            {"name": "Reviewer", "dept": "Operations", "role": "Team lead"},
        ]
        stages = []
        for code, name, dept, owner, nxt in [
            ("S01", "Receive source", "Operations", "Worker One", ["S02"]),
            ("S02", "Check payroll", "Payroll", "Worker Two", ["S03"]),
            ("S02A", "Additional details", "Operations", "Worker One", ["S03"]),
            ("S03", "Final approval", "Management", "Admin One", []),
        ]:
            stages.append(dict(code=code, name=name, dept=dept, owners=[owner], validator="Admin One",
                               sla_hours=2, output="Verified output", next=nxt))
        stages[1]["branch"] = {"question": "Additional details?", "options": {"Yes": ["S02A"], "No": []}}
        stages[-1]["requires"] = ["S02"]
        stages[-1]["optional_requires"] = ["S02A"]
        config = {"host": "127.0.0.1", "port": 0, "security": {"admin_pin": self.pin},
                  "storage": {"enabled": False}, "lunch": {"enabled": False, "start": "13:00", "end": "14:00"},
                  "automation": {"auto_start": False, "monthly_open_day": 0}}
        flow = {"stages": stages, "start_stage": "S01", "final_stages": ["S03"], "settings": {"demo_speed": 1}}
        for name, obj in [("config.json", config), ("workflow.json", flow), ("users.json", {"users": users})]:
            (base / name).write_text(json.dumps(obj), encoding="utf-8")
        if legacy:
            (self.root / "data").mkdir()
            with sqlite3.connect(self.root / "data/monthly_cycle.db") as db:
                db.execute("CREATE TABLE alerts(id INTEGER PRIMARY KEY,ts TEXT,user TEXT,kind TEXT,title TEXT,body TEXT,task_id INTEGER,bill_id TEXT,read INTEGER DEFAULT 0)")
                db.execute("INSERT INTO alerts(id,ts,user,kind,title,body,read) VALUES (1,'2026-01-01 09:00:00','Admin One','complete','Legacy notification','Preserve this history',1)")
            db.close()  # sqlite's context manager commits; it does not close the Windows file handle.
        self.g = {"__file__": str(base / "app.py"), "__name__": "somesh_test_app"}
        try:
            exec(compile((BACKEND / "app.py").read_text(encoding="utf-8"), str(base / "app.py"), "exec"), self.g)
            self.g["FRONTEND"] = str(PROJECT / "frontend")
            self.g["load_adhoc"]()
            self.server = self.g["ThreadingHTTPServer"](("127.0.0.1", 0), self.g["H"])
            self.server.daemon_threads = True
            self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.02), daemon=True)
            self.thread.start()
            self.origin = f"http://127.0.0.1:{self.server.server_port}"
        except Exception:
            if "DB" in self.g:
                self.g["DB"].close()
            self.temp.cleanup()
            raise

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.g["DB"].close()
        self.temp.cleanup()

    def request(self, path, body=None, token=None, binary=False):
        req = urllib.request.Request(self.origin + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **({"X-Session": token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read()
                return response.status, raw if binary else json.loads(raw)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def login(self, user="Admin One"):
        body = {"user": user}
        if self.g["is_admin"](user):
            body["pin"] = self.pin
        status, data = self.request("/api/login", body)
        if status != 200:
            raise AssertionError("Fixture sign-in failed")
        return data["token"]

    def task(self, title="Review evidence", owner="Worker One", checker="Admin One", submitted=False):
        code = self.g["create_adhoc"](title, [owner], checker, 4, "Verified evidence", "Admin One")
        tid = self.g["q"]("SELECT id FROM tasks WHERE stage=?", (code,))[0]["id"]
        if submitted:
            self.g["claim"](tid, owner)
            self.g["submit"](tid, owner, "Evidence for " + title)
        return tid

    def seed_browser(self):
        g = self.g
        overdue = self.task("Overdue evidence")
        g["x"]("UPDATE tasks SET due_at='2020-01-01 00:00:00' WHERE id=?", (overdue,))
        for message in ("Original deadline warning", "Repeated deadline warning"):
            g["alert"](["Admin One"], "overdue", "Overdue evidence", message, g["get_task"](overdue))
        review = self.task(submitted=True)
        start = g["ts"](g["now"]() - g["timedelta"](seconds=3))
        g["x"]("UPDATE work_log SET start=? WHERE task_id=?", (start, review))
        running = self.task("Running payroll", "Worker Two")
        g["claim"](running, "Worker Two")
        g["x"]("UPDATE work_log SET start=? WHERE task_id=?", (start, running))
        assignment = self.task("New manager task", "Admin One")
        bill = g["new_bill"]("Synthetic client", "Admin One")
        g["alert"](["Admin One"], "complete", "General update", "Synthetic activity update")
        return dict(overdue=overdue, review=review, running=running, assignment=assignment, bill=bill)
