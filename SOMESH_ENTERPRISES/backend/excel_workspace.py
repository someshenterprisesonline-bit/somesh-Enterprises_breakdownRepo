"""Private, versioned XLSX storage. Uses the application's SQLite connection and sessions.

Original OOXML bytes are retained for imports/restores. Edits operate on the whole
workbook, never a lossy table export. No workbook is served through public storage.
"""
import base64
import copy
import io
import json
import math
import re
import uuid
import zipfile
import excel_calculation as CALC
import word_workspace as WORD
from datetime import datetime, date, time
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.workbook.properties import CalcProperties
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.formula.translate import Translator

MAX_BYTES = 10 * 1024 * 1024
SCHEMA = """
CREATE TABLE IF NOT EXISTS ew_books(id TEXT PRIMARY KEY,name TEXT NOT NULL,owner TEXT NOT NULL,
 slot INTEGER,master INTEGER DEFAULT 0,revision INTEGER DEFAULT 0,locked INTEGER DEFAULT 0,
 can_view INTEGER DEFAULT 1,can_edit INTEGER DEFAULT 1,can_download INTEGER DEFAULT 1,
 formulas_unlocked INTEGER DEFAULT 0,editor TEXT,modified TEXT,source TEXT);
CREATE TABLE IF NOT EXISTS ew_versions(book TEXT,revision INTEGER,data BLOB NOT NULL,
 actor TEXT,stamp TEXT,changes TEXT,PRIMARY KEY(book,revision));
CREATE TABLE IF NOT EXISTS ew_pending(id TEXT PRIMARY KEY,actor TEXT,data BLOB,name TEXT,stamp TEXT);
CREATE TABLE IF NOT EXISTS ew_slots(slot INTEGER PRIMARY KEY,name TEXT,book TEXT);
CREATE TABLE IF NOT EXISTS ew_template_access(slot INTEGER,user TEXT,
 can_view INTEGER DEFAULT 1,can_edit INTEGER DEFAULT 1,can_download INTEGER DEFAULT 1,
 PRIMARY KEY(slot,user));
"""


def init(g):
    db = g['DB']
    db.executescript(SCHEMA)
    columns = {r[1] for r in db.execute('PRAGMA table_info(ew_books)')}
    for column, declaration in [('format', "TEXT DEFAULT 'xlsx'"), ('category', "TEXT DEFAULT ''"), ('origin', "TEXT DEFAULT 'existing'"), ('schema_json', "TEXT DEFAULT '{}'")]:
        if column not in columns:
            db.execute('ALTER TABLE ew_books ADD COLUMN '+column+' '+declaration)
    for i in (1, 2, 3):
        db.execute('INSERT OR IGNORE INTO ew_slots VALUES (?,?,NULL)', (i, f'Template slot {i}'))
        for user in g['USERS']:
            if user['name'].casefold() in {'nandha','jagadeeshwari','sudharsan','rupashri'}:
                db.execute('INSERT OR IGNORE INTO ew_template_access(slot,user) VALUES (?,?)',(i,user['name']))
    db.commit()


def fail(g, message):
    raise g['FlowError'](message)


def allowed_employee(g, actor):
    identity = next((u.get('identity_name', actor) for u in g['USERS'] if u['name'] == actor), actor)
    return g['is_admin'](actor) or identity.casefold() in {'nandha', 'jagadeeshwari', 'sudharsan', 'rupashri'}


def read(data, g):
    if not data or len(data) > MAX_BYTES:
        fail(g, 'Workbook must be between 1 byte and 10 MB.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = z.infolist()
            if len(entries) > 5000 or sum(i.file_size for i in entries) > 80 * 1024 * 1024:
                fail(g, 'Workbook expands beyond the safe upload limit.')
            names = [i.filename.lower() for i in entries]
            if any('vbaproject' in n or 'externallinks/' in n or '/embeddings/' in n for n in names):
                fail(g, 'Macros, embedded objects and external workbook links are not supported.')
            if any(b'<!DOCTYPE' in z.read(i) or b'<!ENTITY' in z.read(i) for i in entries if i.filename.endswith('.xml')):
                fail(g, 'Unsafe workbook XML.')
        w = openpyxl.load_workbook(io.BytesIO(data), data_only=False, keep_links=False)
        if len(w.sheetnames) > 40 or sum(s.max_row * s.max_column for s in w) > 2000000 or any(s.max_column > 250 or s.max_row > 100000 for s in w):
            fail(g, 'Workbook exceeds 40 sheets, 250 columns, 100,000 rows or 2 million cells.')
        return w
    except g['FlowError']:
        raise
    except Exception:
        fail(g, 'Invalid or encrypted XLSX workbook. Legacy .xls must be saved as .xlsx in Excel first.')


def layout(s):
    start = 1
    for row in s.iter_rows(max_row=min(30, s.max_row)):
        if any(str(c.value or '').strip().lower().replace('.', '').replace(' ', '') in ('sno', 'slno') for c in row[:2]):
            start = row[0].row
            break
    end = start
    for m in s.merged_cells.ranges:
        if m.min_row <= start <= m.max_row:
            end = max(end, m.max_row)
    rows = [[s.cell(r, c).value for c in range(1, s.max_column + 1)] for r in range(start, end + 1)]
    data_end=s.max_row
    for row in s.iter_rows(min_row=end+1,max_col=min(s.max_column,3)):
        if any(isinstance(c.value,str) and re.match(r'^\s*(?:[A-Z]\.\s*)?(?:(?:over\s*all\s+|grand\s+|sub\s*)?total)\b',c.value,re.I) for c in row):
            data_end=row[0].row-1;break
    return {'header_start': start, 'header_end': end, 'header_rows': rows,'data_end':data_end}


def metadata(w):
    result = []
    for s in w:
        info = {'name': s.title, 'rows': s.max_row, 'columns': s.max_column, **layout(s),
                'merged': [str(m) for m in s.merged_cells.ranges],
                'validations': [dict(range=str(v.sqref), type=v.type, formula1=v.formula1, formula2=v.formula2) for v in s.data_validations.dataValidation],
                'formula_count': sum(c.data_type == 'f' for row in s for c in row),
                'types': sorted({c.data_type for row in s for c in row if c.value is not None})}
        result.append(info)
    return result


def book(g, actor, bid, action='view'):
    row = g['DB'].execute('SELECT * FROM ew_books WHERE id=?', (bid,)).fetchone()
    if not row or not (g['is_admin'](actor) or (row['owner'] == actor and row['can_view'])):
        raise g['Denied']('Workbook is unavailable or you do not have access.')
    b = dict(row)
    if not g['is_admin'](actor) and action in ('edit', 'download') and not b['can_' + action]:
        raise g['Denied']('This workbook does not permit ' + action + '.')
    if action == 'edit' and b['locked']:
        fail(g, 'Workbook is locked. Ask an administrator to unlock it.')
    return b


def template_book(g, actor, bid, action='view'):
    """A shared reference grants sanitized preview/blank creation, never raw access.

    Library access is independent of ownership of previously saved employee files.
    The existing book() guard still exclusively controls all private operations.
    """
    try:
        return book(g,actor,bid,action)
    except g['Denied']:
        row=g['DB'].execute('''SELECT b.*,a.can_edit AS grant_edit,a.can_download AS grant_download
          FROM ew_template_access a JOIN ew_slots s ON s.slot=a.slot
          JOIN ew_books b ON b.id=s.book
          WHERE a.user=? AND b.id=? AND b.master=1 AND a.can_view=1 AND b.can_view=1''',(actor,bid)).fetchone()
        if not row:raise g['Denied']('This shared template is not available to your profile.')
        b=dict(row);edit=b.pop('grant_edit');download=b.pop('grant_download')
        b['can_edit']=int(bool(b['can_edit'] and edit))
        b['can_download']=int(bool(b['can_download'] and download))
        if action=='edit' and not b['can_edit']:raise g['Denied']('This template is view-only.')
        if action=='edit' and b['locked']:fail(g,'This template is locked. Ask an admin to unlock it.')
        return b


def template_library(g,actor):
    rows=g['DB'].execute('SELECT b.*,s.slot AS library_slot FROM ew_slots s JOIN ew_books b ON b.id=s.book WHERE b.master=1 AND b.revision>0 ORDER BY s.slot').fetchall()
    result=[]
    for row in rows:
        try:b=template_book(g,actor,row['id'])
        except g['Denied']:continue
        result.append({'id':b['id'],'slot':row['library_slot'],'name':b['name'],'category':category(b),
                       'format':b['format'],'revision':b['revision'],'shared':True,
                       'can_edit':bool(b['can_edit']),'can_download':bool(b['can_download']),'locked':bool(b['locked'])})
    return result


def data_for(g, b, revision=None):
    v = g['DB'].execute('SELECT data FROM ew_versions WHERE book=? AND revision=?', (b['id'], revision or b['revision'])).fetchone()
    if not v:
        fail(g, 'Version not found.')
    return bytes(v[0])


def commit(g, b, actor, data, changes):
    rev = b['revision'] + 1
    stamp = g['ts']()
    g['DB'].execute('INSERT INTO ew_versions VALUES (?,?,?,?,?,?)', (b['id'], rev, data, actor, stamp, json.dumps(changes, default=str)))
    g['DB'].execute('UPDATE ew_books SET revision=?,editor=?,modified=? WHERE id=?', (rev, actor, stamp, b['id']))
    g['DB'].commit()
    return {'ok': True, 'id': b['id'], 'revision': rev}


def check_revision(g, b, body):
    if body.get('revision') != b['revision']:
        fail(g, 'Conflict: a newer version or permission change exists. Reopen the workbook before saving. Your unsaved edits remain available.')


def create(g, actor, name, owner, slot=None, master=False, source=None):
    bid = uuid.uuid4().hex
    g['DB'].execute('INSERT INTO ew_books(id,name,owner,slot,master,source) VALUES (?,?,?,?,?,?)', (bid, name, owner, slot, int(master), source))
    return dict(g['DB'].execute('SELECT * FROM ew_books WHERE id=?', (bid,)).fetchone())


def category(b):
    if b.get('category'):return b['category']
    name=b['name'].lower()
    if name.endswith('.docx'):return 'letter'
    if '538-omcl' in name or b.get('slot')==1:return 'neft'
    return 'worksheet'


def public(b):
    return {**{k:v for k,v in b.items() if k!='schema_json'},'category':category(b)}


def filename(name, extension):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name)).strip(' .')
    name=re.sub(r'\.(xlsx|docx)$','',name,flags=re.I).strip(' .')[:140]
    if not name:raise ValueError('Enter a filename.')
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',name,re.I):name='_'+name
    return name+'.'+extension


def source_book(g,b):
    # Only follow server-owned assignment ancestry from an authorized book.
    seen=set()
    while b.get('source') and b['source'] not in seen:
        seen.add(b['id'])
        parent=g['DB'].execute('SELECT * FROM ew_books WHERE id=?',(b['source'],)).fetchone()
        if not parent:break
        b=dict(parent)
    return b


def blank_workbook(data,g):
    w=read(data,g);schema={}
    for s in w:
        info=layout(s);types={};identifiers=set()
        for row in info['header_rows']:
            for i,v in enumerate(row,1):
                if re.search(r'account|ifsc|hsn|code',str(v or ''),re.I):identifiers.add(i)
        for row in s:
            for c in row:
                if isinstance(c,MergedCell):continue
                types[c.coordinate]='text' if c.column in identifiers else ('date' if c.is_date else c.data_type)
                if c.data_type=='f' or info['header_start']<=c.row<=info['header_end']:continue
                if c.row>info['header_end'] and isinstance(c.value,str) and re.match(r'^\s*(?:[A-Z]\.\s*)?(?:(?:over\s*all\s+|grand\s+|sub\s*)?total|[CS]?GST|admin charges)\b',c.value,re.I):continue
                c.value='SOMESH ENTERPRISES' if c.row<info['header_start'] and 'SOMESH ENTERPRISES' in str(c.value) else None
                if c.column in identifiers:c.number_format='@'
        schema[s.title]=types
    w.calculation=CalcProperties(calcId=0,fullCalcOnLoad=True)
    out=io.BytesIO();w.save(out)
    return out.getvalue(),schema


def blank_data(g,b):
    source=source_book(g,b)
    cache=g.setdefault('_EW_BLANK_CACHE',{})
    key=(source['id'],source['revision'],source.get('format','xlsx'))
    if key not in cache:
        data=data_for(g,source)
        value=(WORD.blank(data),{}) if source.get('format')=='docx' else blank_workbook(data,g)
        if len(cache)>=6:cache.pop(next(iter(cache)))
        cache[key]=value
    return cache[key]


def decorate_cells(result,w,caches,schema):
    for row in result['rows']:
        for c in row['cells']:
            expected=schema.get(c['address'])
            if not c['formula'] and c['value']=='':c['type']=expected or c['type']
            if c['formula']:
                value=caches.get((result['sheet'],c['address']))
                c['value']=str(value) if value is not None else ''
                c['calculation']='ready' if value is not None else 'pending'
                if isinstance(value,str) and value.startswith('#'):c['value']='';c['calculation']='pending'
                c['editable']=False
    return result


def cell_json(c, b, admin, headers):
    v = c.value
    return {'address': c.coordinate, 'value': v.isoformat() if isinstance(v, (datetime, date, time)) else (str(v) if v is not None else ''),
            'type': 'date' if isinstance(v, (datetime, date, time)) else c.data_type,
            'format': c.number_format, 'formula': c.data_type == 'f',
            'editable': not b['locked'] and (admin or b['can_edit']) and not isinstance(c, MergedCell) and c.row > headers and (c.data_type != 'f' or bool(admin and b['formulas_unlocked']))}


def _get(g, actor, path, qs):
    with g['LOCK']:
        init(g)
        if not allowed_employee(g, actor):
            raise g['Denied']('Excel Workspace is not assigned to this employee.')
        arg = lambda k, d='': (qs.get(k) or [d])[0]
        if path == '/api/excel':
            admin = g['is_admin'](actor)
            rows = g['DB'].execute('SELECT * FROM ew_books' + ('' if admin else ' WHERE owner=? AND can_view=1 AND master=0'), () if admin else (actor,)).fetchall()
            books=[dict(r) for r in rows]
            return {'books': [public(b) for b in books], 'templates':template_library(g,actor), 'slots': [dict(r) for r in g['DB'].execute('SELECT * FROM ew_slots')] if admin else [],
                    'employees': [u['name'] for u in g['USERS'] if allowed_employee(g, u['name']) and not u.get('admin')] if admin else []}
        bid = arg('id')
        template=arg('template')=='1'
        b = template_book(g,actor,bid) if template and path.endswith(('/metadata','/sheet','/document')) else book(g, actor, bid, 'download' if path.endswith('/download') else 'view')
        if path.endswith('/download'):
            extension=b.get('format') or 'xlsx'
            return (data_for(g, b, int(arg('version', '0')) or None), filename(arg('filename',b['name']),extension), 'application/vnd.openxmlformats-officedocument.'+('wordprocessingml.document' if extension=='docx' else 'spreadsheetml.sheet'))
        if path.endswith('/history'):
            return {'versions': [dict(r) for r in g['DB'].execute('SELECT revision,actor,stamp,changes FROM ew_versions WHERE book=? ORDER BY revision DESC', (bid,))]}
        data=data_for(g,b);schema=json.loads(b.get('schema_json') or '{}')
        if template:data,schema=blank_data(g,b)
        if b.get('format')=='docx':
            if path.endswith(('/document','/metadata')):return {'book':public(b),'document':WORD.preview(data),'template':template}
            fail(g,'Choose the document editor for Word files.')
        w = read(data, g)
        if path.endswith('/metadata'):
            return {'book': public(b), 'sheets': metadata(w)}
        if path.endswith('/sheet'):
            name = arg('sheet', w.sheetnames[0])
            if name not in w.sheetnames:
                fail(g, 'Worksheet not found.')
            s = w[name]; info = layout(s)
            offset = max(0, int(arg('offset', '0'))); limit = min(100, max(1, int(arg('limit', '50'))))
            query = arg('q').casefold(); col = int(arg('column', '0')); exact = arg('filter').casefold()
            indices = list(range(info['header_end'] + 1, s.max_row + 1))
            if query or exact:
                columns = s.max_column
                indices = [row[0].row for row in s.iter_rows(min_row=info['header_end'] + 1, max_col=columns)
                           if (not query or any(query in str(c.value if c.value is not None else '').casefold() for c in row))
                           and (not exact or (1 <= col <= columns and exact in str(row[col - 1].value or '').casefold()))]
            if arg('sort'):
                sc = min(s.max_column, max(1, int(arg('sort'))))
                def key(r):
                    v = s.cell(r, sc).value
                    return (0, v) if isinstance(v, (int, float)) else (1, str(v or '').casefold())
                indices.sort(key=key, reverse=arg('direction') == 'desc')
            result={'book': public(b), 'sheet':s.title, **info, 'columns': s.max_column, 'total': len(indices), 'offset': offset,
                    'rows': [{'number': r, 'cells': [cell_json(c, b, g['is_admin'](actor), info['header_end']) for c in s[r]]} for r in indices[offset:offset + limit]]}
            cached={} if template else CALC.cached(openpyxl.load_workbook(io.BytesIO(data),data_only=True))
            result=decorate_cells(result,w,cached,schema.get(s.title,{}))
            if template or b.get('origin')=='blank':
                calculations=CALC.Calculator(w).results()
                for row in result['rows']:
                    for c in row['cells']:
                        if c['formula']:
                            calc=calculations[(s.title,c['address'])]
                            c['value']=calc['value'];c['calculation']=calc['status']
            for row in result['rows']:
                for c in row['cells']:
                    if c['formula']:c['display']=CALC.display(c['value'],c['format'])
            return result
        fail(g, 'Unknown Excel API.')


def typed_value(g, c, value, kind, admin, formulas):
    if value == '' or value is None:
        return None
    if not isinstance(value, str) or len(value) > 32767:
        fail(g, 'Cell values must be text with at most 32,767 characters.')
    if value.startswith('='):
        if not (admin and formulas):
            fail(g, 'Only an administrator with formulas unlocked may enter formulas.')
        if re.search(r'(https?://|file:|\[|WEBSERVICE|HYPERLINK|DDE|\|)', value, re.I):
            fail(g, 'External or executable formulas are not allowed.')
        return value
    if kind == 'date' or c.is_date:
        try:
            return time.fromisoformat(value) if isinstance(c.value, time) else datetime.fromisoformat(value)
        except ValueError:
            fail(g, 'Dates must use ISO format, for example 2026-11-07.')
    if c.data_type == 'b':
        if value.lower() not in ('true', 'false'):
            fail(g, 'Boolean cells accept true or false.')
        return value.lower() == 'true'
    if kind=='text':return value
    if (c.data_type == 'n' and c.value is not None) or (c.value is None and kind in ('number','n')):
        try:
            d = Decimal(value)
            if not d.is_finite() or len(d.as_tuple().digits) > 15:
                fail(g, 'Excel numbers support 15 significant digits. Store longer identifiers as text.')
            return int(d) if d == d.to_integral() else float(d)
        except (InvalidOperation, ValueError, OverflowError):
            fail(g, 'Enter a valid finite number.')
    return value


def shift_reference(reference, current_sheet, target_sheet, row, delta, expand_end=False):
    """Adjust ordinary A1 references across sheets, including absolute references.

    Excel's $ locks apply to copying, not structural row changes. Named references
    are left as names; their definitions are adjusted separately.
    """
    prefix = ''
    if '!' in reference:
        prefix, reference = reference.rsplit('!', 1)
        current_sheet = prefix.strip("'").replace("''", "'")
        prefix += '!'
    if current_sheet != target_sheet:
        return prefix + reference
    match = re.fullmatch(r'(\$?[A-Z]{1,3}\$?)([1-9][0-9]*)(?::(\$?[A-Z]{1,3}\$?)([1-9][0-9]*))?', reference)
    row_match = re.fullmatch(r'(\$?)([1-9][0-9]*):(\$?)([1-9][0-9]*)', reference)
    if not match and not row_match:
        return prefix + reference
    a, lo, z, hi = (match or row_match).groups()
    lo = int(lo); hi = int(hi) if hi else None
    if hi is None:
        if delta < 0 and lo == row:
            return '#REF!'
        return prefix + a + str(lo + delta if lo >= row else lo)
    if delta > 0:
        lo = lo + 1 if lo >= row else lo
        hi = hi + 1 if hi >= row or (expand_end and hi==row-1) else hi
    else:
        if lo == hi == row:
            return '#REF!'
        lo = lo - 1 if lo > row else lo
        hi = hi - 1 if hi >= row else hi
    return prefix + a + str(lo) + ':' + z + str(hi)


def shift_formula(formula, current_sheet, target_sheet, row, delta, expand_end=False):
    tokens = Tokenizer(formula)
    for token in tokens.items:
        if token.subtype == 'RANGE':
            token.value = shift_reference(token.value, current_sheet, target_sheet, row, delta, expand_end)
    return '=' + ''.join(t.value for t in tokens.items)


def change_row(g, w, s, op, b, admin):
    action = op.get('action'); row = int(op.get('row') or s.max_row + 1)
    columns = s.max_column; end = s.max_row
    if action not in ('add', 'delete') or row <= layout(s)['header_end'] or row > end + (action == 'add'):
        fail(g, 'Choose a data row within the worksheet.')
    if action == 'add' and end >= 100000:
        fail(g, 'Row limit reached.')
    if s.tables or s._charts or s._images or len(s.conditional_formatting):
        fail(g, 'This sheet has tables, drawings or conditional formatting. Use Excel for structural row changes.')
    if any((m.min_row < row <= m.max_row if action=='add' else m.min_row <= row <= m.max_row) for m in s.merged_cells.ranges):
        fail(g, 'Merged header and summary rows cannot be inserted into or deleted. Choose an ordinary data row.')
    for ws in w:
        for cells in ws:
            for c in cells:
                if c.data_type == 'f':
                    if not isinstance(c.value, str) or re.search(r"(?:'[^']*:[^']*'|[A-Za-z0-9_]+:[A-Za-z0-9_]+)!|\[|\]", c.value):
                        fail(g, 'Array, structured or 3-D formulas require Excel for row changes.')
    delta = 1 if action == 'add' else -1
    # Preserve styles/formulas when inserting a record. Manual inputs start blank.
    source = max(layout(s)['header_end'] + 1, row - 1)
    pattern = [(copy.copy(s.cell(source, col)._style), s.cell(source, col).value if s.cell(source, col).data_type == 'f' else None, s.cell(source, col).coordinate) for col in range(1, columns + 1)]
    merges = [str(m) for m in s.merged_cells.ranges]
    for m in merges:
        s.unmerge_cells(m)
    dimensions = {r: copy.copy(d) for r, d in s.row_dimensions.items()}
    if action == 'add':
        s.insert_rows(row)
    else:
        s.delete_rows(row)
    s.row_dimensions.clear()
    for r, d in dimensions.items():
        if delta < 0 and r == row:
            continue
        dest = r + delta if r >= row else r
        d.index = dest; s.row_dimensions[dest] = d
    for m in merges:
        shifted = shift_reference(m, s.title, s.title, row, delta)
        if shifted != '#REF!':
            s.merge_cells(shifted)
    for ws in w:
        for cells in ws:
            for c in cells:
                if c.data_type == 'f':
                    c.value = shift_formula(c.value, ws.title, s.title, row, delta, delta>0 and ws==s and c.row>row)
        for v in ws.data_validations.dataValidation:
            if ws == s:
                v.sqref = ' '.join(x for ref in str(v.sqref).split() if (x := shift_reference(ref, s.title, s.title, row, delta)) != '#REF!')
            for key in ('formula1', 'formula2'):
                value = getattr(v, key)
                if value and not value.startswith('"'):
                    setattr(v, key, shift_formula('=' + value.lstrip('='), ws.title, s.title, row, delta).lstrip('='))
    names = w.defined_names.values() if hasattr(w.defined_names, 'values') else w.defined_names.definedName
    for name in names:
        if name.attr_text and '!' in name.attr_text:
            name.attr_text = shift_formula('=' + name.attr_text, '', s.title, row, delta)[1:]
    if action == 'add':
        for col, (style, formula, origin) in enumerate(pattern, 1):
            c = s.cell(row, col); c._style = style
            if formula:
                formula = shift_formula(formula, s.title, s.title, row, delta)
                shifted_origin = shift_reference(origin, s.title, s.title, row, delta)
                c.value = Translator(formula, origin=shifted_origin).translate_formula(c.coordinate)
        if row > end:
            s.cell(row, 1, '')


def _post(g, actor, path, body):
    with g['LOCK']:
        init(g)
        if not allowed_employee(g, actor):
            raise g['Denied']('Excel Workspace is not assigned to this employee.')
        admin = g['is_admin'](actor)
        db = g['DB']
        try:
            if path.endswith('/blank'):
                source=template_book(g,actor,body.get('id'),'edit')
                if not admin and not source['can_edit']:raise g['Denied']('This template is view-only.')
                data,schema=blank_data(g,source)
                b=create(g,actor,source_book(g,source)['name'],actor,source.get('slot'),source=source_book(g,source)['id'])
                db.execute('UPDATE ew_books SET format=?,category=?,origin=?,schema_json=?,can_edit=?,can_download=? WHERE id=?',
                           (source.get('format','xlsx'),category(source),'blank',json.dumps(schema),source['can_edit'],source['can_download'],b['id']))
                return commit(g,b,actor,data,{'created_blank':True})
            if path.endswith('/preview'):
                name = str(body.get('name', ''))
                if not name.lower().endswith(('.xlsx','.docx')):
                    fail(g, 'Use .xlsx for Excel or .docx for Word. Convert legacy files first.')
                try:
                    data = base64.b64decode(body.get('data', ''), validate=True)
                except Exception:
                    fail(g, 'Invalid upload encoding.')
                word=name.lower().endswith('.docx')
                if word:WORD.read(data)
                else:w = read(data, g)
                pid = uuid.uuid4().hex
                db.execute("DELETE FROM ew_pending WHERE stamp < datetime('now','-1 day')")
                if db.execute('SELECT COUNT(*) FROM ew_pending WHERE actor=?', (actor,)).fetchone()[0] >= 10:
                    fail(g, 'Too many pending previews. Import an existing preview or try tomorrow.')
                db.execute('INSERT INTO ew_pending VALUES (?,?,?,?,?)', (pid, actor, data, name[:180], g['ts']())); db.commit()
                if word:return {'preview':pid,'format':'docx','document':WORD.preview(data),'sheets':[]}
                sheets = metadata(w)
                for s, info in zip(w, sheets):
                    cached_w=openpyxl.load_workbook(io.BytesIO(data),data_only=True)
                    info['preview_rows'] = [[str(cached_w[s.title][c.coordinate].value or '') if c.data_type=='f' else str(c.value) if c.value is not None else '' for c in row] for row in s.iter_rows(min_row=info['header_end']+1, max_row=min(s.max_row, info['header_end']+8))]
                return {'preview': pid, 'sheets': sheets}
            if path.endswith('/import'):
                p = db.execute('SELECT * FROM ew_pending WHERE id=? AND actor=?', (body.get('preview'), actor)).fetchone()
                if not p:
                    fail(g, 'Upload preview not found. Upload again.')
                word=p['name'].lower().endswith('.docx')
                if body.get('completed') or word:
                    if word:WORD.read(bytes(p['data']))
                    else:read(bytes(p['data']),g)
                    slot=int(body.get('slot') or 0) if body.get('master') else None
                    if body.get('master') and not admin:raise g['Denied']('Only admins upload master templates.')
                    if body.get('master') and slot not in (1,2,3):fail(g,'Choose a template slot.')
                    b=create(g,actor,p['name'],actor,slot,bool(body.get('master')))
                    cat=body.get('category') or ('letter' if word else 'worksheet')
                    if cat not in ('neft','worksheet','letter') or ((cat=='letter')!=word):fail(g,'File format does not match the document section.')
                    db.execute('UPDATE ew_books SET format=?,category=?,origin=? WHERE id=?',('docx' if word else 'xlsx',cat,'reference' if body.get('master') else 'upload',b['id']))
                    if body.get('master'):db.execute('UPDATE ew_slots SET book=?,name=? WHERE slot=?',(b['id'],p['name'],slot))
                    result=commit(g,b,actor,bytes(p['data']),{'completed_upload':True,'filename':p['name']})
                    db.execute('DELETE FROM ew_pending WHERE id=?',(p['id'],));db.commit();return result
                w = read(bytes(p['data']), g)
                if body.get('sheet') not in w.sheetnames:
                    fail(g, 'Choose a worksheet.')
                warnings = []
                if body.get('id'):
                    b = book(g, actor, body['id'], 'edit'); check_revision(g, b, body)
                    original = read(data_for(g, b), g)
                    for s in w:
                        if s.title not in original.sheetnames:
                            warnings.append('Unexpected worksheet: ' + s.title)
                        elif layout(s)['header_rows'] != layout(original[s.title])['header_rows']:
                            warnings.append('Missing, unexpected or reordered columns in ' + s.title)
                    warnings += ['Missing worksheet: ' + n for n in original.sheetnames if n not in w.sheetnames]
                    if warnings and not body.get('confirm_mismatch'):
                        return {'warnings': warnings, 'confirmation_required': True}
                else:
                    slot = int(body.get('slot', 0))
                    if admin and slot not in (1, 2, 3):
                        fail(g, 'Choose template slot 1, 2 or 3.')
                    if not admin and not body.get('confirm_mismatch'):
                        return {'warnings': ['No reference template selected. This will create a private workbook without template matching.'], 'confirmation_required': True}
                    b = create(g, actor, p['name'], actor, slot if admin else None, admin)
                    if admin:
                        db.execute('UPDATE ew_slots SET book=?,name=? WHERE slot=?', (b['id'], body.get('template_name') or p['name'], slot))
                result = commit(g, b, actor, bytes(p['data']), {'import': p['name'], 'selected_sheet': body['sheet'], 'warnings': warnings})
                db.execute('DELETE FROM ew_pending WHERE id=?', (p['id'],)); db.commit()
                return result
            if path.endswith('/assign'):
                if not admin:
                    raise g['Denied']('Only admins assign templates.')
                source = book(g, actor, body.get('id')); owner = body.get('employee')
                if owner not in g['USER_NAMES'] or not allowed_employee(g, owner):
                    fail(g, 'Choose an authorized employee.')
                b = create(g, actor, source['name'], owner, source['slot'], source=source['id'])
                data,schema=blank_data(g,source) if body.get('blank') else (data_for(g,source),json.loads(source.get('schema_json') or '{}'))
                db.execute('UPDATE ew_books SET format=?,category=?,origin=?,schema_json=?,can_view=?,can_edit=?,can_download=? WHERE id=?',(source.get('format','xlsx'),category(source),'blank' if body.get('blank') else 'existing',json.dumps(schema),source['can_view'],source['can_edit'],source['can_download'],b['id']))
                return commit(g, b, actor, data, {'assigned_from': source['id'], 'employee': owner,'blank':bool(body.get('blank'))})
            b = book(g, actor, body.get('id'), 'view' if path.endswith('/permissions') else 'edit')
            check_revision(g, b, body)
            if path.endswith('/permissions'):
                if not admin:
                    raise g['Denied']('Only admins manage workbook permissions.')
                keys = ('can_view', 'can_edit', 'can_download', 'locked', 'formulas_unlocked')
                for k in keys:
                    if k in body:
                        if not isinstance(body[k], bool):
                            fail(g, 'Permissions must be true or false.')
                        db.execute('UPDATE ew_books SET ' + k + '=? WHERE id=?', (int(body[k]), b['id']))
                return commit(g, b, actor, data_for(g, b), {'permissions': {k: body[k] for k in keys if k in body}})
            if path.endswith('/restore'):
                if not admin:
                    raise g['Denied']('Only admins restore versions.')
                return commit(g, b, actor, data_for(g, b, int(body.get('version', 0))), {'restored_from': body['version']})
            if path.endswith('/save') and b.get('format')=='docx':
                changes=body.get('paragraphs',[])
                if not isinstance(changes,list):fail(g,'Paragraph changes must be a list.')
                data=WORD.edit(data_for(g,b),changes)
                return commit(g,b,actor,data,{'paragraphs':changes})
            if path.endswith(('/save','/calculate')):
                if b.get('format')=='docx':fail(g,'Choose the Word editor.')
                original_data=data_for(g,b)
                w = read(original_data, g); changes = body.get('changes', []); operations = body.get('rows', [])
                layouts={s.title:layout(s) for s in w}
                schema=json.loads(b.get('schema_json') or '{}')
                if not isinstance(changes, list) or len(changes) > 10000 or not isinstance(operations, list) or len(operations) > 100:
                    fail(g, 'Save at most 10,000 cell edits and 100 row changes at once.')
                for change in changes:
                    if change.get('sheet') not in w.sheetnames or not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,5}', str(change.get('address', ''))):
                        fail(g, 'Invalid worksheet or cell address.')
                    s = w[change['sheet']]; c = s[change['address']]
                    if c.row > 100000 or c.column > s.max_column or not cell_json(c, b, admin, layouts[s.title]['header_end'])['editable']:
                        fail(g, 'Cell is protected: ' + change['address'])
                    expected=schema.get(s.title,{}).get(c.coordinate)
                    headers=' '.join(str(row[c.column-1] or '') for row in layouts[s.title]['header_rows'])
                    kind='text' if re.search(r'account|ifsc|hsn|code',headers,re.I) else expected or change.get('type')
                    value = typed_value(g, c, change.get('value'), kind, admin, b['formulas_unlocked'])
                    change['previous_value'] = str(c.value) if c.value is not None else ''
                    change['previous_type'] = c.data_type
                    # Validate common inline Excel lists/numeric/date constraints; reject unsupported rules rather than ignore them.
                    for v in s.data_validations.dataValidation:
                        if c.coordinate in v.sqref and value is not None:
                            if v.type == 'list' and str(v.formula1 or '').startswith('"'):
                                if str(value) not in v.formula1.strip('"').split(','):
                                    fail(g, 'Value is outside the dropdown list at ' + c.coordinate)
                            else:
                                fail(g, 'This cell uses an Excel validation rule. Edit it in Excel to preserve validation.')
                    c.value = value
                    if isinstance(value, str) and not value.startswith('='):
                        c.data_type = 's'
                for op in operations:
                    if op.get('sheet') not in w.sheetnames:
                        fail(g, 'Unknown worksheet.')
                    change_row(g, w, w[op['sheet']], op, b, admin)
                    types=schema.get(op['sheet'],{});shifted={};at=int(op.get('row') or w[op['sheet']].max_row)
                    delta=1 if op['action']=='add' else -1
                    for address,kind in types.items():
                        col,num=re.fullmatch(r'([A-Z]+)(\d+)',address).groups();num=int(num)
                        if delta<0 and num==at:continue
                        shifted[col+str(num+delta if num>=at else num)]=kind
                    if delta>0:
                        for col in range(1,w[op['sheet']].max_column+1):
                            letter=get_column_letter(col);shifted[letter+str(at)]=types.get(letter+str(max(layouts[op['sheet']]['header_end']+1,at-1)),'text')
                    schema[op['sheet']]=shifted
                results=CALC.Calculator(w).results()
                changed=CALC.affected(w,changes) if not operations else set(results)
                results={k:v for k,v in results.items() if k in changed}
                if path.endswith('/calculate'):
                    return {'revision':b['revision'],'calculations':[{'sheet':s,'address':a,**v,'display':CALC.display(v['value'],w[s][a].number_format)} for (s,a),v in results.items()]}
                if operations:db.execute('UPDATE ew_books SET schema_json=? WHERE id=?',(json.dumps(schema),b['id']))
                w.calculation = CalcProperties(calcId=0, fullCalcOnLoad=True)
                out = io.BytesIO(); w.save(out)
                data=CALC.write_caches(out.getvalue(),results,CALC.cached(openpyxl.load_workbook(io.BytesIO(original_data),data_only=True)))
                return commit(g, b, actor, data, {'cells': changes, 'rows': operations})
            fail(g, 'Unknown Excel action.')
        except Exception:
            db.rollback()
            raise


def get(g, actor, path, qs):
    try:
        return _get(g, actor, path, qs)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        fail(g, 'Invalid Excel request parameters.')


def post(g, actor, path, body):
    try:
        return _post(g, actor, path, body)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        g['DB'].rollback()
        fail(g, 'Invalid Excel request parameters.')
