# Excel formula engine verification — 2026-11-11

Implemented on `feature-excel-formula-engine`. Base commit: `0ce3a86`. No push, merge or commit performed. The starting worktree was clean. Production SQLite, original employee records and reference workbook bytes were not modified. All application/browser tests use AppFixture temporary databases and synthetic employee inputs.

## Reference analysis

Read `Oct-26-OMCL - TNOU (1).xlsx` programmatically with openpyxl, with and without data_only. TNOU has 653 formulas, 69 rows and 20 columns; In has 14 formulas, 45 rows and 26 columns. The read-only audit records every formula, dependency, merged range, manual-cell address, number-format/style distribution and row/column dimensions in ignored `data/formula-audit/reference.json`. A checked-in fixture retains formulas, headers, merged ranges and formats, with no employee inputs.

Every reference formula evaluates successfully against the completed original's inputs. **None of the 667 formula cells has a saved Excel calculation cache.** Numeric equality to Excel's saved output cannot be established from this file. Tests instead check exact formula definitions, independently computed expectations across all 54 employee rows, totals, day changes, invoice calculations and exported values. No formulas were rewritten to match expectations.

## Formula mappings and exceptions

The workbook is the executable template: calculations use each cell's original formula rather than a generic payroll mapping. Manual-entry templates retain their formulas; completed uploads retain their own independent workbook definitions.

- TNOU G: F-H; I/K: employer/employee EPF; J/L: ESIC; M: contribution sum; N: prorated D minus contributions; O: net amount; P: administration charge; Q: CTC; R: 18% GST; S: grand total. D62:S62 retain original SUM ranges. F68 is the constant formula `=13000`.
- Row 8: J8 and L8 are manual cells, not formulas. O8 is `=N8+M8`; Q8 is `=O8+P8`.
- Rows 9–37: J/L use the fixed 20000 base.
- Rows 38–41 and 49: J/L are manual cells; no formulas are injected.
- Rows 42–48: J uses fixed 15000; L uses E.
- Rows 50–61: I/J/L use fixed 13000, while K and P still use E.
- In: G9:G15 use `=Frow/31*Erow`. G16 is manual. G17 is SUM(G9:G16); G20 is SUM(G17:G19); G21 is G17*3.4%; G22 is SUM(G20:G21); G23 and G24 are each G22*9%; G25 is SUM(G22:G24). The fixed 31 and all rates are preserved.

## Architecture and changes

The existing bounded openpyxl-token parser and Decimal evaluator were extended; no eval, executable formulas, network functions or new runtime dependency was added. Reverse dependency closure selects affected formulas; recursive memoized evaluation orders dependencies and detects cycles. Cell/range/depth/work budgets bound evaluation. Unsupported expressions and explicit zero denominators remain pending; missing denominators stay blank. Untouched direct-input formulas stay blank; individual blank references in an otherwise active expression behave as zero. Empty SUM returns zero. These intentional blank-template presentation rules differ from displaying Excel errors in untouched rows.

Live previews remain debounced at 280 ms. Worksheet edits now autosave after 1.2 seconds of inactivity through the existing revision-checked save endpoint, preserving newer drafts during an in-flight save, keyboard focus and undo. Save Changes remains available. Export retains formula definitions plus calculated OOXML caches. Imported workbooks are not calculated or populated on arrival, and only affected supported formulas are recalculated after explicit edits. Unrelated imported caches are retained.

Formula results remain read-only. Admins can inspect original formulas in cell tooltips; employee API payloads do not expose those expressions. Theme, layout, scrolling, upload/download, pagination and NEFT synchronization are retained. Capturing a selected document before queuing its load also fixes a selection/reset race.

Modified/added files:

- `backend/excel_calculation.py`: constants, blank arithmetic, empty SUM, display and selective evaluation.
- `backend/excel_workspace.py`: dependency-selected recalculation and admin-only formula inspection metadata.
- `frontend/js/pages/excel-workspace.js`: inspection tooltip, worksheet autosave, draft/undo handling and document selection race fix.
- `frontend/js/pages/neft-sync.js`: forward the automatic-save flag for non-NEFT workbooks.
- `tests/fixtures/tnou_formula_manifest.json`: exact formulas and nonpersonal worksheet metadata.
- `tests/test_formula_engine.py`: reference, synthetic payroll, exceptions, invoice, dependency, error, API, export, sorting and structural-edit tests.
- `tests/test_document_workspace.py`: optional synthetic worksheet seeding and empty-SUM expectation.
- `tests/formula-engine.cjs`, `tests/run_browser.py`: dedicated two-sheet browser checks and screenshot retention.
- `tools/audit_formula_reference.py`: reproducible read-only formula/format/dependency audit.
- `docs/FORMULA_ENGINE_REPORT.md`: this report.

## Verification

- Full backend unittest discovery passed: 90 tests, 85 passed and 5 skipped (output in `data/formula-audit/backend-tests.txt`). Optional private-file suites require additional NEFT/Word files; the exact TNOU reference check is enabled separately with TNOU_REFERENCE_FILE.
- Six dedicated formula tests pass, including all 667 original formula definitions and successful evaluation of all original formulas. Explicit synthetic checks cover the 54 employee variants, both worksheets, partial-entry totals, working/present day changes, blank cells, circular/unsupported formulas, zero division, cross-sheet references, cached export, refresh, sorting and row insertion/deletion. Upload-mode row insertion does not inject formulas.
- Playwright `--formulas` passes in dark and light themes: manual entry, protected results, autosave, persisted reopen, present-day change, undo/redo after autosave and invoice recalculation. Screenshots: `data/formula-audit/{dark,light}/formula-{tnou,invoice}.png`.
- Playwright `--excel` passes in dark theme, including completed uploads, 10,000-row pagination, downloads reopened by Python, permissions and zero page/API errors.
- Playwright `--neft` passes: all sorts, editable salary mapping, undo after autosave, unsaved payroll preservation, add/delete, 100-row independent uploads, conflict/retry and both downloads.
- JavaScript syntax checks and Python compileall pass. This plain JavaScript/Python app has no production build command or compiled frontend; the served source is the production frontend.

For D9=23250, E9=20000, F9=31, H9=25, S9 is 22772.09677419355 and displays 22772 under the original `0` format. Calculations retain precision internally.

No reference formula is unsupported. Functions outside the evaluator's allowlist remain pending rather than executed. Existing structural restrictions for merged rows, tables, drawings, array/structured/3-D formulas remain in place. Template configuration remains managed through the existing admin template library; this change does not replace production templates or install employee reference data into production.

Reproduce from the project directory:

```powershell
$env:TNOU_REFERENCE_FILE = 'C:\path\Oct-26-OMCL - TNOU (1).xlsx'
python -m unittest discover -s tests -v
# Point to an installed Playwright module if it is not on Node's module path.
$env:PLAYWRIGHT_MODULE_PATH = 'C:\path\node_modules\playwright'
$env:TEST_THEME = 'dark' # repeat with light
python tests/run_browser.py --formulas
python tests/run_browser.py --excel
python tests/run_browser.py --neft
python tools/audit_formula_reference.py $env:TNOU_REFERENCE_FILE --output data/formula-audit/reference.json
```
