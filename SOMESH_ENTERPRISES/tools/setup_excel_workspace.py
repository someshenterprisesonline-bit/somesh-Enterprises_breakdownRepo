"""Configure three shared reference masters with access for all four employees.

Run from the project root after stopping the server:
  python tools/setup_excel_workspace.py C:/path/to/reference/files
This is idempotent: existing slots and employee files are never replaced or copied.
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import app
import excel_workspace as EW
import word_workspace as WORD
from inspect_excel_references import NAMES


def setup(reference_root):
    backup = ROOT / 'data' / ('before-excel-workspace-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
    with sqlite3.connect(backup) as destination:
        app.DB.backup(destination)
    print('Database backup:', backup.name)
    g = vars(app); actor = next(u['name'] for u in app.USERS if u.get('admin'))
    with app.LOCK:
        EW.init(g)
        for slot, name in enumerate(NAMES, 1):
            existing = app.DB.execute('SELECT book FROM ew_slots WHERE slot=?', (slot,)).fetchone()[0]
            if existing:
                print('Keeping populated template slot', slot)
                master = EW.book(g, actor, existing)
            else:
                data = (reference_root / name).read_bytes(); EW.read(data, g)
                master = EW.create(g, actor, name, actor, slot, True)
                app.DB.execute('UPDATE ew_slots SET book=?,name=? WHERE slot=?', (master['id'], name, slot))
                EW.commit(g, master, actor, data, {'reference_import': name})
                master = EW.book(g, actor, master['id'])
        letter_name='538-September-26-TN-Open University.docx'
        existing=app.DB.execute('SELECT book FROM ew_slots WHERE slot=3').fetchone()[0]
        if not existing:
            data=(reference_root/letter_name).read_bytes();WORD.read(data)
            letter=EW.create(g,actor,letter_name,actor,3,True)
            app.DB.execute("UPDATE ew_books SET format='docx',category='letter',origin='reference' WHERE id=?",(letter['id'],))
            app.DB.execute('UPDATE ew_slots SET book=?,name=? WHERE slot=3',(letter['id'],letter_name))
            EW.commit(g,letter,actor,data,{'reference_import':letter_name})
            existing=letter['id']
        for employee in ('Nandha','Jagadeeshwari','Sudharsan','Rupashri'):
            if employee not in app.USER_NAMES:raise RuntimeError('Missing existing employee: '+employee)
            if len(EW.template_library(g,employee))!=3:raise RuntimeError('Check shared template permissions for '+employee)
        print('Three shared master references available to all four employees; no employee files duplicated or reset.')


if __name__ == '__main__':
    try:
        setup(Path(sys.argv[1]))
    finally:
        app.DB.close()
