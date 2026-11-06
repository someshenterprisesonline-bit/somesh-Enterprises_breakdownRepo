import ast
import copy
import io
import json
import re
import threading
import unittest
from datetime import timedelta

from openpyxl import load_workbook
from pypdf import PdfReader
from support import AppFixture, PROJECT, BACKEND
from tracker_export import tracker_pdf


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture()
        self.g = self.app.g
        self.token = self.app.login()

    def tearDown(self):
        self.app.close()

    def test_version_and_static_script_dependencies(self):
        shell = (PROJECT / "frontend/js/core/shell.js").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'APP_VERSION = "v([^"]+)"', shell)[1], self.g["APP_VERSION"])
        html = (PROJECT / "frontend/index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="(/static/[^"]+)"', html)
        self.assertEqual(len(scripts), len(set(scripts)))
        for script in scripts:
            self.assertEqual(self.app.request(script, binary=True)[0], 200)
        tree = ast.parse((BACKEND / "app.py").read_text(encoding="utf-8"))
        names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual(len(names), len(set(names)))

    def test_admin_and_employee_authentication(self):
        self.assertEqual(self.app.request("/api/login", {"user": "Admin One"})[0], 400)
        self.assertEqual(self.app.request("/api/login", {"user": "Admin One", "pin": "invalid"})[0], 400)
        _, result = self.app.request("/api/login", {"user": "Worker One", "admin": True})
        self.assertFalse(result["admin"])
        self.assertEqual(self.app.request("/api/admins", token=result["token"])[0], 403)
        self.assertEqual(self.app.request("/api/admins", token="forged-session")[0], 401)
        self.assertEqual(self.app.request("/api/logout", {}, self.token)[0], 200)
        self.assertEqual(self.app.request("/api/me", token=self.token)[0], 401)

    def test_pin_throttle_and_malformed_requests(self):
        for _ in range(5):
            self.assertEqual(self.app.request("/api/login", {"user": "Admin One", "pin": "invalid"})[0], 400)
        status, error = self.app.request("/api/login", {"user": "Admin One", "pin": self.app.pin})
        self.assertEqual(status, 400)
        self.assertIn("Too many", error["error"])
        self.assertEqual(self.app.request("/api/login", ["invalid"])[0], 400)

    def test_admin_roles_persist_without_changing_profiles_or_work(self):
        tid = self.app.task()
        worker_session = self.app.login("Worker One")
        before = copy.deepcopy(self.g["USERS"])
        task_before = self.g["get_task"](tid)
        body = {"user": "Worker One", "admin": True, "confirmation_pin": self.app.pin}
        self.assertEqual(self.app.request("/api/admins/role", body, worker_session)[0], 403)
        self.assertEqual(self.app.request("/api/admins/role", body, self.token)[0], 200)
        self.assertEqual(self.app.request("/api/me", token=worker_session)[0], 401)
        self.assertEqual(self.app.request("/api/login", {"user": "Worker One"})[0], 400)
        promoted = self.app.login("Worker One")
        stored = json.loads((self.app.root / "backend/users.json").read_text())
        self.assertTrue(next(u for u in stored["users"] if u["name"] == "Worker One")["admin"])
        body["admin"] = False
        self.assertEqual(self.app.request("/api/admins/role", body, self.token)[0], 200)
        self.assertEqual(self.app.request("/api/me", token=promoted)[0], 401)
        self.assertEqual(self.g["get_task"](tid), task_before)
        for original in before:
            actual = next(u for u in self.g["USERS"] if u["name"] == original["name"])
            self.assertEqual({k: v for k, v in original.items() if k != "admin"}, {k: v for k, v in actual.items() if k != "admin"})
        audit = self.g["q"]("SELECT * FROM events WHERE kind='admin_access'")
        self.assertEqual(len(audit), 2)
        self.assertTrue(all(row["actor"] == "Admin One" and row["ts"] for row in audit))

    def test_last_admin_and_confirmation_guard(self):
        body = {"user": "Admin Two", "admin": False, "confirmation_pin": "invalid"}
        self.assertEqual(self.app.request("/api/admins/role", body, self.token)[0], 400)
        body["confirmation_pin"] = self.app.pin
        self.assertEqual(self.app.request("/api/admins/role", body, self.token)[0], 200)
        body["user"] = "Admin One"
        status, result = self.app.request("/api/admins/role", body, self.token)
        self.assertEqual(status, 400)
        self.assertIn("last active Admin", result["error"])

    def test_task_assignment_approval_return_and_end(self):
        worker = self.app.login("Worker One")
        status, result = self.app.request("/api/assign", {"tasks": [{"title": "Assigned evidence", "who": "Worker One", "checker": "Admin One", "hours": 2}]}, self.token)
        self.assertEqual(status, 200)
        tid = self.g["q"]("SELECT id FROM tasks WHERE stage=?", (result["codes"][0],))[0]["id"]
        for action in ("claim", "submit"):
            self.assertEqual(self.app.request(f"/api/tasks/{tid}/{action}", {}, worker)[0], 200)
        self.assertEqual(self.app.request(f"/api/tasks/{tid}/approve", {}, self.app.login("Admin Two"))[0], 400)
        self.assertEqual(self.app.request(f"/api/tasks/{tid}/reject", {"note": "Add evidence"}, self.token)[0], 200)
        self.assertEqual(self.g["get_task"](tid)["rework_count"], 1)
        self.assertEqual(self.app.request(f"/api/tasks/{tid}/submit", {}, worker)[0], 200)
        self.assertEqual(self.app.request(f"/api/tasks/{tid}/approve", {}, self.token)[0], 200)
        self.assertEqual(self.app.request(f"/api/tasks/{tid}/end", {}, worker)[0], 200)
        self.assertIsNotNone(self.g["get_task"](tid)["ended_at"])

    def test_new_bill_branch_and_completion(self):
        status, result = self.app.request("/api/bills", {"client": "Synthetic client"}, self.token)
        self.assertEqual(status, 200)
        bid = result["bills"][0]
        for stage, owner, branch in [("S01", "Worker One", None), ("S02", "Worker Two", "No"), ("S03", "Admin One", None)]:
            tid = self.g["q"]("SELECT id FROM tasks WHERE bill_id=? AND stage=?", (bid, stage))[0]["id"]
            user = self.app.login(owner)
            self.assertEqual(self.app.request(f"/api/tasks/{tid}/claim", {}, user)[0], 200)
            self.assertEqual(self.app.request(f"/api/tasks/{tid}/submit", {"branch": branch}, user)[0], 200)
            if owner != "Admin One":
                self.assertEqual(self.app.request(f"/api/tasks/{tid}/approve", {}, self.token)[0], 200)
        self.assertEqual(self.g["q"]("SELECT status FROM bills WHERE id=?", (bid,))[0]["status"], "complete")

    def test_lunch_lock_and_time_exclusion(self):
        tid = self.app.task()
        g = self.g
        g["CONFIG"]["lunch"] = {"enabled": True, "start": "13:00", "end": "14:00"}
        self.assertEqual(g["net_seconds"]("2026-01-05 12:30:00", "2026-01-05 14:30:00"), 3600)
        original = g["is_lunch"]
        g["is_lunch"] = lambda: True
        try:
            status, result = self.app.request(f"/api/tasks/{tid}/claim", {}, self.app.login("Worker One"))
            self.assertEqual(status, 400)
            self.assertIn("Lunch", result["error"])
            self.assertEqual(g["get_task"](tid)["status"], "assigned")
        finally:
            g["is_lunch"] = original

    def test_alert_priority_grouping_read_and_snooze(self):
        info = self.app.seed_browser()
        status, data = self.app.request("/api/alerts", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(data["counts"]["urgent"], 1)
        group = next(g for g in data["groups"] if g["task"] and g["task"]["id"] == info["overdue"])
        self.assertEqual(len(group["records"]), 2)
        self.assertEqual(self.app.request("/api/alerts/snooze", {"ids": [group["latest"]["id"]], "minutes": 15}, self.token)[0], 400)
        pending = next(g for g in data["groups"] if g["can_review"])
        self.assertEqual(self.app.request("/api/alerts/read", {"ids": [pending["latest"]["id"]]}, self.token)[0], 200)
        self.assertEqual(self.g["get_task"](info["review"])["status"], "submitted")
        assignment = next(g for g in data["groups"] if g["task"] and g["task"]["id"] == info["assignment"])
        self.assertEqual(self.app.request("/api/alerts/snooze", {"ids": [assignment["latest"]["id"]], "minutes": 15}, self.token)[0], 200)
        self.g["x"]("UPDATE tasks SET due_at='2020-01-01 00:00:00' WHERE id=?", (info["assignment"],))
        refreshed = self.app.request("/api/alerts", token=self.token)[1]
        self.assertTrue(next(g for g in refreshed["groups"] if g["key"] == assignment["key"])["urgent"])

    def test_alert_recipient_isolation_and_id_validation(self):
        self.g["alert"](["Admin Two"], "complete", "Private recipient", "Other account")
        foreign = self.g["q"]("SELECT id FROM alerts WHERE user='Admin Two'")[0]["id"]
        self.assertEqual(self.app.request("/api/alerts", token=self.app.login("Worker One"))[0], 403)
        self.assertEqual(self.app.request("/api/alerts/read", {"ids": [foreign]}, self.token)[0], 403)
        self.assertEqual(self.app.request(f"/api/alerts/{foreign}/task", token=self.token)[0], 403)
        self.assertEqual(self.app.request("/api/alerts/read", {"ids": [2 ** 100]}, self.token)[0], 400)

    def test_tracker_exports_and_selected_date(self):
        self.app.seed_browser()
        day = self.g["ts"]()[:10]
        data = self.app.request(f"/api/tracker?date={day}", token=self.token)[1]
        self.assertTrue(data["rows"])
        for suffix in ("export", "export.pdf"):
            status, raw = self.app.request(f"/api/tracker/{suffix}?date={day}", token=self.token, binary=True)
            self.assertEqual(status, 200)
            if suffix.endswith("pdf"):
                text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
                self.assertIn("Employee Task Tracker", text)
                self.assertIn("00:00:03", text)
            else:
                workbook = load_workbook(io.BytesIO(raw))
                self.assertEqual(workbook.sheetnames, ["Tasks", "Per person", "Time log", "Notes"])
                self.assertEqual(workbook["Tasks"].max_row, len(data["rows"]) + 1)
        empty = self.app.request("/api/tracker/export.pdf?date=2000-01-01", token=self.token, binary=True)[1]
        self.assertIn("No tracked tasks", PdfReader(io.BytesIO(empty)).pages[0].extract_text())

    def test_pdf_wraps_and_repeats_headers_without_losing_records(self):
        tid = self.app.task(submitted=True)
        tr = self.g["tracker"](self.g["now"]().date())
        row = tr["rows"][0]
        tr["rows"] = [dict(row, code=f"RECORD{i:04d}", task="Long task & <evidence> " * 15) for i in range(60)]
        pdf = PdfReader(io.BytesIO(tracker_pdf(tr)))
        self.assertGreater(len(pdf.pages), 2)
        text = "\n".join(page.extract_text() for page in pdf.pages)
        for i in range(60):
            self.assertIn(f"RECORD{i:04d}", text)
        for page in pdf.pages:
            self.assertGreater(float(page.mediabox.width), float(page.mediabox.height))
            for label in ("Person", "Task", "Started", "Done", "Approved", "Ended", "Worked", "Status", "Docs"):
                self.assertIn(label, page.extract_text())
        tr["rows"] = [dict(row, task="Very long evidence " * 2200 + " FINAL_MARKER")]
        self.assertIn("FINAL_MARKER", "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(tracker_pdf(tr))).pages))

    def test_rule_validation_deduplication_and_error_isolation(self):
        tid = self.app.task()
        rule = {"name": "Submission review", "enabled": True, "trigger": "task_submitted", "conditions": {"dept": "Operations"},
                "actions": [{"type": "alert", "to": "admins", "message": "Check {task} from {person}"}]}
        rid = self.g["save_rule"](rule, "Admin One")["id"]
        task = self.g["get_task"](tid)
        threads = [threading.Thread(target=self.g["fire_rules"], args=("task_submitted", task)) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(self.g["q"]("SELECT * FROM rule_runs WHERE rule_id=?", (rid,))), 1)
        invalid = dict(rule, actions=[{"type": "reassign_to", "person": "Unknown account"}])
        self.assertEqual(self.app.request("/api/rules", invalid, self.token)[0], 400)
        self.g["x"]("INSERT INTO rules(name,enabled,trigger,conditions,actions) VALUES ('Broken',1,'task_started','invalid','[]')")
        good = self.g["save_rule"](dict(rule, trigger="task_started"), "Admin One")["id"]
        self.g["fire_rules"]("task_started", task)
        self.assertEqual(self.g["q"]("SELECT result FROM rule_runs WHERE rule_id=?", (good,))[0]["result"], "fired")

    def test_rule_department_filter_through_real_task_apis(self):
        rule = {"name": "Operations submission check", "enabled": True, "trigger": "task_submitted",
                "conditions": {"dept": "Operations"},
                "actions": [{"type": "alert", "to": "admins", "message": "Please check {task} from {person}"}]}
        status, saved = self.app.request("/api/rules", rule, self.token)
        self.assertEqual(status, 200)
        for owner in ("Worker One", "Worker Two"):
            tid = self.app.task("Evidence for " + owner, owner)
            staff = self.app.login(owner)
            self.assertEqual(self.app.request(f"/api/tasks/{tid}/claim", {}, staff)[0], 200)
            self.assertEqual(self.app.request(f"/api/tasks/{tid}/submit", {"note": "Verified"}, staff)[0], 200)
        runs = self.app.request("/api/rules/log", token=self.token)[1]["runs"]
        self.assertEqual(len(runs), 1)
        state = self.app.request("/api/state", token=self.token)[1]
        messages = [a["body"] for a in state["alerts"] if a["body"].startswith("Please check TASK-")]
        self.assertEqual(len(messages), 1)
        self.assertIn("Evidence for Worker One from Worker One", messages[0])
        self.assertIsInstance(self.app.request(f"/api/rules/{saved['rule']['id']}/test", {}, self.token)[1]["would_fire"], int)

    def test_rule_schedules_dry_run_and_recursion_guard(self):
        tid = self.app.task()
        self.g["x"]("UPDATE tasks SET created_at='2020-01-01 00:00:00' WHERE id=?", (tid,))
        rule = {"name": "Start idle", "enabled": True, "trigger": "task_not_started", "when": {"hours": 1},
                "actions": [{"type": "start_automatically"}]}
        self.g["save_rule"](rule, "Admin One")
        self.g["rules_tick"](); self.g["rules_tick"]()
        self.assertEqual(self.g["get_task"](tid)["status"], "in_progress")
        self.assertEqual(len(self.g["q"]("SELECT * FROM rule_runs")), 1)
        recurring = {"name": "Give template", "enabled": True, "trigger": "task_assigned", "actions": [{"type": "give_template", "template": "Courier dispatch", "to": "dept:Operations"}]}
        rid = self.g["save_rule"](recurring, "Admin One")["id"]
        self.app.task("Trigger one template")
        self.assertEqual(len(self.g["q"]("SELECT * FROM rule_runs WHERE rule_id=?", (rid,))), 1)
        before = self.g["q"]("SELECT * FROM tasks")
        self.assertIsInstance(self.g["rule_test"](rid)["would_fire"], int)
        self.assertEqual(before, self.g["q"]("SELECT * FROM tasks"))

    def test_orphaned_time_history_does_not_break_tracker_or_storage(self):
        self.app.seed_browser()
        self.g["x"]("INSERT INTO work_log(task_id,user,start,end) VALUES (999999,'Worker One',?,?)",
                    (self.g["ts"](), self.g["ts"]()))
        original = self.g["q"]("SELECT * FROM work_log")
        day = self.g["ts"]()[:10]
        for path in ("/api/tracker", "/api/tracker/export", "/api/tracker/export.pdf", "/api/dashboard", "/api/timetable"):
            self.assertEqual(self.app.request(path + "?date=" + day, token=self.token, binary=True)[0], 200, path)
        self.g["CONFIG"]["storage"]["enabled"] = True
        self.g["storage_sync"]()
        self.assertEqual(self.g["STORAGE_STATUS"]["error"], "")
        self.assertEqual(original, self.g["q"]("SELECT * FROM work_log"))

    def test_existing_admin_modules_and_employee_authorization(self):
        self.app.seed_browser()
        endpoints = ["/api/state", "/api/dashboard", "/api/pipeline", "/api/adhoc", "/api/automation", "/api/rules", "/api/workflow-model", "/api/timetable"]
        for path in endpoints:
            self.assertEqual(self.app.request(path, token=self.token)[0], 200, path)
            if path != "/api/state":
                self.assertEqual(self.app.request(path, token=self.app.login("Worker One"))[0], 403, path)


class MigrationTests(unittest.TestCase):
    def test_legacy_alert_records_and_read_flags_are_preserved(self):
        app = AppFixture(legacy=True)
        try:
            alert = app.g["q"]("SELECT * FROM alerts WHERE id=1")[0]
            self.assertEqual(alert["body"], "Preserve this history")
            self.assertEqual(alert["read"], 1)
            self.assertIsNone(alert["snoozed_until"])
            self.assertEqual(len(app.g["q"]("SELECT * FROM rules")), 3)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
