# Excel Workspace improvements — verification report

Branch: `feature-workspace-order-designations`, based on `0ce3a86`. Existing uncommitted formula-engine work was preserved. No commit, push or merge performed. The original reference workbook and live office SQLite database were not modified by this task. All tests use temporary synthetic databases; the persistent local development app uses a separate database under ignored `data/workspace-dev/data/`.

## Changes

- All authorized users see WORKSHEET, NEFT SHEET and COVERING LETTER in that order, including after reload. Workbook tab order is unchanged.
- NEFT names automatically look up designations from same-owner Worksheets. Matching uses Unicode case folding and collapses whitespace. Matching linked Worksheet records take priority; otherwise same-owner records are considered. Blank source roles, unknown names and conflicting duplicates are reported without blocking manual entry.
- Generated designation ownership is tracked by existing row UUIDs, so sorting and row changes do not attach roles to the wrong employee. Name changes update generated roles; clearing a name clears only its generated role. Manual roles are preserved. **Use Worksheet designations** explicitly replaces manual roles for known, unambiguous matches; unmatched manual values remain intact.
- Worksheet designation edits update only generated NEFT cells through versioned persistence. Updates use direct version writes rather than recursively invoking the forward synchronization hook. Mirrored generated data is excluded as independent lookup evidence. Source overrides are tracked separately so a legitimate Worksheet edit remains authoritative.
- Existing NEFT-to-Worksheet ordering, sorting, salary mapping, payroll drafts, conflict detection and retry behavior remain intact. Completed-upload original bytes and saved versions remain available; lookup may create a derived version filling blank designations, while existing manual roles and formulas remain unchanged. No template formulas are inserted into completed uploads.

## Row 7 root cause and repair

The actual `Oct-26-OMCL - TNOU (1).xlsx` has a completely empty row 7. Its first employee is row 8, including these special formulas:

- G8 = F8-H8; I8 = E8/F8*H8*13%; K8 = E8/F8*H8*12%.
- J8 and L8 are manual cells, not ESIC formulas.
- M8 = I8+J8+K8+L8; N8 = D8/F8*H8-M8; O8 = N8+M8.
- P8 = E8/F8*H8*3.4%; Q8 = O8+P8; R8 = Q8*18%; S8 = Q8+R8.

The application had exposed `header_end + 1` (row 7) as an editable employee row even though it was only a spacer. This was a row-mapping error rather than an incorrect payroll percentage.

For new manual templates, leading empty spacers in employee tables are removed using the existing structural row helper. All original formulas, formatting and references are translated together. The first employee now starts at row 7; subsequent employee-specific exceptions shift with their original rows. TNOU totals move to row 61 and include rows 7–60. All 667 formulas remain present across TNOU and In.

Legacy manual drafts that already exposed the spacer get missing first-row formulas and manual-entry types from the actual first reference employee. Existing employee records and formulas elsewhere remain in place; totals expand to include the repaired row. GET preparation is in memory; explicit saves persist the repair and current downloads include it. Completed uploads and historical downloads retain their original structure/bytes.

For D7=40000, E7=50000, F7=31, H7=31, with J7/L7 blank:

| Result | Value |
|---|---:|
| Absent days | 0 |
| Employer EPF | 6500 |
| Employee EPF | 6000 |
| Contributions | 12500 |
| Take-home salary | 27500 |
| Administration charge | 1700 |
| CTC | 41700 |
| GST | 7506 |
| Grand total | 49206 |

The ESIC inputs remain manual in this first-row exception. Later rows retain the original 20000, 15000 and 13000 bases and other distinctions. No formulas or rates were invented. The bounded Decimal formula evaluator, safe error handling and protected formula cells remain in use.

## Files modified or added for this task

- `backend/excel_workspace.py`: spacer compaction, legacy formula/type repair, correct final revision reporting, formula-preserving current exports.
- `backend/neft_sync.py`: lookup integration, source ownership, reverse designation updates and normalized adoption of existing employee records.
- `backend/designation_lookup.py`: same-owner lookup, ambiguity detection, generated/manual ownership and source provenance.
- `frontend/js/pages/excel-workspace.js`: section order.
- `frontend/js/pages/neft-sync.js`: immediate designation results, non-blocking messages and explicit replacement control.
- `tests/test_workspace_improvements.py`: nine tests for lookup, source changes, manual preservation/replacement, unknown/duplicate names, uploads, user isolation, all-row formula translation, row 7 and legacy types.
- `tests/workspace-improvements.cjs`: Chrome end-to-end verification against either an isolated fixture or the running development app.
- `tests/test_formula_engine.py`: accurate synthetic reference employee types and summary labels; compacted-template totals.
- `tests/test_document_workspace.py`, `tests/run_browser.py`: optional synthetic NEFT seed, new browser mode and evidence retention.
- `tests/excel-workspace.cjs`, `tests/all-employees-excel.cjs`: requested section-order expectations.
- `tools/start_workspace_dev.py`: isolated synthetic runtime using the existing launcher and its backup helper; no office settings or database are copied.
- `README.md`, `docs/WORKSPACE_IMPROVEMENTS_REPORT.md`: usage and this report.

## Executed verification

- Full backend suite: **99 tests, 94 passed, 5 skipped**. Skips require additional private reference files. The supplied TNOU reference test was enabled and passed. Output: `data/workspace-improvements-tests.txt`.
- Every one of the 54 employee rows was checked against the translated original formula definitions. All 667 original formulas evaluate successfully against the supplied workbook's inputs. The reference contains **no saved formula-result caches**, so equality against Excel's saved numeric results cannot be measured; independent expected-value tests are used instead.
- Nine dedicated improvement tests pass, including first-row salary/attendance, manual/template separation, generated designation updates and clears, manual overrides, explicit replacement, ambiguous/unknown/blank sources, sorting, same-owner access, original upload bytes and legacy schema repair.
- Chrome/Playwright `--improvements` passes in dark and light themes: section order, row 7 results and protection, autosave, normalized lookup, Worksheet role edits, unknown-name messages and saved reopen.
- Chrome/Playwright `--excel` passes: original controls, manual editing, calculations, upload/download, 10,000-row pagination, mobile bounds and reopened Excel/Word downloads.
- Chrome/Playwright `--neft` passes: all sorts, employee identity, salary mapping, unsaved payroll preservation, undo, add/delete, conflict/retry, 100-row uploads and both downloads.
- Chrome/Playwright `--all-employees` passes for Nandha, Jagadeeshwari, Sudharsan and Rupashri, including section order, refresh, isolated files and session switching.
- The same new workflow also passed against the actual running **http://localhost:8081** development server, not just a temporary fixture. Output: `data/workspace-local-browser.txt`.
- JavaScript syntax checks and Python compileall pass. **Production build: not applicable**; the README documents a plain JavaScript frontend served directly by Python, with no npm build step.

Screenshots are retained under `data/formula-audit/local/` and `data/formula-audit/{dark,light}/`: `workspace-row7.png`, `workspace-row7-totals.png` and `workspace-designations.png` (totals screenshot available from the final local run). Runtime logs and screenshots are ignored by Git. Browser test pages use installed Google Chrome through Playwright. The existing launcher also opened the development URL in Chrome.

## Local launch

The app is left running at **http://localhost:8081**, bound to loopback and backed by `data/workspace-dev/data/monthly_cycle.db`. Select **Nandha** for the synthetic employee workspace. A private Worksheet contains synthetic Ramesh/Kumar/Priya name-role lookup examples. The separate office server was not restarted or attached to a second process.

Run again with `python tools/start_workspace_dev.py --port 8081`. Repeating it reuses the healthy dev server. Before switching ports or refreshing copied backend source, stop only that verified development process. Startup checks and backs up the development database using the existing launcher.

No unsupported formulas were found in the reference. Existing safe restrictions for unsupported uploaded formulas and structural changes around merged rows/drawings remain. Invalid/ambiguous lookup data is deliberately left for manual review rather than guessed.
