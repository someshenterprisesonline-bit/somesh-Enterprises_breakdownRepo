"""Data Center storage for SOMESH ENTERPRISES.

    <storage root>/
      00 Handoff/<BILL-ID> <Client>/          work files each team submits (the 'Where is the file?' path)
      01 Master Tracker/<YYYY>/Master_Tracker_<YYYY-MM>.xlsx   rewritten by the app on every change
      02 Contract Register/Contract_Register.xlsx               kept by Data Center; the app reads it
      02 Contract Register/Contracts/<Client>/<Contract No>.pdf
      03 Vault/<YYYY>/<MM Month>/<BILL-ID> <Client>/           final copies, filed when the last stage is approved
      03 Vault/Vault_Index.xlsx                                 one row per filed bill

The root is set in config.json -> storage.root (default: the 'storage' folder next to app.py). It can be a
shared-drive path such as G:\\Shared drives\\Data Center\\SOMESH Storage.
"""
import csv, os, re, shutil, zlib
from datetime import datetime

HANDOFF, TRACKER, REGISTER, VAULT = "00 Handoff", "01 Master Tracker", "02 Contract Register", "03 Vault"
REG_FILE = "Contract_Register.xlsx"
REG_COLS = ["Contract No", "Client", "Service", "Start date", "End date", "Headcount", "Monthly value (Rs)",
            "Billing day", "GST No", "Client contact", "Contract file", "Notes"]
INDEX_COLS = ["Bill ID", "Client", "Contract No", "Bill month", "Filed on", "Stored by", "Checked by", "Vault folder", "Files"]
README = {
    HANDOFF: "Work in progress. Each team saves its output for a bill in '<BILL-ID> <Client>' and pastes the path when it submits.",
    TRACKER: "Master Tracker, one workbook per month. The app rewrites it on every start, submit and approval. Do not edit by hand; "
             "open it read-only or connect Power BI / Looker Studio to it.",
    REGISTER: "Contract Register. Data Center keeps Contract_Register.xlsx up to date (one row per client contract) and saves the signed "
              "contract in Contracts/<Client>/. The app looks up the contract for every new bill.",
    VAULT: "Vault. When the final stage of a bill is approved, the app files a copy of every stage output, the contract and a "
           "Bill_Summary.xlsx in <Year>/<MM Month>/<BILL-ID> <Client>/ and adds a row to Vault_Index.xlsx. Read-only for everyone except "
           "the Vault custodian.",
}


def safe(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(name)).strip(" .")[:80] or "file"


def ensure(root):
    for sub in (HANDOFF, TRACKER, os.path.join(REGISTER, "Contracts"), VAULT):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    for sub, text in README.items():
        p = os.path.join(root, sub, "_READ ME.txt")
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f: f.write(text + "\n")


# ------------------------------------------------------------------ tiny PDF writer (no extra packages)
def pdf(path, title, lines, subtitle="SOMESH ENTERPRISES"):
    def esc(s): return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")
    ops = ["0.11 0.11 0.12 rg", "BT /F2 10 Tf 50 800 Td (" + esc(subtitle) + ") Tj ET",
           "BT /F2 18 Tf 50 770 Td (" + esc(title) + ") Tj ET", "0.8 0.8 0.82 RG 50 758 m 545 758 l S"]
    y = 735
    for ln in lines:
        bold = ln.startswith("**"); ln = ln.strip("*")
        if y < 60: break
        ops.append(f"BT /{'F2' if bold else 'F1'} 11 Tf 50 {y} Td ({esc(ln)}) Tj ET"); y -= 18 if ln else 10
    ops.append("BT /F1 8 Tf 50 30 Td (Sample document generated for the demo - not a real record) Tj ET")
    stream = zlib.compress("\n".join(ops).encode("latin-1"))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n"); offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f: f.write(out)


# ------------------------------------------------------------------ workbook helpers
def _wb_table(ws, cols, rows, widths=None):
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1D1D1F")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows: ws.append(list(r))
    ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(c, max(10, min(40, len(c) + 4)))


def _save(wb, path):
    """Save via a temp file. If the file is open in Excel (locked) keep the old copy and report it."""
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    try:
        os.replace(tmp, path); return True
    except PermissionError:
        os.remove(tmp); return False


# ------------------------------------------------------------------ contract register
def load_register(root):
    path = os.path.join(root, REGISTER, REG_FILE)
    if not os.path.exists(path): return []
    import openpyxl
    try: wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception: return []
    ws = wb.worksheets[0]; rows = list(ws.iter_rows(values_only=True)); wb.close()
    if not rows: return []
    head = [str(h or "").strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        d = {h: r[i] for i, h in enumerate(head) if h and i < len(r)}
        if d.get("Client"): out.append(d)
    return out


def contract_for(root, client):
    """Returns (contract dict or None, status text: 'Active' / 'Expired' / 'No contract on file')."""
    today = datetime.now().date()
    best = None
    for c in load_register(root):
        if str(c.get("Client", "")).strip().lower() == client.strip().lower():
            best = c
            end = c.get("End date")
            end = end.date() if isinstance(end, datetime) else end
            if not end or end >= today: return c, "Active"
    return (best, "Expired") if best else (None, "No contract on file")


def write_register_template(root):
    import openpyxl
    path = os.path.join(root, REGISTER, REG_FILE)
    if os.path.exists(path): return
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Contracts"
    _wb_table(ws, REG_COLS, [], {"Client": 28, "Service": 26, "Contract file": 44, "Notes": 30})
    _save(wb, path)


SAMPLE_CONTRACTS = [
    ("SE-C-2025-014", "ABC Industries", "Housekeeping & security", "2025-04-01", "2027-03-31", 48, 1185000, 25, "33AABCA1234F1Z5", "R. Kumar, Admin Manager"),
    ("SE-C-2025-021", "XYZ Hospital", "Facility management", "2025-07-01", "2026-06-30", 46, 1092000, 28, "33AAACX5678K1Z2", "Dr. S. Meena, Hospital Admin"),
    ("SE-C-2026-003", "PQR Logistics", "Loading & warehouse staff", "2026-01-01", "2027-12-31", 62, 1470000, 30, "33AAFCP9012L1Z8", "V. Prakash, Ops Head"),
    ("SE-C-2026-009", "Sri Lakshmi Textiles", "Production support", "2026-04-01", "2028-03-31", 35, 812000, 25, "33AAGCS3456M1Z1", "K. Lakshmi, HR"),
    ("SE-C-2024-030", "Metro Facility Services", "Sub-contract manpower", "2024-10-01", "2027-09-30", 28, 655000, 26, "33AAHCM7890N1Z4", "J. Arun, Contracts"),
]


def write_sample_register(root):
    import openpyxl
    rows = []
    for no, client, svc, s, e, hc, val, day, gst, who in SAMPLE_CONTRACTS:
        folder = os.path.join(root, REGISTER, "Contracts", safe(client)); os.makedirs(folder, exist_ok=True)
        fp = os.path.join(folder, f"{no}.pdf")
        pdf(fp, f"Service Agreement {no}", [
            f"**Client: {client}", f"Service: {svc}", f"Period: {s} to {e}", f"Deployed headcount: {hc}",
            f"Monthly contract value: Rs {val:,}", f"Bill to be raised by day {day} of each month", f"Client GST No: {gst}",
            f"Client contact: {who}", "", "**Key terms",
            "1. Attendance is shared by the client by the 1st working day of the month.",
            "2. Statutory compliance (EPF, ESI, wages) is the contractor's responsibility.",
            "3. Payment within 30 days of invoice with acknowledgement copy.", "",
            "Signed for SOMESH ENTERPRISES: M. Sampath, CEO", f"Signed for {client}: {who}"])
        rows.append([no, client, svc, datetime.strptime(s, "%Y-%m-%d"), datetime.strptime(e, "%Y-%m-%d"), hc, val, day, gst, who,
                     os.path.relpath(fp, root), "Expired - renewal pending" if e < datetime.now().strftime("%Y-%m-%d") else ""])
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Contracts"
    _wb_table(ws, REG_COLS, rows, {"Client": 28, "Service": 26, "Contract file": 44, "Notes": 30, "GST No": 20, "Client contact": 28})
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 4).number_format = ws.cell(r, 5).number_format = "dd-mmm-yyyy"; ws.cell(r, 7).number_format = "#,##0"
    _save(wb, os.path.join(root, REGISTER, REG_FILE))


# ------------------------------------------------------------------ sample stage outputs (demo)
STAFF = ["Arun K", "Bhavani S", "Chitra M", "Dinesh R", "Eswari P", "Farook A", "Gopi N", "Hema V", "Ilango T", "Jaya L"]


KIND_WORDS = [("attendance check", "S04"), ("worksheet", "S03"), ("salary register", "S03"), ("wage", "S03"), ("attendance", "S01"),
              ("leave", "S04"), ("tally", "S05"), ("ledger", "S05"), ("approval", "S09"), ("summary", "S09"), ("follow up", "PDF"),
              ("challan", "S13"), ("return", "S14"), ("filing", "S14"), ("compliance", "S14"), ("uan", "S04A"), ("staff", "S04A"),
              ("onboard", "S04A"), ("neft", "S06"), ("bank", "S06"), ("epf", "S07"), ("esi", "S07"), ("payslip", "PDF"), ("payment", "S13"),
              ("scan", "S15"), ("invoice", "S08"), ("bill set", "S08"), ("acknowledg", "S11"), ("vault", "S16"), ("dispatch", "S10"),
              ("deliver", "S10"), ("submit at client", "S10"), ("tracker", "S02"), ("contract", "S02")]


def sample_kind(code, name):
    """Which kind of sample file to make, judged from the stage name (any workflow); the code is the fallback."""
    n = name.lower()
    return next((k for w, k in KIND_WORDS if w in n), code)


def sample_output(root, bill, client, code, stage):
    """Create a plausible sample file for a stage in 00 Handoff and return its path."""
    import openpyxl
    folder = os.path.join(root, HANDOFF, f"{bill} {safe(client)}"); os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"{code} {safe(stage['name'])}")
    month = datetime.now().strftime("%B %Y")
    code = sample_kind(code, stage.get("name", ""))
    if code in ("S01", "S03", "S04"):
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Sheet1"
        if code == "S03":
            _wb_table(ws, ["Employee", "Days", "Rate/day", "Gross", "EPF 12%", "ESI 0.75%", "Net pay"],
                      [[n, 26 - i % 3, 650, (26 - i % 3) * 650, round((26 - i % 3) * 650 * .12), round((26 - i % 3) * 650 * .0075),
                        (26 - i % 3) * 650 - round((26 - i % 3) * 650 * .12) - round((26 - i % 3) * 650 * .0075)] for i, n in enumerate(STAFF)])
        else:
            _wb_table(ws, ["Employee", "Site", "Present days", "Leave", "OT hours", "Checked"],
                      [[n, client, 26 - i % 3, i % 3, (i * 2) % 7, "Yes" if code == "S04" else ""] for i, n in enumerate(STAFF)])
        p = base + ".xlsx"; wb.save(p); return p
    if code in ("S05", "S06", "S13", "S15"):
        p = base + ".csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if code == "S06":
                w.writerow(["Beneficiary", "Account No", "IFSC", "Amount", "Narration"])
                for i, n in enumerate(STAFF): w.writerow([n, f"XXXXXX{4100 + i}", "SBIN0000XXX", 14200 + i * 150, f"Salary {month}"])
            elif code == "S05":
                w.writerow(["Voucher", "Ledger", "Debit", "Credit"]); w.writerow(["Sales", client, 0, 1185000]); w.writerow(["Sales", "Output GST 18%", 0, 213300])
            elif code == "S13":
                w.writerow(["Payment", "UTR", "Amount", "Date"]); w.writerow(["Salary NEFT", "SBIN2611XXXX0042", 151500, datetime.now().strftime("%d-%m-%Y")])
                w.writerow(["EPF", "EPF2611XXXX17", 18180, datetime.now().strftime("%d-%m-%Y")])
            else:
                w.writerow(["Document", "Scanned file", "Pages", "Logged by"])
                for d in ("Invoice", "Acknowledgement copy", "EPF challan", "ESI challan"): w.writerow([d, f"{bill}_{safe(d)}.pdf", 1, "Deeraj"])
        return p
    if code == "S07":
        p = base + ".txt"
        with open(p, "w", encoding="utf-8") as f:
            f.write("#~#".join(["UAN", "NAME", "GROSS", "EPF WAGES", "EPS WAGES", "EDLI WAGES", "EE SHARE", "EPS", "ER SHARE", "NCP DAYS", "REFUND"]) + "\n")
            for i, n in enumerate(STAFF): f.write("#~#".join([f"10{i:010d}", n.upper(), "16900", "15000", "15000", "15000", "1800", "1250", "550", str(i % 3), "0"]) + "\n")
        return p
    lines = {
        "S02": [f"Bill {bill} entered in the Master Tracker.", f"Client: {client}", f"Month: {month}"],
        "S04A": ["New joiners this month:", "1. Kavya R - Housekeeping - joined 03 Nov", "2. Mani S - Security - joined 05 Nov", "Joining forms and ID proofs attached."],
        "S08": [f"**TAX INVOICE  {bill}", f"Bill to: {client}", f"Service month: {month}", "Manpower charges           Rs 11,85,000",
                "GST 18%                    Rs  2,13,300", "**Total                    Rs 13,98,300", "", "Enclosures: attendance, wage sheet, EPF/ESI proof"],
        "S09": [f"Payment approved for {bill} ({client}).", "Approved by M. Sampath, CEO.", f"Date: {datetime.now():%d %b %Y}"],
        "S10": [f"Bill set {bill} delivered to {client}.", "Delivered by Munro.", "Received at front office."],
        "S11": [f"**ACKNOWLEDGEMENT - {client}", f"Received bill {bill} for {month}.", "Signature and seal: (client)", f"Date: {datetime.now():%d %b %Y}"],
        "S14": [f"Statutory filing for {month}", "EPF ECR uploaded - TRRN 2611XXXX0091", "ESI contribution paid - challan 2611XXXX33", "Filed by Thavamani"],
        "S16": [f"Vault entry for {bill}", "Original bill set and acknowledgement placed in the vault cabinet.", "Custodian: Harish"],
    }.get(code, [f"{stage['name']} for {bill} ({client})."])
    p = base + ".pdf"; pdf(p, f"{code} {stage['name']}", lines); return p


# ------------------------------------------------------------------ master tracker
STATUS = {"assigned": "To start", "in_progress": "In progress", "submitted": "With checker", "approved": "Approved"}
FILL = {"assigned": "E8F1FD", "in_progress": "FFF1E0", "submitted": "F4EAFA", "approved": "E4F6E9", "late": "FFE9EB"}


def write_master_tracker(root, bills, tasks, events, stages, order, now_ts):
    """One workbook per bill month. Returns list of (path, saved_ok)."""
    import openpyxl
    from openpyxl.styles import PatternFill
    by_month = {}
    for b in bills: by_month.setdefault(b["created_at"][:7], []).append(b)
    results = []
    for month, mb in sorted(by_month.items()):
        ids = {b["id"] for b in mb}
        mt = [t for t in tasks if t["bill_id"] in ids]
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Bills"
        cols = ["Bill ID", "Client", "Contract No", "Contract status", "Opened", "Bill status", "Now at", "Overdue"] + order + ["Vault folder"]
        rows, colour = [], []
        for b in sorted(mb, key=lambda b: b["id"]):
            bt = {t["stage"]: t for t in mt if t["bill_id"] == b["id"] and t["status"] != "cancelled"}
            open_ = [t for t in bt.values() if t["status"] in ("assigned", "in_progress", "submitted")]
            late = [t for t in open_ if t["status"] != "submitted" and t["due_at"] < now_ts]
            row = [b["id"], b["client"], b.get("contract_no") or "", b.get("contract_status") or "", b["created_at"],
                   "Complete" if b["status"] == "complete" else "Open", ", ".join(sorted(t["stage"] for t in open_)), "Yes" if late else ""]
            cs = []
            for c in order:
                t = bt.get(c)
                row.append(STATUS.get(t["status"], t["status"]) if t else "")
                cs.append(("late" if t in late else t["status"]) if t else None)
            row.append(b.get("vault_folder") or ""); rows.append(row); colour.append(cs)
        _wb_table(ws, cols, rows, {"Client": 26, "Vault folder": 50, "Contract status": 18})
        for r, cs in enumerate(colour, 2):
            for i, st in enumerate(cs):
                if st in FILL: ws.cell(r, 9 + i).fill = PatternFill("solid", fgColor=FILL[st])
        ws2 = wb.create_sheet("Stage log")
        _wb_table(ws2, ["Bill ID", "Stage", "Stage name", "Department", "Done by", "Checked by", "Status", "Assigned", "Started",
                        "Submitted", "Decided", "Due", "Late", "Reworks", "Output", "File"],
                  [[t["bill_id"], t["stage"], stages.get(t["stage"], {}).get("name", ""), stages.get(t["stage"], {}).get("dept", ""),
                    t["assignee"] or "", t["validator"], STATUS.get(t["status"], t["status"]), t["created_at"], t["claimed_at"] or "",
                    t["submitted_at"] or "", t["decided_at"] or "", t["due_at"],
                    "Yes" if (t["decided_at"] or now_ts) > t["due_at"] and t["status"] != "submitted" else "", t["rework_count"],
                    t["output_note"] or "", t["output_link"] or ""] for t in sorted(mt, key=lambda t: t["id"])],
                  {"Stage name": 24, "Output": 34, "File": 60, "Department": 22})
        ws3 = wb.create_sheet("Activity")
        _wb_table(ws3, ["Time", "Bill ID", "Who", "What"],
                  [[e["ts"], e["bill_id"] or "", e["actor"], e["text"]] for e in events if (e["bill_id"] in ids)], {"What": 90, "Time": 20})
        folder = os.path.join(root, TRACKER, month[:4]); os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"Master_Tracker_{month}.xlsx")
        results.append((path, _save(wb, path)))
    return results


# ------------------------------------------------------------------ vault
def archive_bill(root, bill, tasks, stages, contract):
    """Copy every stage output that exists on this PC + the contract into the vault folder; write Bill_Summary.xlsx."""
    import openpyxl
    created = datetime.strptime(bill["created_at"][:10], "%Y-%m-%d")
    folder = os.path.join(root, VAULT, created.strftime("%Y"), created.strftime("%m %B"), f"{bill['id']} {safe(bill['client'])}")
    os.makedirs(folder, exist_ok=True)
    copied, missing = [], []
    for t in sorted(tasks, key=lambda t: t["id"]):
        if t["status"] != "approved": continue
        src = (t["output_link"] or "").strip().strip('"')
        name = f"{t['stage']} {safe(stages.get(t['stage'], {}).get('name', ''))}"
        if src and os.path.isfile(src):
            dst = os.path.join(folder, name + os.path.splitext(src)[1]); shutil.copy2(src, dst); copied.append(os.path.basename(dst))
        elif src and os.path.isdir(src):
            dst = os.path.join(folder, name); shutil.copytree(src, dst, dirs_exist_ok=True); copied.append(name + "\\")
        elif src:
            missing.append(f"{t['stage']}: {src}")
    if contract and contract.get("Contract file"):
        cf = contract["Contract file"]; cf = cf if os.path.isabs(cf) else os.path.join(root, cf)
        if os.path.isfile(cf):
            shutil.copy2(cf, os.path.join(folder, "Contract " + os.path.basename(cf))); copied.append("Contract " + os.path.basename(cf))
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Summary"
    _wb_table(ws, ["Stage", "Stage name", "Done by", "Checked by", "Submitted", "Approved", "Output", "Original file"],
              [[t["stage"], stages.get(t["stage"], {}).get("name", ""), t["assignee"] or "", t["validator"], t["submitted_at"] or "",
                t["decided_at"] or "", t["output_note"] or "", t["output_link"] or ""] for t in sorted(tasks, key=lambda t: t["id"]) if t["status"] == "approved"],
              {"Stage name": 24, "Output": 34, "Original file": 60})
    info = wb.create_sheet("Bill")
    for k, v in [("Bill ID", bill["id"]), ("Client", bill["client"]), ("Contract No", (contract or {}).get("Contract No", "")),
                 ("Opened", bill["created_at"]), ("Filed in vault", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                 ("Stage files and contract copied", len(copied)), ("Files not reachable from this PC", "; ".join(missing))]:
        info.append([k, v])
    info.column_dimensions["A"].width = 30; info.column_dimensions["B"].width = 70
    _save(wb, os.path.join(folder, "Bill_Summary.xlsx")); copied.append("Bill_Summary.xlsx")
    final = next((t for t in tasks if t["stage"] == sorted(tasks, key=lambda t: t["id"])[-1]["stage"]), None)
    _index_add(root, [bill["id"], bill["client"], (contract or {}).get("Contract No", ""), bill["created_at"][:7],
                      datetime.now().strftime("%Y-%m-%d %H:%M"), (final or {}).get("assignee") or "", (final or {}).get("validator") or "",
                      os.path.relpath(folder, root), len(copied)])
    return folder, copied, missing


def _index_add(root, row):
    import openpyxl
    path = os.path.join(root, VAULT, "Vault_Index.xlsx")
    rows = []
    if os.path.exists(path):
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            rows = [list(r) for r in list(wb.worksheets[0].iter_rows(values_only=True))[1:] if r and r[0] and r[0] != row[0]]
            wb.close()
        except Exception: rows = []
    rows.append(row)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Vault Index"
    _wb_table(ws, INDEX_COLS, rows, {"Client": 26, "Vault folder": 56})
    _save(wb, path)


# ------------------------------------------------------------------ browsing
def tree(root, max_entries=400):
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if not d.startswith("."))
        rel = os.path.relpath(dp, root); depth = 0 if rel == "." else rel.count(os.sep) + 1
        if rel != ".": out.append({"path": rel.replace(os.sep, "/"), "name": os.path.basename(dp), "dir": True, "depth": depth - 1})
        for fn in sorted(fns):
            if fn.endswith(".tmp.xlsx") or fn.startswith("~$"): continue
            fp = os.path.join(dp, fn); st = os.stat(fp)
            out.append({"path": os.path.relpath(fp, root).replace(os.sep, "/"), "name": fn, "dir": False, "depth": depth,
                        "size": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
        if len(out) > max_entries: break
    return out[:max_entries]
