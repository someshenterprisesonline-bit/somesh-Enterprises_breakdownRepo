"""Workflow input workbook: read, check and write the Excel / Google Sheet that defines the process.

Sheets
  Stages         one row per stage: who does it, who checks it, time limit, what comes next
  People         everyone who uses the app
  Bills to open  clients to open a bill for when the file is loaded (optional)
  Settings       time speed and who else gets alerts

The app turns the rows into workflow.json + users.json, so tasks and alerts follow the file.
"""
import io, re

STAGE_COLS = ["Stage Code", "Stage Name", "Department", "Done by", "Checked by", "Time limit (hours)",
              "Next stages", "Waits for", "Also waits for (if it ran)", "Decision question",
              "If Yes also start", "If No also start", "Output expected", "Also alert", "Accepted files", "File required",
              "Start stage", "Final stage"]
PEOPLE_COLS = ["Name", "Department", "Role", "Email", "Admin", "Lead"]
BILL_COLS = ["Client", "Notes"]
SETTINGS = [
    ("Time speed", 1, "1 = real time (use this). Demo bills always run 60x faster on their own."),
    ("Overdue alert to checker", "Yes", "Yes = the checker also gets the red overdue alert, not just the person doing it."),
    ("Bill complete alert to admins", "Yes", "Yes = admins get an alert when a bill reaches its final stage."),
]
HINTS = {
    "Stage Code": "Short unique code, e.g. S01",
    "Done by": "Names from People, comma separated. All of them get the new-task alert",
    "Checked by": "One name. Gets the 'Please check' alert. Same as Done by = no check",
    "Time limit (hours)": "After this, doer + checker get an overdue alert",
    "Next stages": "Codes started after approval, comma separated",
    "Waits for": "Codes that must ALL be approved before this stage starts",
    "Also waits for (if it ran)": "Codes to wait for only if they were started",
    "Decision question": "Optional Yes / No question asked on Submit",
    "If Yes also start": "Codes added when the answer is Yes",
    "Also alert": "Extra names copied on new-task and overdue alerts",
    "Accepted files": "File types people attach on Submit, e.g. xlsx, pdf. Blank = any file",
    "File required": "Yes = Submit needs at least one attached file or a path",
    "Start stage": "Yes on exactly one row: every new bill starts here",
    "Final stage": "Yes = the bill is complete when this stage is approved",
}


class InputError(Exception):
    pass


def _need_openpyxl():
    try:
        import openpyxl  # noqa
        return openpyxl
    except ImportError:
        raise InputError("The Excel reader (openpyxl) is not installed. Close the app and start it again with "
                         "'START SOMESH ENTERPRISES.bat', which installs it.")


def _names(v):
    if v is None: return []
    return [p.strip() for p in re.split(r"[,;\n]+", str(v)) if p.strip()]


def _yes(v):
    return str(v or "").strip().lower() in ("yes", "y", "true", "1", "x", "✓")


def _cell(v):
    if v is None: return ""
    if isinstance(v, float) and v.is_integer(): v = int(v)
    return str(v).strip()


def _norm(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


# Other names people use for the same column, so a department's own sheet works as it is.
SYNONYMS = {
    "Stage Code": ["stagecode", "code", "taskcode", "stepcode", "taskid", "stageid", "stepid", "id", "taskno", "stepno", "no", "sno", "slno"],
    "Stage Name": ["stagename", "stage", "task", "taskname", "activity", "activityname", "step", "stepname", "work", "workassigned",
                   "nameoftheworkassigned", "nameofwork", "description", "taskdescription", "process"],
    "Department": ["department", "dept", "team", "section", "division", "unit"],
    "Done by": ["doneby", "owner", "owners", "assignedto", "assignee", "responsible", "doer", "person", "staff", "employee", "who",
                "handledby", "performedby", "members"],
    "Checked by": ["checkedby", "checker", "approver", "approvedby", "validator", "validatedby", "reviewer", "reviewedby", "verifiedby",
                   "verifier", "supervisor", "lead"],
    "Time limit (hours)": ["timelimithours", "timelimit", "hours", "sla", "slahours", "tat", "tathours", "duration", "durationhours",
                           "turnaround", "turnaroundtime", "timehours", "deadlinehours"],
    "Next stages": ["nextstages", "next", "nextstage", "nexttask", "nexttasks", "then", "followedby", "handoverto", "handsoverto", "successors"],
    "Waits for": ["waitsfor", "dependson", "dependencies", "dependency", "requires", "predecessors", "after", "prerequisites"],
    "Also waits for (if it ran)": ["alsowaitsforifitran", "alsowaitsfor", "optionalwaitsfor", "optionaldependencies"],
    "Decision question": ["decisionquestion", "question", "decision", "condition"],
    "If Yes also start": ["ifyesalsostart", "ifyes", "yesstart", "yesnext"],
    "If No also start": ["ifnoalsostart", "ifno", "nostart", "nonext"],
    "Output expected": ["outputexpected", "output", "deliverable", "deliverables", "expectedoutput", "result"],
    "Also alert": ["alsoalert", "cc", "notify", "alsonotify", "copyto", "inform"],
    "Accepted files": ["acceptedfiles", "filetypes", "accepted", "allowedfiles", "fileformat", "fileformats", "inputfile", "inputfiles"],
    "File required": ["filerequired", "uploadrequired", "attachmentrequired", "requiresfile"],
    "Start stage": ["startstage", "start", "first", "isstart"],
    "Final stage": ["finalstage", "final", "last", "end", "isfinal"],
    "Name": ["name", "employeename", "staffname", "person", "member", "fullname"],
    "Role": ["role", "designation", "designination", "title", "position", "jobtitle"],
    "Email": ["email", "emailid", "mail", "emailaddress"],
    "Admin": ["admin", "isadmin", "administrator"],
    "Lead": ["lead", "islead", "teamlead", "head"],
    "Client": ["client", "clientname", "customer", "company", "site"],
    "Notes": ["notes", "note", "remarks", "comment", "comments"],
    "Setting": ["setting", "settings", "key"],
    "Value": ["value", "val"],
}
SHEETS = {"Stages": ["stages", "tasks", "workflow", "process", "activities", "steps", "stagelist", "tasklist"],
          "People": ["people", "staff", "employees", "team", "members", "users", "persons"],
          "Bills to open": ["billstoopen", "bills", "clients", "openbills"],
          "Settings": ["settings", "config"]}


def _rows(ws, cols, key=None):
    """Find the header row (within the first 10 rows) by known names or their synonyms; return [(row, {col: value})], {col: index}."""
    key = key or cols[0]
    best = None
    for r in range(1, min(ws.max_row, 10) + 1):
        vals = [_norm(c.value) for c in ws[r]]
        idx = {}
        for c in cols:
            for i, v in enumerate(vals):
                if v and (v == _norm(c) or v in SYNONYMS.get(c, [])) and i not in idx.values():
                    idx[c] = i; break
        if key in idx and (best is None or len(idx) > len(best[1])): best = (r, idx)
    if best is None:
        raise InputError(f"Sheet '{ws.title}': can't find the header row (a column like '{key}').")
    header_row, idx = best
    out = []
    for r in range(header_row + 1, ws.max_row + 1):
        row = [c.value for c in ws[r]]
        rec = {c: (row[i] if i < len(row) else None) for c, i in idx.items()}
        if all(_cell(v) == "" for v in rec.values()): continue
        out.append((r, rec))
    return out, idx


def _sheet(wb, name):
    for ws in wb.worksheets:
        if _norm(ws.title) in [_norm(name)] + SHEETS.get(name, []): return ws
    return None


def _code_prefix(dept):
    words = [w for w in re.split(r"[^A-Za-z]+", dept or "") if w and w.lower() not in ("and", "of", "the")]
    return ("".join(w[0] for w in words[:3]).upper() or "ST")


def parse(data, current_flow=None, current_users=None, merge=False):
    """bytes of an .xlsx -> dict(flow, users, bills, errors, warnings, merged).

    Works with the template or a department's own sheet: column and sheet names may vary (see SYNONYMS), codes are made up
    when missing, rows run one after another when no 'Next stages' column is given, people come from the People sheet or,
    without one, from the names in the stages. merge=True updates only the stages in this file and keeps the rest."""
    openpyxl = _need_openpyxl()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:
        raise InputError("This isn't a readable Excel file (.xlsx). In Google Sheets the link must be shared as "
                         "'Anyone with the link: Viewer'. Details: " + str(e)[:200])
    errors, warnings = [], []
    current_flow = current_flow or {"stages": [], "start_stage": "", "final_stages": []}
    current_users = current_users or []
    ws_s = _sheet(wb, "Stages")
    if not ws_s:   # any sheet with a task / stage column
        for ws in wb.worksheets:
            try: _rows(ws, STAGE_COLS, "Stage Name"); ws_s = ws; break
            except InputError: pass
    if not ws_s: raise InputError("No sheet with a list of tasks was found. Name a sheet 'Stages' (or 'Tasks') with a 'Stage Name' (or 'Task') column.")
    ws_p = _sheet(wb, "People")

    # ---- people
    users, seen = [], set()
    if ws_p:
        try: prow, pidx = _rows(ws_p, PEOPLE_COLS, "Name")
        except InputError as e: errors.append(str(e)); prow, pidx = [], {}
        for r, rec in prow:
            name = _cell(rec.get("Name"))
            if not name: continue
            if name.lower() in seen: errors.append(f"People row {r}: '{name}' appears twice."); continue
            seen.add(name.lower())
            u = {"name": name, "dept": _cell(rec.get("Department")), "role": _cell(rec.get("Role")), "email": _cell(rec.get("Email"))}
            if not u["dept"]: warnings.append(f"People row {r}: department for '{name}' is empty.")
            if u["email"] and "@" not in u["email"]: warnings.append(f"People row {r}: '{u['email']}' doesn't look like an email.")
            if _yes(rec.get("Admin")): u["admin"] = True
            if _yes(rec.get("Lead")): u["lead"] = True
            users.append(u)
    if merge or not ws_p:   # keep everyone already in the app; the file adds or updates people
        given = {u["name"].lower() for u in users}
        users = [dict(u) for u in current_users if u["name"].lower() not in given] + users
        if not ws_p: warnings.append("No People sheet: kept the people already in the app; new names in the stages are added.")
    names = {u["name"].lower(): u["name"] for u in users}
    auto_people = not ws_p

    def person(v, where, dept=""):
        out = []
        for n in _names(v):
            if n.lower() in names: out.append(names[n.lower()])
            elif auto_people:
                users.append({"name": n, "dept": dept, "role": "", "email": ""}); names[n.lower()] = n; out.append(n)
                warnings.append(f"Added '{n}' ({dept or 'no department'}) as a new person.")
            else: errors.append(f"{where}: '{n}' is not on the People sheet.")
        return out

    # ---- stages
    stages, codes, start, final = [], [], [], []
    srow, sidx = _rows(ws_s, STAGE_COLS, "Stage Name")
    has_next = any(_names(rec.get("Next stages")) for _, rec in srow) or any(
        _names(rec.get("Waits for")) for _, rec in srow)
    taken = {s["code"] for s in current_flow["stages"]} if merge else set()
    counters = {}
    for r, rec in srow:
        name = _cell(rec.get("Stage Name"))
        if not name: continue
        dept = _cell(rec.get("Department"))
        code = _cell(rec.get("Stage Code")).upper()
        if not code or code.isdigit():
            pre = _code_prefix(dept); counters[pre] = counters.get(pre, 0) + 1
            code = f"{pre}-{int(code) if code.isdigit() else counters[pre]:02d}"
        where = f"Stages row {r} ({code})"
        if code in codes: errors.append(f"{where}: code {code} is used twice."); continue
        codes.append(code)
        owners = person(rec.get("Done by"), where + " Done by", dept)
        if not _names(rec.get("Done by")): errors.append(f"{where}: Done by is empty (who does '{name}'?).")
        checker = _names(rec.get("Checked by"))
        if len(checker) > 1: errors.append(f"{where}: Checked by needs one name, found {len(checker)}.")
        val = person(checker[0], where + " Checked by", dept) if checker else []
        if not checker:
            lead = next((u["name"] for u in users if u.get("lead") and u.get("dept") == dept and u["name"] not in owners), None)
            val = [lead or (owners[0] if owners else "")]
            warnings.append(f"{where}: no checker given, used {val[0] or 'nobody'}" + (" (the department lead)." if lead else " (the person doing it checks it)."))
        raw = _cell(rec.get("Time limit (hours)"))
        try:
            sla = float(raw) if raw else 8.0
            if sla <= 0: raise ValueError
            sla = int(sla) if sla.is_integer() else sla
            if not raw: warnings.append(f"{where}: no time limit given, used 8 hours.")
        except ValueError:
            errors.append(f"{where}: Time limit must be a number of hours above 0 (found '{raw}')."); sla = 1
        s = {"code": code, "name": name, "dept": dept, "owners": owners, "validator": val[0] if val else "", "sla_hours": sla,
             "next": [c.upper() for c in _names(rec.get("Next stages"))], "output": _cell(rec.get("Output expected")) or name}
        req = [c.upper() for c in _names(rec.get("Waits for"))]
        opt = [c.upper() for c in _names(rec.get("Also waits for (if it ran)"))]
        if req: s["requires"] = req
        if opt: s["optional_requires"] = opt
        cc = person(rec.get("Also alert"), where + " Also alert", dept)
        if cc: s["cc"] = cc
        acc = [a.strip().lower().lstrip("*.") for a in _names(str(rec.get("Accepted files") or "").replace("/", ","))
               if a.strip().lower() not in ("any", "all", "*")]
        if acc: s["accept"] = acc
        if _yes(rec.get("File required")): s["file_required"] = True
        qn = _cell(rec.get("Decision question"))
        if qn:
            s["branch"] = {"question": qn, "options": {"Yes": [c.upper() for c in _names(rec.get("If Yes also start"))],
                                                        "No": [c.upper() for c in _names(rec.get("If No also start"))]}}
        elif _names(rec.get("If Yes also start")) or _names(rec.get("If No also start")):
            errors.append(f"{where}: 'If Yes / If No also start' need a Decision question.")
        if not s["dept"]:
            s["dept"] = next((u["dept"] for u in users if owners and u["name"] == owners[0]), "")
        if _yes(rec.get("Start stage")): start.append(code)
        if _yes(rec.get("Final stage")): final.append(code)
        stages.append(s)
    if not stages: errors.append("Stages: no tasks found. Each row needs at least a task name and who does it.")
    if stages and not has_next:   # a plain list of tasks: run them one after another
        for a, b in zip(stages, stages[1:]): a["next"] = [b["code"]]
        if not merge: warnings.append("No 'Next stages' column: the tasks run one after another in the order of the rows.")
        else: warnings.append("No 'Next stages' column: this file's tasks run one after another in row order.")

    # ---- merge with the stages already in the app
    merged_info = None
    if merge:
        mine = {s["code"]: s for s in stages}
        kept = [mine.pop(s["code"]) if s["code"] in mine else s for s in current_flow["stages"]]
        added = [s for s in stages if s["code"] in mine]
        merged_info = {"updated": [s["code"] for s in stages if s["code"] not in mine], "added": [s["code"] for s in added]}
        stages = kept + added
        codes = [s["code"] for s in stages]
        if not start: start = [current_flow.get("start_stage")] if current_flow.get("start_stage") in codes else []
        if not final: final = [c for c in current_flow.get("final_stages", []) if c in codes]

    if users and not any(u.get("admin") for u in users):
        errors.append("People: mark at least one person as Admin = Yes (admins open bills and change the workflow).")
    cs = set(codes)
    for s in stages:
        refs = s["next"] + s.get("requires", []) + s.get("optional_requires", [])
        if s.get("branch"): refs += sum(s["branch"]["options"].values(), [])
        for c in refs:
            if c not in cs: errors.append(f"Stage {s['code']}: refers to {c}, which isn't a Stage Code.")
        if s["code"] in s["next"]: errors.append(f"Stage {s['code']}: can't be its own next stage.")
    if stages:
        if len(start) == 0:
            start = [stages[0]["code"]]; warnings.append(f"No row has Start stage = Yes, so {start[0]} (the first row) is used.")
        elif len(start) > 1: errors.append("Only one stage can have Start stage = Yes (found " + ", ".join(start) + ").")
        if not final:
            final = [s["code"] for s in stages if not s["next"] and not (s.get("branch") and any(s["branch"]["options"].values()))]
            final = final[-1:]
            warnings.append(f"No row has Final stage = Yes, so {', '.join(final) or 'none'} is used.")
        reach = {start[0]}; todo = [start[0]]; by = {s["code"]: s for s in stages}
        while todo:
            s = by.get(todo.pop())
            if not s: continue
            nx = s["next"] + (sum(s["branch"]["options"].values(), []) if s.get("branch") else [])
            for c in nx:
                if c in by and c not in reach: reach.add(c); todo.append(c)
        for s in stages:
            if s["code"] not in reach: warnings.append(f"Stage {s['code']} is never reached from {start[0]}; it will not run. Link it with 'Next stages'.")
        for s in stages:
            for c in s.get("requires", []):
                if c in by and s["code"] not in by[c]["next"] and not any(s["code"] in o for o in by[c].get("branch", {}).get("options", {}).values()):
                    warnings.append(f"Stage {s['code']} waits for {c}, but {c} doesn't list {s['code']} under Next stages, so nothing will start it from {c}.")

    # ---- bills
    bills = []
    ws_b = _sheet(wb, "Bills to open")
    if ws_b:
        try:
            brow, _ = _rows(ws_b, BILL_COLS, "Client")
            bills = [{"client": _cell(rec.get("Client")), "notes": _cell(rec.get("Notes"))} for _, rec in brow if _cell(rec.get("Client"))]
        except InputError as e:
            warnings.append(str(e))

    # ---- settings
    cur = (current_flow or {}).get("settings", {})
    settings = {k: v for k, v, _ in SETTINGS}
    if merge and cur:
        settings.update({"Time speed": cur.get("demo_speed", 60), "Overdue alert to checker": "Yes" if cur.get("overdue_to_checker", True) else "No",
                         "Bill complete alert to admins": "Yes" if cur.get("complete_to_admins", True) else "No"})
    ws_t = _sheet(wb, "Settings")
    if ws_t:
        try:
            trow, _ = _rows(ws_t, ["Setting", "Value"], "Setting")
            for r, rec in trow:
                k = _cell(rec.get("Setting"))
                if k in settings: settings[k] = rec.get("Value")
        except InputError as e:
            warnings.append(str(e))
    try:
        sp = float(_cell(settings["Time speed"]) or 1)
        settings["Time speed"] = max(1, int(sp))
    except ValueError:
        errors.append("Settings: Time speed must be a number (1 = real time)."); settings["Time speed"] = 1
    for k in ("Overdue alert to checker", "Bill complete alert to admins"):
        settings[k] = _yes(settings[k])

    flow = {"stages": stages, "start_stage": start[0] if start else "", "final_stages": final,
            "settings": {"demo_speed": settings["Time speed"], "overdue_to_checker": settings["Overdue alert to checker"],
                         "complete_to_admins": settings["Bill complete alert to admins"]}}
    return {"flow": flow, "users": users, "bills": bills, "errors": errors, "warnings": warnings, "merged": merged_info}


# ------------------------------------------------------------------ template writer
def build(flow, users, bills=None, demo_speed=60):
    openpyxl = _need_openpyxl()
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.comments import Comment
    F = "Calibri"
    INK, MUTED, BLUE = "1D1D1F", "6E6E73", "0071E3"
    head_fill = PatternFill("solid", fgColor="1D1D1F"); band = PatternFill("solid", fgColor="F5F5F7")
    thin = Side(style="thin", color="D2D2D7"); box = Border(bottom=thin)
    wb = openpyxl.Workbook()

    def title(ws, t, sub, width):
        ws["A1"] = t; ws["A1"].font = Font(name=F, size=18, bold=True, color=INK)
        ws["A2"] = sub; ws["A2"].font = Font(name=F, size=11, color=MUTED)
        ws.row_dimensions[1].height = 28; ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    def table(ws, cols, rows, widths, hdr=3):
        for i, c in enumerate(cols, 1):
            cell = ws.cell(hdr, i, c); cell.font = Font(name=F, bold=True, color="FFFFFF"); cell.fill = head_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if c in HINTS: cell.comment = Comment(HINTS[c], "SOMESH ENTERPRISES")
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = widths[i - 1]
        ws.row_dimensions[hdr].height = 34
        for r, row in enumerate(rows, hdr + 1):
            for i, v in enumerate(row, 1):
                cell = ws.cell(r, i, v); cell.font = Font(name=F, color=INK); cell.border = box
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if (r - hdr) % 2 == 0: cell.fill = band
        ws.freeze_panes = ws.cell(hdr + 1, 2)

    # How to fill
    ws = wb.active; ws.title = "How to fill"
    title(ws, "SOMESH ENTERPRISES · Workflow input", "This file decides the stages, who is alerted, who checks, and the time limits.", 100)
    lines = [
        ("1", "Stages sheet", "One row per step of the Monthly Cycle. Done by = everyone who gets the 'New task' alert. Checked by = the one person who gets 'Please check' and approves or sends back."),
        ("2", "Hand-offs", "Next stages = codes that start when this stage is approved. Waits for = codes that must all be approved first (e.g. S06 waits for S03, S04)."),
        ("3", "Decisions", "Decision question (e.g. New candidates?) is asked on Submit. If Yes also start = extra stage codes for a Yes answer."),
        ("4", "Alerts", "New task -> Done by + Also alert. Submitted -> Checked by. Approved / Sent back -> the person who did it. Overdue -> doer + checker + Also alert. Bill complete -> admins."),
        ("5", "People sheet", "Names must match exactly what you type in Done by / Checked by. Admin = Yes can open bills and load this file. Email turns on mail alerts if email is set up."),
        ("6", "Bills to open", "Optional. Each client listed gets a new bill when the file is loaded (once per client per month)."),
        ("7", "Settings", "Time speed 1 = real time. 60 = demo (1 hour = 1 minute)."),
        ("8", "Load it", "In the app: Workflow input -> paste the Google Sheet link or a file path (G:\\Shared drives\\...\\Workflow_Input.xlsx), or upload this file -> Check -> Apply."),
        ("9", "Google Sheets", "File -> Share -> General access: 'Anyone with the link' -> Viewer. Keep the sheet names and column headings as they are."),
    ]
    ws.column_dimensions["A"].width = 5; ws.column_dimensions["B"].width = 20; ws.column_dimensions["C"].width = 110
    for i, (n, h, t) in enumerate(lines, 4):
        ws.cell(i, 1, n).font = Font(name=F, bold=True, color=BLUE, size=13)
        ws.cell(i, 2, h).font = Font(name=F, bold=True, color=INK)
        c = ws.cell(i, 3, t); c.font = Font(name=F, color=INK); c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[i].height = 34

    # Stages
    ws = wb.create_sheet("Stages")
    title(ws, "Stages", "One row per stage. Hover a heading for help. Names come from the People sheet.", 0)
    rows = []
    for s in flow["stages"]:
        br = s.get("branch") or {}
        rows.append([s["code"], s["name"], s.get("dept", ""), ", ".join(s.get("owners", [])), s.get("validator", ""), s.get("sla_hours", 1),
                     ", ".join(s.get("next", [])), ", ".join(s.get("requires", [])), ", ".join(s.get("optional_requires", [])),
                     br.get("question", ""), ", ".join(br.get("options", {}).get("Yes", [])), ", ".join(br.get("options", {}).get("No", [])),
                     s.get("output", ""), ", ".join(s.get("cc", [])), ", ".join(s.get("accept", [])), "Yes" if s.get("file_required") else "",
                     "Yes" if s["code"] == flow.get("start_stage") else "",
                     "Yes" if s["code"] in flow.get("final_stages", []) else ""])
    table(ws, STAGE_COLS, rows, [8, 26, 22, 24, 15, 10, 14, 12, 14, 18, 12, 12, 30, 16, 14, 10, 9, 9])
    last = 3 + max(len(rows), 1) + 60
    yn = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True); ws.add_data_validation(yn)
    yn.add(f"P4:R{last}")
    who = DataValidation(type="list", formula1="=People!$A$4:$A$300", allow_blank=True,
                         error="Pick a name from the People sheet", showErrorMessage=True); ws.add_data_validation(who)
    who.add(f"E4:E{last}")
    hrs = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True,
                         error="Hours, above 0", showErrorMessage=True); ws.add_data_validation(hrs)
    hrs.add(f"F4:F{last}")

    # People
    ws = wb.create_sheet("People")
    title(ws, "People", "Everyone who uses the app. Admin = can open bills and load this file.", 0)
    table(ws, PEOPLE_COLS, [[u["name"], u.get("dept", ""), u.get("role", ""), u.get("email", ""),
                             "Yes" if u.get("admin") else "No", "Yes" if u.get("lead") else "No"] for u in users], [18, 28, 32, 30, 9, 9])
    yn2 = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True); ws.add_data_validation(yn2); yn2.add("E4:F300")

    # Bills to open
    ws = wb.create_sheet("Bills to open")
    title(ws, "Bills to open", "Optional. A bill is opened for each client when the file is loaded (once per client per month).", 0)
    table(ws, BILL_COLS, [[b["client"], b.get("notes", "")] for b in (bills or [])], [34, 50])

    # Settings
    ws = wb.create_sheet("Settings")
    title(ws, "Settings", "Change the Value column only.", 0)
    st = flow.get("settings", {})
    vals = {"Time speed": st.get("demo_speed", demo_speed),
            "Overdue alert to checker": "Yes" if st.get("overdue_to_checker", True) else "No",
            "Bill complete alert to admins": "Yes" if st.get("complete_to_admins", True) else "No"}
    table(ws, ["Setting", "Value", "What it means"], [[k, vals[k], m] for k, _, m in SETTINGS], [30, 10, 80])
    yn3 = DataValidation(type="list", formula1='"Yes,No"', allow_blank=False); ws.add_data_validation(yn3); yn3.add("B5:B6")

    wb.active = 1
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def sheet_export_url(location):
    """Google Sheet link -> direct .xlsx download URL. Other http(s) links are returned unchanged."""
    m = re.search(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)", location)
    if m: return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=)([A-Za-z0-9_-]+)", location)
    if m: return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return location
