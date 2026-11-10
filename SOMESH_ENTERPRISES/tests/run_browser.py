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
        if "--excel" in sys.argv or '--all-employees' in sys.argv:
            from test_excel_workspace import sample
            from test_document_workspace import seed_documents
            info['excel'] = seed_documents(app, actual=bool(os.environ.get('EXCEL_REFERENCE_ROOT')),assign='--all-employees' not in sys.argv)
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
        env = dict(os.environ, TEST_BASE_URL=app.origin, TEST_ADMIN_PIN=app.pin,
                   TEST_FIXTURE_INFO=json.dumps(info), TEST_ARTIFACT_DIR=str(app.root))
        script = 'all-employees-excel.cjs' if '--all-employees' in sys.argv else ("excel-workspace.cjs" if "--excel" in sys.argv else ("action-center.cjs" if "--action-center" in sys.argv else "browser.cjs"))
        if "--employees" in sys.argv: script = "employees.cjs"
        result = subprocess.call(["node", str(PROJECT / "tests" / script)], env=env)
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
                assert len(app.g['q']('SELECT id FROM ew_books WHERE owner=?',(name,)))==6
            assert len(app.g['q']('SELECT id FROM ew_books WHERE master=1'))==3
            print('PASS all 12 employee-downloaded Excel/Word files reopened; saved values/formulas retained; only 3 shared master files')
        return result
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
