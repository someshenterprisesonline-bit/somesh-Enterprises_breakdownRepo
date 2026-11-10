# Excel Workspace redesign and document behavior

**Access update:** All four employees now use the same three shared master references, independently of their owned documents. See [EMPLOYEE_TEMPLATE_FIX_REPORT.md](EMPLOYEE_TEMPLATE_FIX_REPORT.md) for the current access model, loading/profile-switch fixes, migration preservation checks and all-employee tests. This supersedes the earlier partial assignment description below.

Updated 7 November 2026. The existing application is running at **http://localhost:8080**. This report supersedes the initial Excel Workspace implementation report.

## Result

The existing plain JavaScript frontend and Python HTTP backend were extended in place. No React conversion, replacement database, new login system or separate frontend server was introduced. Existing employee accounts, workbook versions, tasks, timers, alerts and admin functions remain available. No commit or push was made.

Three independent compact sections now appear:

| Heading | Reference | Format |
| --- | --- | --- |
| NEFT SHEET | 538-OMCL-Open University -Sept-26(03-10-2026).xlsx | Excel |
| WORKSHEET | Oct-26-OMCL - TNOU.xlsx, including the `(1)` filename variant | Excel |
| COVERING LETTER | 538-September-26-TN-Open University.docx | Word |

The original filename appears as secondary text. A saved-file selector separates previously populated/uploaded workbooks from blank templates and current work. The default hover preview is empty and never automatically opens historical employee records. Viewing a preview does not create or modify a workbook version.

## Interaction

- Hovering a section opens its preview. Hovering spreadsheet headers increases the viewing height. Both use 250 ms CSS transitions, respecting reduced-motion preferences.
- Pointer movement into the table keeps it open. Clicking a heading or focusing an editable field pins that section open. Each section has its own draft, timers and pin state.
- Close / Collapse is explicit. Collapsing preserves the draft; keyboard focus cannot enter collapsed editors. Click, keyboard and touch opening are supported.
- Excel tools include direct editing, insertion/deletion of ordinary data rows, copy/paste, Shift-click range copying, undo/redo, search/filter/sort, sticky headers, column resizing, 50-row pagination, save/reset, full-screen expansion and new-tab editing.
- Existing task dashboards and navigation are retained. Unsaved drafts survive internal page changes; browser close/reload warns about unsaved work.
- Download Excel and Download Word open filename dialogs. Empty names are rejected, invalid characters are sanitized on both client and server, the appropriate extension is enforced, and reserved names are handled. Unsaved drafts offer Save and download or Download saved version. Cancel downloads nothing.

## Blank templates

New Blank Template is a separate backend operation. It derives structure and formulas from an authorized reference ancestor, never from a historical file as default data.

Excel creation retains all original worksheets, exact header matrices and order, merged ranges, styles, number formats, formulas and required summary labels. Historical manual records are cleared: names, salaries, account numbers, attendance, invoice amounts and historical dates are not copied into editable rows. Identifier columns such as account numbers and IFSC codes are handled as text. Protected headers are retained exactly, including spelling, whitespace and line breaks.

The supplied Excel references retain these original sheets:

- September: `Office Copy`, `Net Banking Copy`, `TNOU`, `In`.
- October: `TNOU`, `In`.

`EXCEL_TEMPLATE_STRUCTURE.json` (local generated metadata, excluded from Git) records the exact original headers, merged ranges, formula locations, number formats and dimensions. Original reference files in Downloads were never written to.

Adding payroll records copies formulas already present in the preceding record, translates references, retains cell formats and extends the supplied summary ranges. The original `Over All total Amount` label is retained. Explicitly deleting an ordinary data row adjusts references; direct references to deleted cells become `#REF!` and display as pending. Header/merged summary rows remain protected. Direct editing of formula cells remains protected for employees.

## Calculations and completed uploads

Formula expressions are not displayed in normal spreadsheet cells. The evaluator interprets the actual stored Excel formulas; it does not contain payroll rates or substitute invented calculations. The supplied arithmetic, percentages, references and `SUM` formulas are supported, along with bounded `ROUND`, `MIN` and `MAX` support.

Missing required inputs produce blank results. Unsupported functions, invalid arithmetic, cycles or expressions beyond safe limits show **Recalculation pending**. Number formats determine displayed calculated results. Unsaved edits use a debounced calculation endpoint; saving writes supported results into OOXML formula caches without replacing `<f>` expressions. Downloads retain genuine Excel formulas and request recalculation when opened in Excel.

Upload Completed File always creates an independent saved file. Initial import retains the entire original XLSX/DOCX byte-for-byte. Import and viewing do not recalculate or rewrite the uploaded workbook. Existing cached formula values are displayed when available. A completed XLSX with no formulas receives no formulas. After an explicit manual edit, only the dependency closure of formulas already in that workbook is recalculated; unrelated cached results are retained. Structural row actions are also explicit.

## Covering letter

The actual supplied Word document is the third reference. The editor supports blank creation, expandable preview, paragraph editing, undo/redo, save/reset, custom `.docx` download and new-tab editing.

Blank creation substitutes editable placeholders for the historical invoice number, amount, amount in words, month, dates and reference number. Static company information, address, standard wording, headings and signature structure remain. The source letterhead image is included in the browser preview.

Saving patches text inside the original paragraph/run XML rather than rebuilding a Word document. Existing alignment, run formatting, tables, page setup, image relationships, embedded letterhead and other untouched ZIP parts are retained. The supplied reference has no tables; an additional synthetic table document is tested to verify preservation.

## Storage, permissions and APIs

The existing SQLite `ew_books`, `ew_versions`, `ew_pending` and `ew_slots` tables remain. Additive columns record document format, category, origin and non-sensitive blank-cell type metadata. A database backup was taken before installing the covering-letter reference: `data/before-excel-workspace-20261107-120540.sqlite3`.

Existing populated files and all versions remain accessible. Slot 3 now contains the actual supplied Word reference; it is not an invented third Excel workbook. Rupashri received an independent blank covering letter. Existing Payroll/Finance spreadsheet assignments were retained. No payroll documents were automatically shared with Sudharsan; his existing private-upload access and admin-controlled assignments remain.

The backend uses existing sessions and performs owner/view/edit/download/lock checks. Blank creation requires an authorized editable reference. Save, calculate, import-into-existing, permissions and restore operations validate revisions where applicable. Concurrent stale saves fail without overwriting a newer version. Workbook and document downloads use `Cache-Control: no-store`.

New or extended operations:

| API | Behavior |
| --- | --- |
| GET `/api/excel` | Authorized files and assigned reference catalog |
| GET `/api/excel/metadata`, `/sheet` with `template=1` | Read-only blank previews, with no saved version created |
| POST `/api/excel/blank` | Independent blank XLSX or DOCX |
| POST `/api/excel/preview`, `/import` | Validated XLSX/DOCX previews and independent completed-file imports |
| POST `/api/excel/calculate` | Permission/revision-checked in-memory draft calculations; no save |
| GET `/api/excel/document` | Authorized formatted Word preview |
| POST `/api/excel/save` | Existing cell/row edits or Word paragraph edits, with immutable versions |
| GET `/api/excel/download?filename=...` | Sanitized custom filename and correct Excel/Word MIME type |
| POST `/api/excel/assign`, `/permissions`, `/restore` | Retained admin management; blank assignment supported |

Upload size/archive/XML limits remain enforced. Macro-enabled documents, embedded executable objects, unsafe XML and external workbook/document relationships are rejected. Legacy `.xls` requires conversion to `.xlsx`.

## Files changed

New files for this redesign:

- `backend/excel_calculation.py`: bounded evaluator, dependency closure and formula-cache writing.
- `backend/word_workspace.py`: original-package DOCX editing, blanking and formatted preview.
- `tests/test_document_workspace.py`: blanking, import/cache isolation, real formulas, row behavior, Word preservation and filenames.

Updated files:

- `backend/excel_workspace.py`: additive metadata, empty previews, blank creation, calculations, DOCX operations and independent imports.
- `backend/app.py`: Excel/Word download MIME types and private caching behavior.
- `frontend/js/pages/excel-workspace.js`: independent section editors, hover/pin/touch behavior, hidden formulas, Word editor and filename dialogs.
- `frontend/css/excel-workspace.css`: compact responsive layout, transitions, full-screen tables and document preview.
- `frontend/js/pages/new-bill-demo.js`: fixed an observed regression-test race where refresh could erase the successful bill-opening message; the message is now retained in user-scoped state.
- `tests/excel-workspace.cjs`: revised end-to-end suite for all three sections and four employees.
- `tests/test_excel_workspace.py`: retained regression coverage with header-protection checks reflecting explicit row deletion.
- `tests/run_browser.py`: isolated three-document fixtures, large imports and reopening actual browser downloads. Download validation reads in-memory bytes so Windows cleanup does not retain file handles.
- `tools/setup_excel_workspace.py`: idempotent installation of the actual Word reference without replacing existing spreadsheet assignments.
- `tools/verify_excel_live.cjs`: live Rupashri verification, preservation checks and optional visible Chrome session.
- `docs/EXCEL_WORKSPACE_REPORT.md`: this report.

Earlier unrelated uncommitted changes were preserved.

## Executed tests

Environment used on this machine:

```powershell
$env:EXCEL_REFERENCE_ROOT = 'C:\path\to\reference-files'
$env:PLAYWRIGHT_MODULE_PATH = 'C:\path\to\test-tools\node_modules\playwright'
```

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 44 passed, including private real references |
| `python tests/run_browser.py --excel` | Passed; real template headers/formulas, all four employees, hover/pin, blank creation, calculations, text accounts, undo/redo, new tabs, custom Excel/Word filenames, Word editing, reload, large upload/pagination/search, resizing/full-screen and mobile admin assignment |
| Reopen the actual browser-downloaded XLSX and DOCX | Passed: worksheet/header order, original formulas, cached payroll result and saved letter text |
| `python tests/run_browser.py` | Passed: existing login/session/admin-role, task/timer, Tracker, alerts, Dashboard, Pipeline, Activity, automation, New bill and mobile checks |
| `python tests/run_browser.py --action-center` | Passed: existing Action Center, review/return/approve, reassignment, SSE, exports, mobile and permission checks |
| `node tools/verify_excel_live.cjs` | Passed against localhost as Rupashri, using all three real references; blank previews, editing/reset, letterhead, custom downloads and preservation of every pre-existing revision |
| Console/API monitoring | No browser JavaScript exceptions or failed Excel API requests in the final workspace suite; none in the final live Rupashri check |
| Python compilation, JavaScript syntax checks | Passed |
| HTTP `http://localhost:8080` | 200 |

Real arithmetic verification includes `30000 / 30 * 23 * 13% = 2990` using the formula present in the October source, not an application-defined payroll rate. Real-reference round trips also compare every unchanged cell/type/number format, header, formula, merge and worksheet.

Initial failures were fixed or corrected and affected checks rerun: a Word `contenteditable` value rendered as `1`, clipped/early hover test timing, popup initialization timing, offscreen resizing coordinates, a real source summary label differing from a generic label, Windows test-download file handles, and the existing New bill confirmation race. A test formula-copy expectation was corrected to retain the actual source's literal basis and reference pattern rather than assuming a different payroll formula. The expected malformed-rule log in the error-isolation test is not a failed test.

## Production startup and limits

This application has no production build step or npm/React build configuration. Python directly serves its HTML/CSS/JavaScript. Production readiness was checked with Python compilation, JavaScript syntax validation, regression/browser tests, the actual server startup command `python backend/app.py`, and a verified HTTP 200 on port 8080. No dependencies needed installation.

The live server serves both frontend and backend at **http://localhost:8080**. Google Chrome is supported, and the live verification signs in as Rupashri and opens her Excel Workspace. `node tools/verify_excel_live.cjs --show` leaves that verified Chrome window open. Live checks create/reuse independent empty documents and reset temporary edits; existing saved-file revisions are checked for preservation.

Limits:

- This is a bounded Excel evaluator, not the entire Excel calculation engine. Unsupported formulas display pending and remain intact in exported files.
- Header/merged summary cells remain protected. Structural edits involving tables, drawings, conditional formatting or array/structured/3-D formulas require Excel.
- Word preview approximates pagination and advanced Word layout. Original DOCX formatting/package parts are preserved on export; nested text-box structures requiring unsupported paragraph mapping are rejected rather than rewritten.
- Long identifiers remain text. Numeric Excel cells use Excel's 15-significant-digit limit.
- Existing trusted-office profile authentication remains the application's access model.

Runtime backups, verification downloads and `data/excel-workspace-redesign.png` are ignored by Git. Original reference files were not modified, and no changes were pushed.
