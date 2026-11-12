"""Run optional Playwright checks against synthetic temporary data, never port 8080."""
import json
import io
import os
import subprocess
import sys

from support import AppFixture, PROJECT


def main():
    app = AppFixture()
    try:
        info = app.seed_browser()
        if "--critical" in sys.argv or "--improvements" in sys.argv or "--formulas" in sys.argv or "--excel" in sys.argv or '--all-employees' in sys.argv or "--themes" in sys.argv:
            from test_excel_workspace import sample
            from test_document_workspace import seed_documents
            from test_formula_engine import template, payload
            from test_neft_sync import neft_file
            info['excel'] = seed_documents(app, actual=bool(os.environ.get('EXCEL_REFERENCE_ROOT')),assign='--all-employees' not in sys.argv and '--improvements' not in sys.argv and '--critical' not in sys.argv,worksheet_data=payload(template()) if '--formulas' in sys.argv or '--improvements' in sys.argv or '--critical' in sys.argv else None,neft_data=neft_file() if '--improvements' in sys.argv or '--critical' in sys.argv else None)
            from test_document_workspace import letter_sample
            letter = app.root / 'letter.docx'
            letter.write_bytes(letter_sample())
            info['excel']['letter_upload'] = str(letter)
            large = app.root / 'large-workbook.xlsx'
            large.write_bytes(sample(10000))
            info['excel']['large_upload'] = str(large)
            completed=app.root/'completed.xlsx'
            completed.write_bytes(sample())
            info['excel']['completed_upload']=str(completed)
        if '--neft' in sys.argv:
            import base64
            from test_neft_sync import neft_file, worksheet_file
            from test_excel_workspace import add_employees
            add_employees(app)
            admin = app.login()
            for slot, category, data in [(1, 'neft', neft_file()), (2, 'worksheet', worksheet_file())]:
                status, pending = app.request('/api/excel/preview', {'name': category+'.xlsx', 'data': base64.b64encode(data).decode()}, admin)
                assert status == 200, pending
                status, imported = app.request('/api/excel/import', {'preview':pending['preview'], 'completed':True, 'master':True, 'slot':slot, 'category':category}, admin)
                assert status == 200, imported
            upload = app.root / 'neft-100.xlsx'
            upload.write_bytes(neft_file(100))
            info['neft'] = {'token':app.login('Nandha'), 'other_token':app.login('Rupashri'), 'upload':str(upload)}
        if '--lan' in sys.argv:
            from test_excel_workspace import seed
            info['lan'] = seed(app)
        env = dict(os.environ, TEST_BASE_URL=app.origin, TEST_ADMIN_PIN=app.pin,
                   TEST_FIXTURE_INFO=json.dumps(info), TEST_ARTIFACT_DIR=str(app.root))
        script = 'all-employees-excel.cjs' if '--all-employees' in sys.argv else ("excel-workspace.cjs" if "--excel" in sys.argv else ("action-center.cjs" if "--action-center" in sys.argv else "browser.cjs"))
        if "--employees" in sys.argv: script = "employees.cjs"
        if "--assign-dialog" in sys.argv: script = "assign-dialog.cjs"
        if "--themes" in sys.argv: script = "theme-baseline.cjs" if os.environ.get("THEME_BASELINE") else "themes.cjs"
        if '--neft' in sys.argv: script = 'neft-sync.cjs'
        if '--lan' in sys.argv: script = 'lan-sync.cjs'
        if '--multi-user' in sys.argv: script = 'multi-user.cjs'
        if '--formulas' in sys.argv: script = 'formula-engine.cjs'
        if '--improvements' in sys.argv: script = 'workspace-improvements.cjs'
        if '--critical' in sys.argv: script = 'critical-sync-profiles.cjs'
        result = subprocess.call(["node", str(PROJECT / "tests" / script)], env=env)
        if result==0 and '--critical' in sys.argv:
            import shutil
            evidence=PROJECT/'data'/'critical-audit'/os.environ.get('TEST_THEME','dark')
            evidence.mkdir(parents=True,exist_ok=True)
            for file in app.root.glob('critical-*.png'):shutil.copy2(file,evidence/file.name)
            print('Critical screenshots:',evidence)
        if result == 0 and ('--formulas' in sys.argv or '--improvements' in sys.argv):
            import shutil
            evidence=PROJECT/'data'/'formula-audit'/os.environ.get('TEST_THEME','light')
            evidence.mkdir(parents=True,exist_ok=True)
            for file in list(app.root.glob('formula-*.png'))+list(app.root.glob('workspace-*.png')):shutil.copy2(file,evidence/file.name)
            print('Formula screenshots:',evidence)
        if result == 0 and '--neft' in sys.argv:
            import shutil
            import openpyxl
            neft = openpyxl.load_workbook(io.BytesIO((app.root / 'neft-browser.xlsx').read_bytes()))
            work = openpyxl.load_workbook(io.BytesIO((app.root / 'worksheet-browser.xlsx').read_bytes()))
            assert [r[1].value for r in neft['NEFT'].iter_rows(min_row=2)] == [r[1].value for r in work['Worksheet'].iter_rows(min_row=2)]
            assert neft['NEFT']['J2'].value == '=H2*2'
            assert work['Worksheet']['F2'].value == '=D2+E2'
            evidence = PROJECT / 'data' / 'neft-sync-audit' / os.environ.get('TEST_THEME', 'light')
            evidence.mkdir(parents=True, exist_ok=True)
            for file in app.root.glob('neft-*.png'): shutil.copy2(file, evidence / file.name)
            print('PASS reopening both browser downloads: identical employee order and preserved formulas; screenshot in', evidence)
        if result == 0 and '--excel' in sys.argv:
            import openpyxl
            import word_workspace as WORD
            import excel_workspace as EW
            workbook = openpyxl.load_workbook(io.BytesIO((app.root / 'edited.xlsx').read_bytes()))
            master = EW.book(app.g, 'Admin One', info['excel']['masters']['worksheet'])
            original = EW.read(EW.data_for(app.g, master), app.g)
            assert workbook.sheetnames == original.sheetnames
            for sheet in workbook:
                assert EW.layout(sheet)['header_rows'] == EW.layout(original[sheet.title])['header_rows']
            assert any(c.data_type == 'f' for sheet in workbook for row in sheet for c in row)
            cached = openpyxl.load_workbook(io.BytesIO((app.root / 'edited.xlsx').read_bytes()), data_only=True)
            assert cached['TNOU']['I8'].value == 2990 if 'TNOU' in cached.sheetnames else cached['Payroll']['E3'].value == 2400.5
            _, tree = WORD.read((app.root / 'edited.docx').read_bytes())
            assert any('Date: 07/11/2026' in WORD.text(p) for p in tree.findall('.//w:p', WORD.NS))
            print('PASS reopening browser-downloaded XLSX/DOCX: worksheets, headers, formulas, cached payroll result and saved letter text')
        if result==0 and '--all-employees' in sys.argv:
            import openpyxl
            import word_workspace as WORD
            for name in info['excel']['employees']:
                for category in ('neft','worksheet','letter'):
                    ext='docx' if category=='letter' else 'xlsx'
                    raw=(app.root/(name+'-'+category+'.'+ext)).read_bytes()
                    marker=name+' '+category+' saved in new tab'
                    if ext=='docx':
                        assert marker in json.dumps(WORD.preview(raw))
                    else:
                        w=openpyxl.load_workbook(io.BytesIO(raw))
                        assert any(c.value==marker for s in w for row in s for c in row)
                        assert any(c.data_type=='f' for s in w for row in s for c in row)
                links=app.g['q']('SELECT target FROM ew_neft_links WHERE book IN (SELECT id FROM ew_books WHERE owner=?) AND target IS NOT NULL',(name,))
                assert len(app.g['q']('SELECT id FROM ew_books WHERE owner=?',(name,)))==6+len(links)
            assert len(app.g['q']('SELECT id FROM ew_books WHERE master=1'))==3
            print('PASS all 12 employee-downloaded Excel/Word files reopened; saved values/formulas retained; only 3 shared master files')
        return result
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
