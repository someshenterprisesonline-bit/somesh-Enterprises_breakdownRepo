# Shared template availability for all four employees

The existing application remains at **http://localhost:8080**. No rebuild, commit or push was performed.

## Root cause

All three master references already existed. Employee identity was not the problem: the application uses the existing canonical profile names as session identities, and all four names matched the database/configuration.

The old setup assigned Excel copies only to Nandha, Jagadeeshwari and Rupashri, and assigned the covering-letter reference only to Rupashri. Sudharsan was deliberately omitted from those earlier copy assignments. The API then constructed the template catalog from each employee's owned documents/assignment ancestry. An employee without a suitable copied document therefore had no default preview, even though the master reference existed. An unrelated completed upload did not count as an assigned reference.

Preview fetches also lacked a timeout and profile cancellation. Library errors could leave an empty catalog described as a missing assignment, and an old profile's asynchronous work could finish after switching profiles. Queued operations could remain behind a stalled request.

## Change

`ew_slots` now acts as the shared master library. Each of the four existing employees has access to all three slots through a new, additive `ew_template_access` table. Its `(slot, user)` key and view/create/download permissions are independent of owned documents.

There are exactly **three shared master books and twelve access rows**. Template access does not create an employee copy or duplicate a master archive. A private, employee-owned workbook/document is created only by New Blank Template, completed upload, or an explicit admin assignment.

| Employee | NEFT SHEET | WORKSHEET | COVERING LETTER |
| --- | --- | --- | --- |
| Nandha | Available | Available | Available |
| Jagadeeshwari | Available | Available | Available |
| Sudharsan | Available | Available | Available |
| Rupashri | Available | Available | Available |

The three entries use the same master IDs for every profile:

- NEFT SHEET: `538-OMCL-Open University -Sept-26(03-10-2026).xlsx`.
- WORKSHEET: `Oct-26-OMCL - TNOU.xlsx`.
- COVERING LETTER: `538-September-26-TN-Open University.docx`.

Existing worksheet names, exact headers/column order, internal formulas, formats and blank manual inputs are retained. New calculated fields remain blank until sufficient inputs exist. The reference-copy/blanking engine from the previous implementation remains in use, with a bounded in-memory cache keyed by reference ID/revision to avoid repeated conversion during preview loading.

## API and isolation

- `GET /api/excel` returns owned files in `books` and the shared, permission-checked catalog in `templates`. It no longer depends on employee document copies.
- `GET /api/excel/metadata`, `/sheet` and `/document` may use a shared reference ID only with `template=1`. Those requests generate sanitized, blank previews.
- Shared reference grants do **not** permit downloading raw historical reference files, reading their raw content/history, saving changes to masters, or reading any other employee's saved work.
- `POST /api/excel/blank` accepts an authorized shared reference and creates a new private document owned by the current authenticated employee. View/create/download rights and locks remain enforced server-side.
- Existing file save, restore, upload, download and optimistic revision checks remain in place. Completed uploads remain independent and byte-identical on import; formula-free uploads receive no template formulas.
- Individual access rows are inserted idempotently. Existing saved documents/versions and explicit grant restrictions are not overwritten on repeated initialization.

## Loading and profile switches

- Preview state is explicit: idle, loading, ready, empty or error.
- Catalog failures identify an unavailable library and offer **Retry templates**; they do not claim a template is unassigned.
- Preview failures offer **Retry preview**. Requests time out after 20 seconds and clear the busy state.
- Initial hover waits for the catalog before deciding whether a template is configured.
- Every workspace request captures the profile/session and a session generation. Switching profiles aborts pending requests, discards stale responses/queued actions and closes old profile dialogs.
- A retry, profile cancellation or failure cannot leave a permanent Loading preview message. Truly unconfigured slots use a distinct empty state.
- Existing pointer transfer, heading/header hover, pinning, keyboard controls and touch expansion remain supported for every profile.

## Local data migration

The running server was stopped before the additive setup was applied, then restarted on port 8080. Backup:

`data/before-excel-workspace-20261107-143359.sqlite3`

The migration compared every existing workbook row and every version's metadata and SHA-256 content hash before/after setup. **All 16 existing files and all 19 stored versions were unchanged.** No new employee file was created during migration and no master file was duplicated. The twelve access rows are the only new persistent assignment records. Details are stored in ignored runtime file `data/shared-template-migration.json`.

The live browser verification only reads blank previews and switches profiles; it does not write or reset existing employee documents.

## Files changed for this fix

- `backend/excel_workspace.py`: shared access schema, catalog, sanitized reference authorization, private blank creation and revision-keyed blank preview cache.
- `frontend/js/pages/excel-workspace.js`: bounded/scoped requests, cancellation, state/error/retry handling and catalog-independent previews.
- `tools/setup_excel_workspace.py`: idempotent library setup; removed the partial employee-copy assignment loops.
- `tests/test_document_workspace.py`: supports fixtures with no employee copies.
- `tests/test_template_library.py`: backend coverage for all four profiles, isolated files, raw-master protection, idempotent migration and unchanged uploads.
- `tests/all-employees-excel.cjs`: independent, complete browser journeys for all four profiles plus error, timeout, stale response and touch tests.
- `tests/run_browser.py`: shared-library-only fixtures and reopening all twelve employee downloads.
- `tools/verify_employee_templates.cjs`: read-only live Chrome verification through the actual four profile selections; `--show` leaves Chrome open.
- `docs/EMPLOYEE_TEMPLATE_FIX_REPORT.md`: this report.
- `docs/EXCEL_WORKSPACE_REPORT.md`: links to this updated access model.

Earlier unrelated uncommitted changes were retained.

## Executed verification

Environment for private references/browser tooling on this machine:

```powershell
$env:EXCEL_REFERENCE_ROOT = 'C:\path\to\reference-files'
$env:PLAYWRIGHT_MODULE_PATH = 'C:\path\to\test-tools\node_modules\playwright'
```

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | **49 passed**, including the original workflow, auth, notification, timer, export and document tests |
| `python tests/run_browser.py --all-employees` | **Passed** for all four independent profiles, starting with **no pre-assigned employee copies** |
| All-employee browser matrix | Each profile: all three previews, heading/header hover, pointer transfer, pin, blank creation, editing/save, new-tab editing/save, custom filenames, download/reopen, completed uploads and isolation |
| Browser-download verification | All **12 Excel/Word downloads** reopened; saved values and original formulas retained; only three master books exist |
| Completed-upload verification | Every profile imported Excel/Word independently; downloaded initial bytes matched the upload exactly |
| Failure recovery | Injected catalog HTTP 503 shows a library error, not a missing assignment; retry restores the previews |
| Timeout recovery | Deliberately stalled metadata request times out, clears loading/busy state and retries successfully |
| Profile switching | Switching during a pending catalog request and during a pending preview request cancels/ignores old responses |
| Touch | Sudharsan opens all three sections manually at 390px with no page overflow |
| Normal-journey error monitoring | No JavaScript exceptions and no failed API requests; deliberately injected faults and expected authorization denials are separate test cases |
| `python tests/run_browser.py --excel` | Existing spreadsheet/document/large-file/mobile regression suite passed |
| `python tests/run_browser.py` | Passed: existing login, employee/admin navigation, task cards, timers, alerts, role controls, workflow/automation and mobile checks |
| `python tests/run_browser.py --action-center` | Passed: existing review/approval/return, reassignment, notifications/SSE, exports, mobile and access-control checks |
| `node tools/verify_employee_templates.cjs` | Passed on the real app for Nandha, Jagadeeshwari, Sudharsan and Rupashri; all three references, original sheet structure, empty preview, hover/pin, unchanged saved files and zero console/API errors |
| Python compilation, JavaScript syntax and whitespace checks | Passed |
| HTTP localhost check | **200** at `http://localhost:8080` |

Live per-profile results are saved to `data/employee-template-live-checks.json`, with blank-preview screenshots under `data/shared-templates-*.png`. Those artifacts are ignored by Git.

Browser suites are run sequentially on this Windows environment to avoid renderer contention; parallel browser launches caused action/navigation timeouts. The repeated hover test also waits for the actual expansion state rather than mistaking an already-loaded, collapsed table for an expanded preview.

## Startup and limits

The existing Python server directly serves the frontend; there is no separate frontend production build command. Production validation uses Python compilation, JavaScript syntax checks, the actual application startup `python backend/app.py`, browser regressions and the verified HTTP endpoint.

The shared access model creates no new runtime dependency. The existing bounded Excel calculation/Word-layout limitations are unchanged: unsupported formulas show pending, legacy `.xls` requires conversion, and complex structural Excel edits or advanced Word layout may require the original desktop application.

No original reference file, saved employee document, task, notification, timer or account was deleted or reset. No changes were pushed to GitHub.
