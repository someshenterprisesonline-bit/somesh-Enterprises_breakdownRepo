# Critical Worksheet–NEFT synchronization and profile-source fix

Branch: `fix-workspace-reverse-sync-profile-safety`. Existing uncommitted work was preserved. No commit, push or merge was performed.

## Root causes

**Synchronization:** full row synchronization existed only from NEFT to Worksheet. Worksheet saves called designation lookup refresh, but did not extract and persist full employee rows into NEFT. The UI treated a successful forward sync/connection as “Worksheet Synced,” including when zero NEFT employees had been transferred. A floating-point serialization edge case also made an unchanged generated payable look manually edited after a workbook round-trip.

**Profiles:** two different instances were running. The office service at **http://localhost:8080** had **14 active profiles, including 2 Admins**, matching its SQLite roster and `users.json`; none had the placeholder names. The isolated development service at **http://localhost:8081** had 9 synthetic test profiles, including Admin One/Admin Two and Worker profiles. The expected office accounts were not deleted or filtered out: the development login was showing its separate database. Chrome read-only verification confirmed that all 14 office profile buttons and both Admins match the office API.

## Storage and backups

- Office database: `SOMESH_ENTERPRISES/data/monthly_cycle.db`.
- Development database: `SOMESH_ENTERPRISES/data/workspace-dev/data/monthly_cycle.db`.
- Profiles are authoritative in SQLite `employees.profile`, keyed by `name_key`, with `deleted_at` controlling eligibility. `backend/users.json` is the synchronized mirror/initial legacy bootstrap input. PIN settings remain in the original private configuration/environment.
- Both source databases were opened read-only for inspection and online backups. Verified backups, including complete workbook version BLOBs, profiles, tasks and configuration files, were created **before code changes** under `data/backups/critical-sync-profiles/{office,development}/before-fix-20261111-113513`.
- The backup directory has inheritance removed and access limited to the Windows account, SYSTEM and Administrators. SQLite integrity, configuration hashes and backup/history digests were verified. No production database was copied into the development runtime.
- The post-fix preservation audit confirms original office profiles, task assignment fields and private configuration bytes match the backup. **No pre-fix workbook version is missing or changed.** Eight additional live-office versions had appeared at the audit time; those legitimate additions were retained. No snapshot was restored over live data. Aggregate findings: `data/critical-audit/preservation.json`.

The office backend was not restarted or migrated by this work. Source changes are implemented and reviewed locally; the isolated development server runs the fixed backend. Apply an office service restart through normal deployment when ready, rather than pointing a development process at office data.

## Exact field mapping

| Worksheet source | NEFT destination |
|---|---|
| S.No (A) | S.No (A) |
| Employee Name (B) | Name (B) |
| Designation (C) | Designation (C) |
| TNOU Take Home Salary (N) | Salary Amount (H) |

Take Home Salary is calculated using the preserved workbook formulas. Gross Net Salary D, Basis Salary E, Net Amount O and invoice totals are not used as the TNOU bank-payment amount.

The September NEFT reference contains both Office Copy/Net Banking Copy and its own TNOU sheet. Programmatic comparison against its embedded payroll supports N: 53 of 54 Office Copy records and 47 of 48 Net Banking Copy records match computed N within one rupee, consistent with whole-rupee formatting. None match gross D within that tolerance. One supplied employee bank entry differs from the computed take-home value. It was not corrected, overwritten or used to change the reference formulas. October formulas remain unchanged. Generic employee tables without a Take Home Salary header retain the existing explicit Salary Amount/Net Salary header fallback; Basis Salary is never inferred as payable. Missing/ambiguous salary headers are not guessed.

Bank, Account Number, Branch, IFSC, Remarks and existing formulas are excluded from reverse mapping. Missing salary inputs preserve an existing NEFT amount; pending/invalid formula calculations report a failure. A copied take-home amount is tracked and excluded from the legacy forward gross-salary mapping, preventing repeated deductions. Numeric ownership comparisons use Excel's 15-digit serialization precision.

## Reliable synchronization

- Worksheet autosave/explicit save persists the source, identifies or creates its private same-owner NEFT counterpart, extracts named employee rows, calculates payable values, updates mapped cells and records versioned NEFT changes.
- Existing `ew_neft_rows` UUIDs and `ew_neft_members` relationships are reused. New reverse provenance/status tables are additive. Known identities use UUIDs; initial adoption requires an unambiguous serial/name/designation identity. Conflicting rows trigger review rather than assigning bank details by name or position alone.
- Duplicate names remain separate employees when their established UUIDs distinguish them, including different designations. Lookup follows the bound UUID once available.
- Deletions clear only generated mapped values. Banking information and formulas remain on the old versioned row/UUID, and that row cannot be silently reused for a replacement employee.
- Worksheet row changes update mapping positions; NEFT sorting moves complete employee records and corresponding Worksheet payroll rows. Formula references, row-7 exceptions and saved bank associations remain intact.
- Reverse writes do not recursively invoke forward hooks. A savepoint protects target changes; a failed sync retains the saved source and existing target records. Independently edited mapped cells, locked targets and stale revisions produce useful conflicts.
- Successful status includes the actual number of saved employee mappings. Empty input reports **No employee records available**. Errors report **Sync failed — Retry** or **Mapping conflict — Review required**. Both Worksheet's **Retry NEFT sync** and NEFT's **Retry sync** work; the latter retries the failed direction.
- Existing SSE notices refresh a clean linked panel without full-page reload. A dirty NEFT draft is retained instead of overwritten. A second session cannot save an old revision over synchronized bank/payroll data.

## Profile and startup safeguards

- Existing SQLite identities are authoritative at startup. Stale/example JSON cannot inject replacement users. Missing `users.json` can be read from the valid existing SQLite roster without creating replacement accounts.
- Empty or admin-less established stores fail visibly. Missing production configuration or a missing configured production database does not silently fall back to a new demo installation.
- A genuinely new production installation requires explicit `--initialize`; existing installations do not use it. Example settings are not copied over established configurations.
- Optional `data_dir` resolves from the absolute application root, independent of shell working directory. Backend, launcher and backup tool share this resolver. Health checks compare storage identity; startup logs the environment and absolute database path without credentials.
- Development/test screens identify their synthetic environment. User lists remain API-driven. Invalid/unavailable profile metadata shows an error and no replacement profiles.
- Background metadata refresh avoids unnecessary login-form rerenders, preserving search/profile selection during account switching. Hover previews require pointer movement, preventing a new environment notice from causing accidental panel expansion during initial layout.

No office account recovery or merge is required. Existing names, roles, departments, identity keys, task assignments, access and credentials were preserved.

## Files changed for this task

Backend/runtime:

- `backend/worksheet_neft_sync.py` — new reverse pipeline, provenance, safe mappings and persisted status.
- `backend/runtime_storage.py` — shared absolute path/storage identity and read-only profile validation.
- `backend/neft_sync.py` — reverse integration, salary feedback guard, truthful counts, retry direction and safe explicit relinking.
- `backend/excel_workspace.py` — reverse save responses, metadata and Worksheet retry route.
- `backend/designation_lookup.py` — atomic linked updates and UUID-bound designation lookup.
- `backend/app.py`, `backend/employee_management.py` — authoritative profiles, production startup guards, runtime metadata/logging.
- `backend/launcher.py`, `tools/backup_db.py`, `tools/start_workspace_dev.py` — consistent storage, explicit initialization, preserved runtime data and development labeling.

Frontend:

- `frontend/js/pages/excel-workspace.js`, `frontend/js/pages/neft-sync.js` — reverse result handling, linked refresh, counts/errors/retry and stable hover behavior.
- `frontend/js/core/login-and-admins.js`, `frontend/js/core/shell.js`, `frontend/js/main.js` — environment notice, profile validation/error display and safe login refresh.

Tests/docs:

- `tests/test_critical_sync_profiles.py`, `tests/critical-sync-profiles.cjs`, `tests/run_browser.py` — critical regressions and Chrome evidence.
- `tests/support.py`, `tests/test_excel_workspace.py`, `tests/test_neft_sync.py`, `tests/test_startup.py` — explicit test environment, persisted fixture identities and updated two-way/startup expectations.
- `tests/neft-sync.cjs`, `tests/excel-workspace.cjs`, `tests/all-employees-excel.cjs` — regression scenarios and diagnostic evidence.
- `README.md`, `docs/CRITICAL_SYNC_PROFILE_REPORT.md` — deployment/usage and this report.

Pre-existing uncommitted formula engine changes remain preserved; no reference formulas or original Excel files were modified by this task.

## Executed verification

- Full backend suite: **104 tests; 99 passed, 5 optional private-reference tests skipped**. Output: `data/critical-full-tests.txt`. Final focused reruns cover reverse sync/profile safety and all NEFT API regressions, including duplicate names with different roles and blank names.
- The exact sample employees `wqe` and `ew` transfer from Worksheet to NEFT. Independent expected payable amounts are **1590.75** and **618.3515625**, respectively, for the supplied salary/attendance inputs and their original first/subsequent employee formulas.
- Backend checks cover designation and salary updates, repeat saves, bank fields, sorting, deletion, duplicate/blank names, zero/error calculations, locked-target rollback, successful retry, stale revisions, authoritative user metadata, unchanged task assignments and absolute storage paths. Existing formula/upload/export, security, HTTPS/LAN and Windows launcher tests pass.
- Chrome critical workflow passes against temporary fixtures and against the actual running **http://localhost:8081** app: Admin/Employee profile groups and navigation, environment notice, missing-profile error without fake cards, two-row autosave, payable mapping, designation update, bank-safe sorting, failure/retry, two-session conflict and saved reopen. Logs: `data/critical-browser.txt`, `data/critical-local-browser.txt`.
- Chrome Excel regression passes: editable/protected cells, immediate calculation, refresh, 10,000-row pagination, completed imports, exports and reopened XLSX/DOCX.
- Chrome NEFT regression passes: all sorts, payroll draft preservation, undo, add/delete, locked-target failure/retry, 100-row uploads, private-user isolation and reopened downloads.
- Chrome all-employee journeys pass for all four authorized Excel profiles, including all three sections, initial hover/collapse, file operations, session switching during pending requests, errors/retry and mobile bounds.
- Read-only Chrome verification at **http://localhost:8080** confirms the office's 14 profiles and 2 Admins match its API. No office login or write request was used.
- Final Windows startup rerun: 5 tests pass after the storage-path guards. Final focused reverse/profile and NEFT API reruns pass.
- Core Chrome regression passes: Dashboard, Dynamic Island alerts, role changes, task approvals, Tracker downloads, workflow rules, automation, sessions and mobile behavior. Output: `data/critical-core-browser.txt`.
- JavaScript syntax checks (28 files) and Python compileall pass. **Production frontend build: not applicable** — this application serves plain JavaScript directly and has no compilation/build command.

Screenshots: `data/critical-audit/local/critical-login.png` and `critical-sync.png`. Additional isolated fixture screenshots are under `data/critical-audit/dark/`. Logs/screenshots, runtime databases and all backups remain ignored by Git. No development dependencies were installed; the existing Playwright and Google Chrome were used.

## Running URLs and remaining items

- **Office profiles/data:** http://localhost:8080 — existing service and accounts retained.
- **Fixed isolated development app:** http://localhost:8081 — explicitly labeled synthetic data, opened in Chrome, using its existing development database with preserved records.

No destructive recovery was performed or is necessary for the profiles. Existing independently conflicting NEFT salary/designation records require explicit review; they are deliberately preserved. The supplied September reference has the bank/payable discrepancy described above, and the October reference has no saved calculation caches, so independent numeric expectations are used. Unsupported uploaded formulas retain the existing safe pending behavior. Office deployment/service restart has not been performed by the isolated development test workflow.


## Follow-up: office instance activated on localhost:8080

The user's subsequent report confirmed they were using the existing office service on port 8080. That process was still running the old backend. A fresh access-restricted online backup was verified before activation: `data/backups/critical-sync-profiles/office/office-activation-20261111-130058` (14 employees, 282 tasks, 42 workbooks, 319 versions).

The verified office process was restarted through the normal production launcher using its unchanged database/configuration. No development database, demo seed or profile import was used. The office health endpoint now reports `environment=production`, database storage identity and HTTPS port 8443. All 14 original profiles, including 2 Admins, remain available. This supersedes the earlier statement that office activation was pending.

The existing workbook containing the reported `wqe`/`ew` entries was retried through its owner's existing access context. The linked NEFT **Office Copy** sheet reports **31 saved employee records**, and both reported sample names are present. A read-only Chrome check confirmed the actual office UI shows all 31 named rows in that sheet. The retry itself reported 0 changed rows: it confirmed the current saved data rather than fabricating updates.

The frontend now selects the clean linked NEFT document after a Worksheet sync even if another clean NEFT file was displayed; unsaved drafts remain protected. This prevents a blank template/other document from being mistaken for the linked destination. A new isolated Chrome regression covers that view switch. Existing forward-only pair adoption is allowed only when the old NEFT amount still matches its last saved Worksheet baseline; independently changed amounts remain conflicts. Six focused backend regressions pass.

Verified saved office NEFT link: http://localhost:8080/?excel=<saved-document-id> . Refresh the office browser to load the updated frontend and use the saved **Office Copy** sheet.
