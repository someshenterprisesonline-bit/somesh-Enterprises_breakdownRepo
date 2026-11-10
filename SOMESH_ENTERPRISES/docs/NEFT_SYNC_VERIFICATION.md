# NEFT synchronization verification — 2026-11-10

The existing application is plain JavaScript served by its Python HTTP service, with SQLite document/version storage. The implementation extends that architecture. It does not introduce React, FastAPI, another database, or temporary production storage.

## Implemented behavior

- Persisted ascending/descending sorting for numerical S.No, alphabetical Name and Designation, and Original Order. Header buttons cycle through the same options. Entire rows and their formatting move together in current downloads; canonical source/version bytes remain intact.
- One-way synchronization of S.No, Name → Name of the Employees, and Designation. Salary Amount → Net Salary only for recognized, editable numeric fields. Existing calculated salary cells remain formulas.
- Same-owner private document pairs, independent targets for separate NEFT sheets/documents, UUID row identities, idempotent updates, saved versions and optimistic revision checks.
- Automatic saves after a short pause, immediate linked Worksheet refresh, row addition/deletion, editable payroll fields, and safe rebasing of unsaved payroll drafts across sorting.
- Visible success/error status, explicit target selection, Open linked Worksheet and Retry sync. A manual override in a mapped target field stops that target update, retains the NEFT save and preserves the target/version history.
- Completed uploads retain existing formulas; adding rows to a completed upload does not introduce formulas. Unsupported formula rearrangements fail visibly rather than modifying the original.

## Executed checks

| Check | Result |
| --- | --- |
| Full backend/API unittest discovery, private reference templates enabled | PASS — 70 tests |
| New NEFT API tests | PASS — 9 tests, including a genuine backend restart |
| NEFT Chrome browser suite, light and dark modes | PASS |
| Manual paste of 10 employees and automatic Worksheet updates | PASS |
| 100-row completed Excel upload and separate counterpart | PASS |
| All six sort combinations and Original Order | PASS |
| Complete bank/account/salary/remarks row association | PASS |
| Saved and unsaved Worksheet payroll fields follow employee identity | PASS |
| Edit, undo after autosave, add/delete with confirmation | PASS |
| Refresh/reopen, persisted sorting, both browser Excel downloads | PASS |
| Manual mapped-cell conflict, visible error and Retry sync | PASS |
| Second employee upload and direct foreign-document HTTP 403 | PASS |
| Real Worksheet headers, formulas, images and summary merges | PASS |
| Real NEFT conditional formatting after add/delete; original version bytes | PASS |
| Existing Excel/Word Chrome suite with private reference files | PASS |
| All four employee browser journeys, downloads and access isolation | PASS |
| JavaScript syntax checks, Python compileall, git diff whitespace check | PASS |
| Existing BAT startup tests in paths containing spaces | PASS |
| BAT launch at localhost:8080 and live Admin/Employee read-only smoke test | PASS |
| Live existing NEFT document sorting/status controls | PASS |
| SQLite integrity and preservation of all pre-existing rows/version bytes | PASS |
| Frontend build/lint command | N/A — none configured; syntax and browser checks executed |

All destructive/editing browser and API scenarios used disposable synthetic databases. Live checks opened existing records without issuing save, sort or upload requests. A SQLite backup was created before the installed application restart. Database comparison checked all 14 pre-existing non-session tables for missing/changed original rows; none were missing. Additional records created during normal application use were retained.

## Fixes found while testing

- Excluded self-closing XML cells from the formula-cache patch matcher, preventing a cached formula result from being attached to the wrong cell.
- Adjusted references when sorting employee rows, including discontiguous aggregate ranges in the real Worksheet template.
- Preserved conditional formatting across recognized NEFT structural row changes.
- Kept unsaved payroll changes attached to UUIDs across sorting and correctly followed the linked document when changing NEFT documents/sheets.
- Updated old browser expectations: a Worksheet preview now legitimately receives the newly synchronized employees, and generated counterparts count as additional private documents.

Initial test-only failures (a Windows workbook file handle and assertions expecting a renamed, alphabetically sorted employee to remain in the first row) were corrected and the affected suites rerun successfully. Windows process-cleanup restrictions required the BAT tests to be rerun with permission; the final full suite passed.

## Evidence and operating notes

Screenshots are local under `data/neft-sync-audit/light/`, `dark/` and `live-controls.png`. The backend log is `data/neft-backend-tests-final.log`. Downloads and private templates remain excluded from Git. See README for commands and usage.

The BAT launcher is already correct: it runs current source and opens Chrome, with no compiled frontend directory. There is one combined frontend/API service at **http://localhost:8080**. Configure an editable shared Worksheet template with recognized headers. Resolve any mapped-cell conflict before retrying; unsupported workbook structures/formula rearrangements remain protected with an error. No Git commit/push was performed for this implementation request.
