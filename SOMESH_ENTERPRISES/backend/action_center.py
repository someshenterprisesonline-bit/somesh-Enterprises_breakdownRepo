"""Read-only operational projections. Existing workflows remain the source of truth."""
import io
import json
from datetime import datetime, timedelta
from xml.sax.saxutils import escape


def build_report(tasks, logs, events, users, definitions, stamp, day, workday, lunch, net_seconds, actor,
                 department="", person="", query="", workload="all", sort="attention"):
    lo = datetime.combine(day, datetime.min.time())
    hi = lo + timedelta(days=1)
    ds = day.isoformat()
    parse = lambda value: datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None
    on_day = lambda value: bool(value and str(value)[:10] == ds)
    tasks = [t for t in tasks if not str(t.get("bill_id") or "").startswith("DEMO-")]
    valid = {t["id"] for t in tasks}
    logs = [w for w in logs if w["task_id"] in valid]
    by_task, by_person, active = {}, {}, set()
    for w in logs:
        seconds = net_seconds(w["start"], w["end"] or stamp, lo, min(hi, stamp))
        total = net_seconds(w["start"], w["end"] or stamp)
        by_task[w["task_id"]] = by_task.get(w["task_id"], 0) + total
        by_person[w["user"]] = by_person.get(w["user"], 0) + seconds
        if seconds: active.add(w["user"])
    for e in events:
        if e.get("task_id") in valid and on_day(e["ts"]): active.add(e["actor"])
    start = datetime.combine(day, datetime.strptime(workday["start"], "%H:%M").time())
    end = datetime.combine(day, datetime.strptime(workday["end"], "%H:%M").time())
    working_day = day.weekday() in workday.get("days", [0, 1, 2, 3, 4, 5])
    capacity = net_seconds(start, end) if working_day else 0
    in_lunch = bool(lunch and lunch[0] <= stamp < lunch[1])
    expected = bool(day == stamp.date() and working_day and start <= stamp < end and not in_lunch
                    and net_seconds(start, stamp) >= 1800)
    rows = []
    for t in tasks:
        d = definitions[t["stage"]]
        owners = [t["assignee"]] if t["assignee"] else json.loads(t["owners"])
        complete_at = t.get("ended_at") if d.get("adhoc") else t.get("decided_at") if t["status"] == "approved" else None
        pending = t["status"] in ("assigned", "in_progress", "submitted") or (d.get("adhoc") and t["status"] == "approved" and not t.get("ended_at"))
        due = parse(t.get("due_at"))
        executable = t["status"] in ("assigned", "in_progress")
        overdue = bool(executable and due and due < stamp)
        remaining = net_seconds(stamp, due) if due and due >= stamp else 0
        late = net_seconds(due, stamp) if overdue else 0
        returned = bool(t["status"] == "in_progress" and t.get("rework_count") and t.get("decision_note"))
        approval = t["status"] == "submitted"
        documents = bool(d.get("adhoc") and t["status"] == "approved" and not t.get("ended_at"))
        approaching = bool(executable and due and due >= stamp and remaining <= 3600)
        own_approval = approval and t["validator"] == actor
        category = "overdue" if overdue else "approvals" if approval else "approaching" if approaching else "returned" if returned else "documents" if documents else "other"
        priority = 0 if overdue and late >= 7200 else 1 if own_approval else 2 if overdue else 3 if approaching else 4 if returned or documents else 5
        recommendation = ("Review the missed deadline and confirm the next owner" if overdue else
                          "Review submission" if own_approval else f"Follow up with approver {t['validator']}" if approval else
                          "Check progress before the deadline" if approaching else "Review the correction note" if returned else
                          "Follow up on documents / End task" if documents else "Monitor assigned work")
        rows.append(dict(id=t["id"], code=t["stage"], task=d["name"], dept=d.get("dept", ""),
                         people=owners, person=", ".join(owners) or "Unassigned", validator=t["validator"], bill=t.get("bill_id") or "",
                         due=t.get("due_at"), status=t["status"], status_label="Awaiting documents / End task" if documents else
                         "Returned for correction" if returned else {"assigned": "Assigned", "in_progress": "Running", "submitted": "Waiting for approval", "approved": "Completed"}.get(t["status"], t["status"]),
                         assigned_today=on_day(t["created_at"]), completed_today=on_day(complete_at), pending=bool(pending),
                         overdue=overdue, approaching=approaching, returned=returned, approval=approval, documents=documents,
                         category=category, priority=priority, late_seconds=late, remaining_seconds=remaining,
                         remaining_limit_seconds=max(0, float(d.get("sla_hours") or 0) * 3600 - by_task.get(t["id"], 0)),
                         can_review=own_approval, can_reassign=executable, note=t.get("decision_note") or "",
                         recommendation=recommendation))
    # Task filters operate on the task's team and actual assignee / eligible owner.
    filtered = [r for r in rows if (not department or r["dept"] == department) and (not person or person in r["people"])
                and (not query or query.lower() in " ".join([r["task"], r["code"], r["person"], r["dept"], r["bill"]]).lower())]
    people = []
    for user in users:
        name = user["name"]
        if department and user.get("dept", "") != department or person and name != person: continue
        owned = [r for r in rows if name in r["people"]]
        if query and query.lower() not in (name + " " + user.get("dept", "")).lower() and not any(r in filtered for r in owned): continue
        open_rows = [r for r in owned if r["pending"]]
        remaining = sum(r["remaining_limit_seconds"] for r in open_rows if r["status"] != "submitted" and not r["documents"])
        late_count = sum(r["overdue"] for r in owned)
        overload = bool(late_count >= 2 or capacity and remaining > capacity)
        # No leave data exists: this is a follow-up prompt, never an absence/performance finding.
        no_activity = bool(not user.get("admin") and expected and open_rows and name not in active)
        people.append(dict(person=name, dept=user.get("dept", ""), assigned=sum(r["assigned_today"] for r in owned),
                           completed=sum(r["completed_today"] for r in owned), pending=len(open_rows), overdue=late_count,
                           seconds=by_person.get(name, 0), recorded_activity=name in active, no_activity=no_activity,
                           remaining_seconds=remaining, capacity_seconds=capacity, overloaded=overload,
                           workload_reason="Multiple overdue assignments" if late_count >= 2 else
                           "Remaining configured task limits exceed one working day's capacity" if overload else "Within this review threshold"))
    if workload == "overloaded": people = [p for p in people if p["overloaded"]]
    elif workload == "no_activity": people = [p for p in people if p["no_activity"]]
    elif workload == "open": people = [p for p in people if p["pending"]]
    names = {p["person"] for p in people}
    if workload != "all": filtered = [r for r in filtered if names.intersection(r["people"])]
    people.sort(key=lambda p: (-(p["overdue"] * 100 + p["pending"]) if sort == "attention" else
                              -p["seconds"] if sort == "time" else -p["pending"] if sort == "pending" else 0, p["person"].lower()))
    counts = {key: sum(bool(r[key]) for r in filtered) for key in ("overdue", "approval", "completed_today", "approaching", "returned", "assigned_today", "documents")}
    counts["no_activity"] = sum(p["no_activity"] for p in people)
    counts["active_people"] = sum(p["recorded_activity"] for p in people)
    counts["people"] = len(people)
    queue = [r for r in filtered if r["category"] != "other"]
    queue.sort(key=lambda r: (r["priority"], -r["late_seconds"], r["due"] or "9999", r["id"]))
    queue += [dict(category="no_activity", priority=6, person=p["person"], people=[p["person"]], dept=p["dept"],
                   task="No recorded activity", status_label="Check availability", due=None, id=None,
                   recommendation="Verify availability / leave before following up") for p in people if p["no_activity"]]
    recommendations = []
    for key, count, text in [("overdue", counts["overdue"], "overdue tasks need deadline review"),
                             ("approvals", counts["approval"], "submissions are waiting for their designated approver"),
                             ("approaching", counts["approaching"], "tasks are due within 60 lunch-adjusted minutes"),
                             ("returned", counts["returned"], "tasks are currently back for correction"),
                             ("no_activity", counts["no_activity"], "employees with open work need an availability check")]:
        if count: recommendations.append(dict(filter=key, count=count, text=f"{count} {text}."))
    multiple = sum(p["overdue"] >= 2 for p in people)
    if multiple: recommendations.append(dict(filter="overdue", count=multiple, text=f"{multiple} employees have multiple overdue assignments."))
    return dict(date=ds, server_now=stamp.strftime("%Y-%m-%d %H:%M:%S"), counts=counts, queue=queue, tasks=filtered,
                people=people, recommendations=recommendations, activity_expected=expected,
                activity_note="Availability checks apply only today, during working hours outside lunch, after 30 working minutes, with open work. No leave/attendance register is available; verify availability first.",
                scope_note="Outstanding work uses current status. New assignment (creation), completion and activity totals use the selected date. Workload tasks use current owners; tracked time stays with the person who recorded it. Demo data is excluded. Shared unclaimed work appears for each eligible owner; task totals count it once.",
                thresholds=dict(approaching_minutes=60, critical_overdue_minutes=120, activity_grace_minutes=30),
                departments=sorted({u.get("dept", "") for u in users}), person_options=[u["name"] for u in users])


def export_report(report, fmt):
    summary = [("Date", report["date"])] + [(k.replace("_", " ").title(), v) for k, v in report["counts"].items()]
    headings = ["Employee", "Department", "Assigned on date", "Completed on date", "Pending now", "Overdue now", "Worked (HH:MM:SS)", "Workload review"]
    duration = lambda n: f"{int(n)//3600:02d}:{int(n)%3600//60:02d}:{int(n)%60:02d}"
    people = [[p["person"], p["dept"], p["assigned"], p["completed"], p["pending"], p["overdue"], duration(p["seconds"]), p["workload_reason"]] for p in report["people"]]
    qhead = ["Employee", "Department", "Task", "Deadline", "Status", "Recommended next action"]
    queue = [[r["person"], r["dept"], f"{r.get('code', '')} {r['task']}", r["due"] or "–", r["status_label"], r["recommendation"]] for r in report["queue"]]
    out = io.BytesIO()
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook(); wb.remove(wb.active)
        for name, header, rows in [("Operations summary", ["Metric", "Value"], summary + [("Scope", report["scope_note"]), ("Availability", report["activity_note"])]),
                                   ("Employee workload", headings, people), ("Needs attention", qhead, queue)]:
            sheet = wb.create_sheet(name); sheet.append(header)
            for row in rows:
                # Prevent spreadsheet formula execution from employee/task text.
                sheet.append(["'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for v in row])
            for cell in sheet[1]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="1D1D1F")
            for row in sheet:
                for cell in row: cell.alignment = Alignment(wrap_text=True, vertical="top")
            for column in sheet.columns: sheet.column_dimensions[column[0].column_letter].width = 26
            sheet.freeze_panes = "A2"; sheet.auto_filter.ref = sheet.dimensions
        wb.save(out)
    else:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
        from tracker_export import register_tracker_fonts
        register_tracker_fonts()
        normal = ParagraphStyle("action-cell", fontName="Tracker", fontSize=8, leading=11)
        bold = ParagraphStyle("action-header", parent=normal, fontName="TrackerBold")
        cell = lambda v: Paragraph(escape(str(v)).replace("\n", "<br/>"), normal)
        doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=30)
        story = [Paragraph("Admin Smart Action Center", ParagraphStyle("title", parent=bold, fontSize=18, leading=23)),
                 cell("Selected date: " + report["date"]), cell(report["scope_note"]), cell(report["activity_note"]), Spacer(1, 12)]
        for name, header, rows, weights in [("Operations summary", ["Metric", "Value"], summary, [1, 2]),
                                           ("Employee workload", headings, people, [1.2, 1, .7, .7, .7, .7, 1, 2]),
                                           ("Needs Your Attention", qhead, queue, [1, .8, 1.5, 1, 1, 1.8])]:
            story += [Paragraph(name, bold), Spacer(1, 6)]
            data = [[cell(v) for v in header]] + [[cell(v) for v in row] for row in rows or [["No records"] + [""] * (len(header) - 1)]]
            table = LongTable(data, colWidths=[doc.width * w / sum(weights) for w in weights], repeatRows=1, splitInRow=1)
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8ed")),
                                       ("GRID", (0, 0), (-1, -1), .4, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            story += [table, Spacer(1, 14)]
        def footer(canvas, document):
            canvas.setFont("Tracker", 8); canvas.drawString(24, 14, f"Action Center · {report['date']}")
            canvas.drawRightString(document.pagesize[0] - 24, 14, f"Page {document.page}")
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
