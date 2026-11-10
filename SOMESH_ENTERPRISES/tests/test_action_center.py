import copy
import io
import json
import unittest
from datetime import datetime, timedelta
from urllib.parse import urlencode

from openpyxl import load_workbook
from pypdf import PdfReader
from support import AppFixture
from action_center import export_report


class ActionCenterTests(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture()
        self.g = self.app.g
        self.stamp = datetime(2026, 11, 6, 11)
        self.g["now"] = lambda: self.stamp
        self.g["CONFIG"]["workday"] = {"start": "09:30", "end": "18:30", "days": [0, 1, 2, 3, 4]}
        self.g["CONFIG"]["lunch"] = {"enabled": True, "start": "13:00", "end": "14:00"}
        self.token = self.app.login()

    def tearDown(self):
        self.app.close()

    def report(self, **filters):
        status, data = self.app.request("/api/action-center?" + urlencode(filters), token=self.token)
        self.assertEqual(status, 200, data)
        return data

    def seed(self):
        critical = self.app.task("Critical deadline")
        late = self.app.task("Recent deadline")
        for tid, due in [(critical, "08:30:00"), (late, "10:45:00")]:
            self.g["x"]("UPDATE tasks SET due_at=? WHERE id=?", ("2026-11-06 " + due, tid))
        pending = self.app.task("Review payroll", "Worker Two", submitted=True)
        approaching = self.app.task("Due soon", "Reviewer")
        self.g["x"]("UPDATE tasks SET due_at='2026-11-06 11:45:00' WHERE id=?", (approaching,))
        returned = self.app.task("Correct evidence", submitted=True)
        self.g["reject"](returned, "Admin One", "Please fix totals")
        completed = self.app.task("Completed finance", "Admin Two", submitted=True)
        self.g["approve"](completed, "Admin One"); self.g["end_task"](completed, "Admin Two")
        demo = self.app.task("Excluded demo", "Reviewer")
        self.g["x"]("UPDATE tasks SET bill_id='DEMO-test',due_at='2020-01-01 00:00:00' WHERE id=?", (demo,))
        return dict(critical=critical, late=late, pending=pending, approaching=approaching, returned=returned, completed=completed, demo=demo)

    def test_counts_priority_and_read_only_projection(self):
        ids = self.seed()
        before = {name: self.g["q"]("SELECT * FROM " + name) for name in ("tasks", "work_log", "alerts", "events")}
        report = self.report()
        c = report["counts"]
        self.assertEqual((c["overdue"], c["approval"], c["completed_today"], c["approaching"], c["returned"], c["no_activity"]), (2, 1, 1, 1, 1, 1))
        self.assertEqual(c["assigned_today"], 6)
        self.assertEqual([r["id"] for r in report["queue"][:4]], [ids["critical"], ids["pending"], ids["late"], ids["approaching"]])
        self.assertNotIn(ids["demo"], [r["id"] for r in report["tasks"]])
        worker = next(p for p in report["people"] if p["person"] == "Worker One")
        self.assertTrue(worker["overloaded"])
        self.assertTrue(any(r["filter"] == "overdue" for r in report["recommendations"]))
        for name, rows in before.items(): self.assertEqual(rows, self.g["q"]("SELECT * FROM " + name))

    def test_activity_grace_working_hours_lunch_and_no_assignment(self):
        self.app.task("Available work", "Reviewer")
        for stamp, expected in [(datetime(2026, 11, 6, 9, 45), False), (datetime(2026, 11, 6, 10), True),
                                (datetime(2026, 11, 6, 13, 30), False), (datetime(2026, 11, 6, 19), False),
                                (datetime(2026, 11, 8, 11), False)]:
            self.stamp = stamp
            d = self.report()
            self.assertEqual(d["activity_expected"], expected)
            self.assertEqual(d["counts"]["no_activity"], int(expected))
        self.stamp = datetime(2026, 11, 6, 11)
        self.assertEqual(self.report(date="2026-11-05")["counts"]["no_activity"], 0)

    def test_lunch_time_and_completion_semantics(self):
        tid = self.app.task(submitted=True)
        self.g["approve"](tid, "Admin One")
        self.assertEqual(self.report()["counts"]["completed_today"], 0)
        self.assertEqual(self.report()["counts"]["documents"], 1)
        self.g["end_task"](tid, "Worker One")
        self.g["x"]("UPDATE work_log SET start='2026-11-06 12:30:00',end='2026-11-06 14:30:00' WHERE task_id=?", (tid,))
        self.stamp = datetime(2026, 11, 6, 15)
        d = self.report()
        self.assertEqual(d["counts"]["completed_today"], 1)
        self.assertEqual(next(p for p in d["people"] if p["person"] == "Worker One")["seconds"], 3600)
        self.assertEqual(self.report(date="2026-11-05")["counts"]["completed_today"], 0)

    def test_filters_sorts_and_shared_ownership(self):
        self.seed()
        self.assertEqual(self.report(department="Payroll")["counts"]["overdue"], 0)
        self.assertEqual(len(self.report(person="Worker Two")["people"]), 1)
        self.assertTrue(all(r["dept"] == "Operations" for r in self.report(department="Operations")["tasks"]))
        self.assertEqual(len(self.report(q="Critical deadline")["tasks"]), 1)
        self.assertTrue(all(p["overloaded"] for p in self.report(workload="overloaded")["people"]))
        d = self.report(sort="name")
        self.assertEqual([p["person"] for p in d["people"]], sorted(p["person"] for p in d["people"]))
        code = self.g["create_adhoc"]("Shared work", ["Worker One", "Reviewer"], "Admin One", 1, "Evidence", "Admin One")
        shared = next(r for r in self.report()["tasks"] if r["code"] == code)
        self.assertEqual(set(shared["people"]), {"Worker One", "Reviewer"})

    def test_authorization_and_validation(self):
        tid = self.app.task()
        staff = self.app.login("Worker One")
        for path in ("/api/action-center", "/api/action-center/export.xlsx", "/api/action-center/export.pdf", f"/api/action-center/task/{tid}"):
            self.assertEqual(self.app.request(path)[0], 401)
            self.assertEqual(self.app.request(path, token=staff)[0], 403)
        self.assertEqual(self.app.request("/api/action-center/reassign", {}, staff)[0], 403)
        for qs in ("date=wrong", "date=2099-01-01", "department=unknown", "person=unknown", "sort=bad", "workload=bad"):
            self.assertEqual(self.app.request("/api/action-center?" + qs, token=self.token)[0], 400)
        self.assertEqual(self.app.request("/api/action-center/task/" + str(2**100), token=self.token)[0], 400)

    def test_reassignment_confirmation_stale_state_busy_guard_and_timers(self):
        tid = self.app.task()
        self.g["claim"](tid, "Worker One")
        self.g["x"]("UPDATE work_log SET start='2026-11-06 10:30:00' WHERE task_id=?", (tid,))
        task = self.app.request(f"/api/action-center/task/{tid}", token=self.token)[1]["task"]
        expected = {key: task[key] for key in ("status", "assignee", "claimed_at", "owners")}
        body = dict(task_id=tid, person="Reviewer", expected=expected, confirmed=True)
        self.assertEqual(self.app.request("/api/action-center/reassign", dict(body, confirmed=False), self.token)[0], 400)
        self.assertEqual(self.app.request("/api/action-center/reassign", dict(body, person="Worker Two"), self.token)[0], 400)
        stale = copy.deepcopy(body); stale["expected"]["status"] = "assigned"
        self.assertEqual(self.app.request("/api/action-center/reassign", stale, self.token)[0], 400)
        busy = self.app.task("Reviewer busy", "Reviewer"); self.g["claim"](busy, "Reviewer")
        self.assertEqual(self.app.request("/api/action-center/reassign", body, self.token)[0], 400)
        self.g["submit"](busy, "Reviewer", "Evidence"); self.g["approve"](busy, "Admin One"); self.g["end_task"](busy, "Reviewer")
        self.assertEqual(self.app.request("/api/action-center/reassign", body, self.token)[0], 200)
        current = self.g["get_task"](tid)
        self.assertEqual(current["validator"], task["validator"])
        self.assertEqual(current["assignee"], "Reviewer")
        logs = self.g["q"]("SELECT * FROM work_log WHERE task_id=? ORDER BY id", (tid,))
        self.assertEqual(len(logs), 2)
        self.assertIsNotNone(logs[0]["end"]); self.assertIsNone(logs[1]["end"])
        self.assertEqual(self.g["worked"](tid)[0], 1800)
        self.assertEqual(self.app.request("/api/action-center/reassign", body, self.token)[0], 400)

    def test_filtered_exports_and_large_tables(self):
        self.seed()
        for suffix in ("xlsx", "pdf"):
            status, data = self.app.request(f"/api/action-center/export.{suffix}?department=Payroll", token=self.token, binary=True)
            self.assertEqual(status, 200)
            if suffix == "xlsx":
                wb = load_workbook(io.BytesIO(data)); self.assertEqual(len(wb.sheetnames), 3)
                self.assertEqual(wb["Employee workload"].max_row, 2)
            else:
                text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
                self.assertIn("Review payroll", text); self.assertNotIn("Critical deadline", text)
        report = self.report()
        row = report["queue"][0]
        report["queue"] = [dict(row, task=f"UNIQUE{i:04d} " + "Long wrapped task description " * 18) for i in range(80)]
        pdf = PdfReader(io.BytesIO(export_report(report, "pdf")))
        self.assertGreater(len(pdf.pages), 3)
        text = "\n".join(page.extract_text() for page in pdf.pages)
        for i in range(80): self.assertIn(f"UNIQUE{i:04d}", text)
        for page in pdf.pages[1:]:
            self.assertGreater(float(page.mediabox.width), float(page.mediabox.height))
            self.assertIn("Recommended next action", page.extract_text())
        report["people"][0]["person"] = "=dangerous-formula"
        wb = load_workbook(io.BytesIO(export_report(report, "xlsx")))
        self.assertEqual(wb["Employee workload"]["A2"].data_type, "s")


if __name__ == "__main__": unittest.main()
