"""Private NEFT/Worksheet pairs. Canonical uploads and version bytes remain immutable."""
import copy
import io
import json
import re
import uuid
import designation_lookup as DESIGNATIONS
import worksheet_neft_sync as REVERSE
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_from_string


SCHEMA = """
CREATE TABLE IF NOT EXISTS ew_neft_rows(id TEXT PRIMARY KEY,book TEXT,sheet TEXT,position INTEGER,
 ordinal INTEGER,signature TEXT,active INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS ew_neft_positions ON ew_neft_rows(book,sheet,position);
CREATE TABLE IF NOT EXISTS ew_neft_sort(book TEXT,sheet TEXT,col INTEGER,direction TEXT,PRIMARY KEY(book,sheet));
CREATE TABLE IF NOT EXISTS ew_neft_links(book TEXT,sheet TEXT,target TEXT UNIQUE,target_sheet TEXT,
 status TEXT,error TEXT,salary_note TEXT,PRIMARY KEY(book,sheet));
CREATE TABLE IF NOT EXISTS ew_neft_members(source_id TEXT PRIMARY KEY,book TEXT,sheet TEXT,
 position INTEGER,last_values TEXT);
"""


def init(g):
    g['DB'].executescript(SCHEMA + DESIGNATIONS.SCHEMA + REVERSE.SCHEMA)


def ew():
    import excel_workspace
    return excel_workspace


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


def columns(s, source=False):
    info = ew().layout(s)
    labels = [normalized(' '.join(str(row[i] or '') for row in info['header_rows'])) for i in range(s.max_column)]
    names = {'name'} if source else {'name', 'nameoftheemployees', 'nameoftheemployee', 'nameofemployees', 'employeename'}
    if len(labels) < 3 or labels[0] not in ('sno', 'slno', 'serialno') or labels[1] not in names or labels[2] != 'designation':
        return None
    salary = [i + 1 for i, label in enumerate(labels) if label in ({'salaryamount'} if source else {'netsalary'})]
    return {'serial': 1, 'name': 2, 'designation': 3, 'salary': salary[0] if len(salary) == 1 else None}


def bounds(s):
    info = ew().layout(s)
    end = info['data_end']
    for merged in s.merged_cells.ranges:
        if merged.min_row > info['header_end'] and merged.min_col == 1 and merged.max_col >= 3:
            end = min(end, merged.min_row - 1)
    return info['header_end'] + 1, end


def value(s, cached, row, col):
    cell = s.cell(row, col)
    return cached.cell(row, col).value if cell.data_type == 'f' else cell.value


def identity(s, row):
    # Used only for adopting an existing Worksheet or replacing a whole upload.
    # Once paired, immutable UUIDs, not names/positions, track employee edits.
    return tuple(normalized(s.cell(row, c).value) for c in (2, 3))


def signature(s, row):
    return json.dumps([str(s.cell(row, c).value or '') for c in range(1, min(7, s.max_column) + 1)])


def reconcile(g, b, s, changes):
    db = g['DB']; start, end = bounds(s)
    previous = [dict(r) for r in db.execute('SELECT * FROM ew_neft_rows WHERE book=? AND sheet=?', (b['id'], s.title))]
    replacing = bool(changes.get('restored_from') or changes.get('import'))
    if replacing:
        db.execute('UPDATE ew_neft_rows SET active=0,position=NULL WHERE book=? AND sheet=?', (b['id'], s.title))
    else:
        for op in changes.get('rows', []):
            if op.get('sheet') != s.title: continue
            at = int(op['row'])
            if op['action'] == 'delete':
                db.execute('UPDATE ew_neft_rows SET active=0,position=NULL WHERE book=? AND sheet=? AND position=? AND active=1', (b['id'], s.title, at))
                db.execute('UPDATE ew_neft_rows SET position=position-1 WHERE book=? AND sheet=? AND position>? AND active=1', (b['id'], s.title, at))
            else:
                db.execute('UPDATE ew_neft_rows SET position=position+1 WHERE book=? AND sheet=? AND position>=? AND active=1', (b['id'], s.title, at))
    current = {r['position']: dict(r) for r in db.execute('SELECT * FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1', (b['id'], s.title))}
    ordinal = max([r['ordinal'] for r in previous] or [0]); used = set()
    for row in range(start, end + 1):
        sig = signature(s, row); existing = current.get(row)
        if not existing:
            matches = [r for r in previous if replacing and r['signature'] == sig and r['id'] not in used]
            if len(matches) == 1:
                existing = matches[0]
                db.execute('UPDATE ew_neft_rows SET position=?,active=1 WHERE id=?', (row, existing['id']))
            else:
                ordinal += 1
                existing = {'id': uuid.uuid4().hex, 'ordinal': ordinal}
                db.execute('INSERT INTO ew_neft_rows VALUES (?,?,?,?,?,?,1)', (existing['id'], b['id'], s.title, row, ordinal, sig))
        used.add(existing['id'])
        db.execute('UPDATE ew_neft_rows SET signature=? WHERE id=?', (sig, existing['id']))
    db.execute('UPDATE ew_neft_rows SET active=0,position=NULL WHERE book=? AND sheet=? AND (position<? OR position>?)', (b['id'], s.title, start, end))


def order(g, b, s, rows):
    setting = g['DB'].execute('SELECT col,direction FROM ew_neft_sort WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone()
    positions = {r['position']: r['ordinal'] for r in g['DB'].execute('SELECT position,ordinal FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1', (b['id'], s.title))}
    rows = sorted(rows, key=lambda r: positions.get(r, r))
    if not setting or not setting['col']: return rows
    col, direction = setting['col'], setting['direction']
    def key(row):
        v = s.cell(row, col).value
        if col == 1:
            try:
                n = Decimal(str(v)); return (0, n) if n.is_finite() else (1, str(v).casefold())
            except (InvalidOperation, ValueError): return (1, str(v or '').casefold())
        return str(v or '').casefold()
    populated = [r for r in rows if s.cell(r, col).value not in (None, '')]
    empty = [r for r in rows if s.cell(r, col).value in (None, '')]
    return sorted(populated, key=key, reverse=direction == 'desc') + empty


def describe(g, b, s):
    if b['master'] or ew().category(b) != 'neft' or not columns(s, True): return None
    setting = g['DB'].execute('SELECT col,direction FROM ew_neft_sort WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone()
    link = g['DB'].execute('SELECT * FROM ew_neft_links WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone()
    return {'column': setting['col'] if setting else 0, 'direction': setting['direction'] if setting else 'original',
            'source_sheet': s.title, 'target': link['target'] if link else None,
            'target_revision': (g['DB'].execute('SELECT revision FROM ew_books WHERE id=?', (link['target'],)).fetchone() or [0])[0] if link and link['target'] else 0, 'status': link['status'] if link else 'waiting',
            'records':g['DB'].execute('SELECT count(*) FROM ew_neft_members WHERE book=? AND sheet=?',(b['id'],s.title)).fetchone()[0],
            'error': link['error'] if link else '', 'salary_note': link['salary_note'] if link else '',
            'designation_values': [{'address':'C'+str(r['position']),'value':r['value']} for r in g['DB'].execute("SELECT r.position,d.value FROM ew_designations d JOIN ew_neft_rows r ON r.id=d.row_id WHERE d.book=? AND d.sheet=? AND r.active=1 AND d.status!='manual'",(b['id'],s.title))],
            'designation_notes': [dict(r) for r in g['DB'].execute("SELECT r.position AS row,d.status FROM ew_designations d JOIN ew_neft_rows r ON r.id=d.row_id WHERE d.book=? AND d.sheet=? AND r.active=1 AND d.status IN ('unknown','blank','ambiguous')",(b['id'],s.title))]}


def adjust_formula(formula, current, target, mapping):
    """Follow employee references, keeping other sheets' references untouched."""
    tokens = Tokenizer(formula)
    stack = []
    for index, token in enumerate(tokens.items):
        if token.type == 'FUNC':
            if token.subtype == 'OPEN': stack.append(token.value[:-1].upper())
            elif stack: stack.pop()
        if token.subtype != 'RANGE': continue
        prefix, reference = ('', token.value)
        sheet = current
        if '!' in reference:
            prefix, reference = reference.rsplit('!', 1)
            sheet = prefix.strip("'").replace("''", "'"); prefix += '!'
        if sheet != target: continue
        parts = reference.split(':')
        matches = [re.fullmatch(r'(\$?[A-Z]{1,3}\$?)([1-9][0-9]*)', p) for p in parts]
        if not all(matches) or len(parts) > 2: continue
        if len(parts) == 2:
            lo, hi = sorted(int(m[2]) for m in matches)
            affected = [mapping.get(r, r) for r in range(lo, hi + 1)]
            if sorted(affected) == list(range(lo, hi + 1)): continue
            ordered = sorted(set(affected))
            groups = []
            for row in ordered:
                if groups and row == groups[-1][1] + 1: groups[-1][1] = row
                else: groups.append([row, row])
            if len(groups) > 1:
                plain = index > 0 and index + 1 < len(tokens.items) and tokens.items[index-1].type in ('FUNC','SEP') and tokens.items[index+1].type in ('FUNC','SEP')
                if not plain or not stack or stack[-1] not in ('SUM','MIN','MAX','AVERAGE','COUNT','COUNTA'):
                    raise ValueError('A partial formula range cannot follow this sort safely. Original workbook retained.')
            token.value = ','.join(prefix + matches[0][1] + str(a) + ':' + matches[1][1] + str(z) for a,z in groups)
            continue
        token.value = prefix + ':'.join(m[1] + str(mapping.get(int(m[2]), int(m[2]))) for m in matches)
    return '=' + ''.join(t.value for t in tokens.items)


def snapshot(s, row):
    return [copy.copy(s.cell(row, col)) for col in range(1, s.max_column + 1)]


def place(s, row, cells):
    for col, old in enumerate(cells, 1):
        if isinstance(old, MergedCell): raise ValueError('Merged employee rows cannot be reordered safely.')
        cell = s.cell(row, col); cell.value = old.value; cell.data_type = old.data_type
        cell._style = copy.copy(old._style); cell.comment = copy.copy(old.comment)
        cell._hyperlink = copy.copy(old.hyperlink)
        if cell._hyperlink: cell._hyperlink.ref = cell.coordinate


def permute(w, s, mapping, records):
    dimensions = {r: copy.copy(s.row_dimensions[r]) for r in mapping if r in s.row_dimensions}
    for row in mapping:
        if row in s.row_dimensions: del s.row_dimensions[row]
    for old, dest in mapping.items():
        if old in records: place(s, dest, records[old])
        if old in dimensions:
            dim = dimensions[old]; dim.index = dest; s.row_dimensions[dest] = dim
    for ws in w:
        for row in ws:
            for cell in row:
                if cell.data_type == 'f': cell.value = adjust_formula(cell.value, ws.title, s.title, mapping)
    for name in w.defined_names.values():
        if name.attr_text and '!' in name.attr_text:
            name.attr_text = adjust_formula('=' + name.attr_text, '', s.title, mapping)[1:]


def serialize(w, original, moves=None, calculations=None):
    E = ew(); caches = E.CALC.cached(openpyxl.load_workbook(io.BytesIO(original), data_only=True))
    if moves:
        remapped = {}
        for (sheet, address), value in caches.items():
            col, row = coordinate_from_string(address)
            remapped[(sheet, col + str(moves.get((sheet, row), row)))] = value
        caches = remapped
    out = io.BytesIO(); w.save(out)
    return E.CALC.write_caches(out.getvalue(), calculations or {}, caches)


def export(g, b, data):
    w = ew().read(data, g); moves = {}
    for s in w:
        if not columns(s, True): continue
        start, end = bounds(s); rows = list(range(start, end + 1)); ordered = order(g, b, s, rows)
        mapping = dict(zip(ordered, rows))
        if all(a == z for a, z in mapping.items()): continue
        permute(w, s, mapping, {r: snapshot(s, r) for r in rows})
        moves.update({(s.title, r): d for r, d in mapping.items()})
    return serialize(w, data, moves) if moves else data


def ensure_link(g, actor, b, s, target_id=None):
    E = ew(); db = g['DB']
    fresh = target_id == 'new'
    if fresh: target_id = None
    existing = db.execute('SELECT * FROM ew_neft_links WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone()
    if existing and existing['target'] and not fresh and (not target_id or existing['target'] == target_id): return dict(existing)
    if target_id:
        target = E.book(g, actor, target_id, 'edit')
        if target['owner'] != b['owner'] or target['master'] or E.category(target) != 'worksheet':
            raise g['Denied']('Choose a private Worksheet belonging to the NEFT document owner.')
        occupied=db.execute('SELECT * FROM ew_neft_links WHERE target=?',(target_id,)).fetchone()
        if occupied and occupied['book']!=b['id']:
            old=E.book(g,actor,occupied['book']);first=db.execute('SELECT changes FROM ew_versions WHERE book=? ORDER BY revision LIMIT 1',(old['id'],)).fetchone()
            ow=E.read(E.data_for(g,old),g);os=ow[occupied['sheet']];salary=columns(os,True)['salary']
            bank=any(c.value not in (None,'') and c.data_type!='f' for row in os.iter_rows(min_row=bounds(os)[0],max_row=bounds(os)[1]) for c in row if c.column not in (1,2,3,salary))
            if not first or json.loads(first[0]).get('created_for_worksheet')!=target_id or bank:E.fail(g,'This Worksheet is already linked to another NEFT document with employee/banking history. Review the existing link.')
            db.execute('DELETE FROM ew_neft_members WHERE book=? AND sheet=?',(old['id'],occupied['sheet']))
            db.execute('DELETE FROM ew_neft_links WHERE book=? AND sheet=?',(old['id'],occupied['sheet']))
        data = E.data_for(g, target); w = E.read(data, g)
    else:
        templates = [t for t in E.template_library(g, b['owner']) if t['category'] == 'worksheet' and t['can_edit'] and not t['locked']]
        if len(templates) != 1: E.fail(g, 'Configure one editable Worksheet template before automatic synchronization.')
        source = E.template_book(g, b['owner'], templates[0]['id'], 'edit')
        data, schema = E.blank_data(g, source); w = E.read(data, g)
        # Validate before creating any counterpart.
        if not any(columns(ws) for ws in w): E.fail(g, 'Worksheet template needs S.No, Name of the Employees and Designation headers.')
        target = E.create(g, actor, 'Worksheet - ' + b['name'], b['owner'], 2, source=source['id'])
        db.execute("UPDATE ew_books SET category='worksheet',origin='blank',schema_json=? WHERE id=?", (json.dumps(schema), target['id']))
        E.write_version(g, target, actor, data, {'created_for_neft': b['id'], 'sheet': s.title})
    sheets = [ws for ws in w if columns(ws)]
    if len(sheets) != 1: E.fail(g, 'Choose a Worksheet with one unambiguous employee table.')
    if existing:
        # Relinking never deletes the old document or versions.
        db.execute('DELETE FROM ew_neft_members WHERE book=? AND sheet=?', (b['id'], s.title))
    db.execute('INSERT INTO ew_neft_links VALUES (?,?,?,?,?,?,?) ON CONFLICT(book,sheet) DO UPDATE SET target=excluded.target,target_sheet=excluded.target_sheet,status=excluded.status,error=excluded.error',
               (b['id'], s.title, target['id'], sheets[0].title, 'pending', '', ''))
    return dict(db.execute('SELECT * FROM ew_neft_links WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone())


def sync(g, actor, b, s, original, target_id=None):
    E = ew(); db = g['DB']; source_cols = columns(s, True)
    link = ensure_link(g, actor, b, s, target_id)
    edits,_=DESIGNATIONS.apply(g,b,s,{})
    if edits:
        original=serialize(s.parent,original)
        E.write_version(g,b,actor,original,{'designation_lookup':True,'cells':edits})
        b['revision']+=1
        reconcile(g,b,s,{})
    target = E.book(g, actor, link['target'], 'edit')
    if target['owner'] != b['owner']: raise g['Denied']('Document owners must match.')
    target_data = E.data_for(g, target); w = E.read(target_data, g); ws = w[link['target_sheet']]
    target_cols = columns(ws)
    if not target_cols: E.fail(g, 'Worksheet employee headers have changed; synchronize after restoring them.')
    cached_source = openpyxl.load_workbook(io.BytesIO(original), data_only=True)[s.title]
    registry = {r['position']: dict(r) for r in db.execute('SELECT * FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1', (b['id'], s.title))}
    source_rows = [r for r in order(g, b, s, list(registry)) if str(value(s,cached_source,r,2) or '').strip()]
    members = {r['source_id']: dict(r) for r in db.execute('SELECT * FROM ew_neft_members WHERE book=? AND sheet=?', (b['id'], s.title))}
    start, end = bounds(ws); original_end = end; original_max_row = ws.max_row
    old_positions = set(range(start, end + 1)); reserved = {m['position'] for m in members.values()}
    unclaimed = {r for r in old_positions - reserved if any(ws.cell(r, c).value not in (None, '') and ws.cell(r, c).data_type != 'f' for c in range(1, ws.max_column + 1))}
    output = []; used = set(); changed = []; ids = []
    salary_note = 'Salary mapping unavailable for these headers.'
    for row in source_rows:
        rid = registry[row]['id']; member = members.get(rid); old_position = member['position'] if member else None
        if old_position not in old_positions: old_position = None
        if old_position is None:
            matches = [r for r in unclaimed - used if identity(ws, r) == identity(s, row) and any(identity(s, row))]
            if len(matches) > 1: E.fail(g, 'Ambiguous duplicate employee identities in Worksheet. Choose a separate Worksheet.')
            if matches: old_position = matches[0]
        if old_position is None:
            available = sorted(old_positions - used - reserved - unclaimed)
            old_position = available[0] if available else None
        if old_position is None:
            # Existing helpers preserve summary ranges/merges and other sheets.
            at = end + 1; E.change_row(g, w, ws, {'action': 'add', 'row': at}, target, g['is_admin'](actor))
            if target.get('origin') != 'blank':
                for cell in ws[at]:
                    if cell.data_type == 'f': cell.value = None  # no new formulas in completed uploads
            end += 1; old_positions.add(at); old_position = at
        if member is None and old_position in unclaimed:
            db.execute('INSERT OR REPLACE INTO ew_designation_sources VALUES (?,?)',(rid,str(ws.cell(old_position,3).value or '')))
        used.add(old_position); cells = snapshot(ws, old_position)
        values = {str(c): value(s, cached_source, row, c) for c in (1, 2, 3)}
        generated=db.execute('SELECT last_values FROM ew_neft_reverse WHERE row_id=?',(rid,)).fetchone()
        generated_pay=json.loads(generated['last_values']).get(str(source_cols['salary'])) if generated and source_cols['salary'] else object()
        reverse_pay=source_cols['salary'] and REVERSE.same_value(s.cell(row,source_cols['salary']).value,generated_pay)
        if source_cols['salary'] and target_cols['salary'] and not reverse_pay:
            c = target_cols['salary']; incoming = value(s, cached_source, row, source_cols['salary'])
            if ws.cell(old_position, c).data_type == 'f':
                salary_note = 'Net Salary formulas preserved; salary amounts are not copied into calculated cells.'
            elif incoming in (None, ''):
                values[str(c)] = None
                salary_note = 'Salary Amount → editable Net Salary.'
            else:
                try:
                    n = Decimal(str(incoming))
                    if not n.is_finite(): raise InvalidOperation()
                    values[str(c)] = float(n) if n != n.to_integral() else int(n)
                    salary_note = 'Salary Amount → editable Net Salary.'
                except (InvalidOperation, ValueError): salary_note = 'Non-numeric Salary Amount was not copied.'
        last = json.loads(member['last_values']) if member else {}
        for key, incoming in values.items():
            c = int(key); current = cells[c - 1].value
            auto=db.execute('SELECT status FROM ew_designations WHERE row_id=?',(rid,)).fetchone()
            if c==3 and incoming in (None,'') and auto and auto['status'] in ('unknown','ambiguous','blank') and current not in (None,''):continue
            if cells[c - 1].data_type == 'f': E.fail(g, 'A mapped employee field contains a formula; it was preserved.')
            allowed = current in (None, '') or current == incoming or (key in last and current == last[key]) or (c in (2,3) and DESIGNATIONS.name_key(current)==DESIGNATIONS.name_key(incoming))
            if not allowed:
                E.fail(g, f'Worksheet {get_column_letter(c)}{old_position} has a manual value. Review it before retrying synchronization.')
            cells[c - 1].value = incoming
            if isinstance(incoming, str): cells[c - 1].data_type = 's'
        output.append((old_position, cells, rid, values))
    # Retain Worksheet-only employees/manual rows, never repurpose them by position.
    for row in sorted(unclaimed - used): output.append((row, snapshot(ws, row), None, None)); used.add(row)
    # Blank spare rows keep existing formulas/styles but not removed employees' inputs.
    for row in sorted(old_positions - used):
        cells = snapshot(ws, row)
        if row in reserved:
            for cell in cells:
                if cell.data_type != 'f': cell.value = None
        output.append((row, cells, None, None))
    mapping = {old: start + i for i, (old, _, _, _) in enumerate(output)}
    records = {old: cells for old, cells, _, _ in output}
    # Columns were modified on copies; the original target/version is never overwritten.
    permute(w, ws, mapping, records)
    for i, (old, cells, rid, values) in enumerate(output):
        dest = start + i
        if rid:
            ids.append(rid)
            db.execute('INSERT INTO ew_neft_members VALUES (?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET position=excluded.position,last_values=excluded.last_values',
                       (rid, b['id'], s.title, dest, json.dumps(values)))
            changed.extend({'sheet': ws.title, 'address': get_column_letter(int(c)) + str(dest)} for c in values)
    for rid in set(members) - set(ids): db.execute('DELETE FROM ew_neft_members WHERE source_id=?', (rid,))
    schema = json.loads(target.get('schema_json') or '{}'); types = schema.get(ws.title, {})
    shifted_types = {}
    for address, kind in types.items():
        col, row = coordinate_from_string(address)
        if row > original_end: row += end - original_end
        shifted_types[col + str(mapping.get(row, row))] = kind
    for row in ws:
        for c in row:
            if not isinstance(c, MergedCell): shifted_types.setdefault(c.coordinate, c.data_type)
    schema[ws.title] = shifted_types
    db.execute('UPDATE ew_books SET schema_json=? WHERE id=?', (json.dumps(schema), target['id']))
    results = E.CALC.Calculator(w).results(); affected = E.CALC.affected(w, changed)
    results = {k: v for k, v in results.items() if k in affected}
    cache_moves = {(ws.title, r): dest for r, dest in mapping.items()}
    cache_moves.update({(ws.title, r): r + end - original_end for r in range(original_end + 1, original_max_row + 1)})
    data = serialize(w, target_data, cache_moves, results)
    # Idempotence: a sync with identical cell data/order creates no duplicate rows/version.
    same = E.read(target_data, g)
    def content(sheet):
        return [[(c.value, c.data_type, str(c._style), str(c.comment), str(c.hyperlink)) for c in row] for row in sheet]
    same_values = all(content(same[sh]) == content(w[sh]) and dict(same[sh].row_dimensions) == dict(w[sh].row_dimensions) for sh in w.sheetnames)
    if not same_values:
        E.write_version(g, target, actor, data, {'neft_sync': b['id'], 'sheet': s.title, 'employees': len(source_rows)})
    db.execute("UPDATE ew_neft_links SET status=?,error='',salary_note=? WHERE book=? AND sheet=?", ('synced' if source_rows else 'empty',salary_note, b['id'], s.title))
    return describe(g, b, s)


def attempt(g, actor, b, s, data, target_id=None):
    db = g['DB']; db.execute('SAVEPOINT neft_target')
    try:
        result = sync(g, actor, b, s, data, target_id)
        db.execute('RELEASE SAVEPOINT neft_target'); return result
    except (g['FlowError'], g['Denied'], ValueError) as error:
        db.execute('ROLLBACK TO SAVEPOINT neft_target'); db.execute('RELEASE SAVEPOINT neft_target')
        # Keep NEFT edits; make the failure explicit and retryable, without partial target writes.
        db.execute("INSERT INTO ew_neft_links(book,sheet,status,error) VALUES (?,?,'error',?) ON CONFLICT(book,sheet) DO UPDATE SET status='error',error=excluded.error", (b['id'], s.title, str(error)))
        return describe(g, b, s)


def after_commit(g, actor, b, data, changes):
    if b['master'] or b.get('format') == 'docx': return None
    # Update target row coordinates after explicit Worksheet structural changes.
    links = list(g['DB'].execute('SELECT book,sheet,target_sheet FROM ew_neft_links WHERE target=?', (b['id'],)))
    for link in links:
        for op in changes.get('rows', []):
            if op.get('sheet') != link['target_sheet']: continue
            at = int(op['row']); params = (link['book'], link['sheet'])
            if op['action'] == 'delete':
                g['DB'].execute('DELETE FROM ew_neft_members WHERE book=? AND sheet=? AND position=?', (*params, at))
            g['DB'].execute('UPDATE ew_neft_members SET position=position+? WHERE book=? AND sheet=? AND position>=?', (1 if op['action'] == 'add' else -1, *params, at if op['action'] == 'add' else at + 1))
    if ew().category(b) == 'worksheet' and 'permissions' not in changes:
        DESIGNATIONS.refresh_sources(g,actor,b,changes)
        w=ew().read(data,g)
        if any(columns(ws) for ws in w):return REVERSE.attempt(g,actor,b,data,changes)
    if ew().category(b) != 'neft' or 'permissions' in changes: return None
    w = ew().read(data, g); result = None
    for s in w:
        if not columns(s, True): continue
        reconcile(g, b, s, changes)
        for edit in changes.get('cells',[]):
            if edit.get('sheet')==s.title and re.fullmatch(r'C[0-9]+',edit.get('address','')):
                g['DB'].execute("INSERT OR REPLACE INTO ew_designations SELECT id,book,sheet,?,?, 'manual' FROM ew_neft_rows WHERE book=? AND sheet=? AND position=? AND active=1",(DESIGNATIONS.name_key(s.cell(s[edit['address']].row,2).value),str(s[edit['address']].value or ''),b['id'],s.title,s[edit['address']].row))
        edits,_=DESIGNATIONS.apply(g,b,s,{})
        if edits:
            data=serialize(w,data)
            ew().write_version(g,b,actor,data,{'designation_lookup':True,'cells':edits})
            b['revision']+=1
            reconcile(g,b,s,{})
        start, end = bounds(s)
        if not any(any(s.cell(r, c).value not in (None, '') for c in (1, 2, 3)) for r in range(start, end + 1)):
            if not g['DB'].execute('SELECT 1 FROM ew_neft_links WHERE book=? AND sheet=?', (b['id'], s.title)).fetchone(): continue
        synced = attempt(g, actor, b, s, data)
        if result is None: result = synced
    return result


def command(g, actor, b, body):
    E = ew(); data = E.data_for(g, b); w = E.read(data, g)
    if b['master'] or E.category(b) != 'neft': E.fail(g, 'Choose a private NEFT document.')
    name = body.get('sheet')
    if name not in w.sheetnames or not columns(w[name], True): E.fail(g, 'Choose a NEFT employee table with S.No, Name and Designation.')
    s = w[name]
    if body.get('target') and body['target'] != 'new':
        target = E.book(g, actor, body['target'], 'edit')
        if target['owner'] != b['owner'] or target['master'] or E.category(target) != 'worksheet':
            raise g['Denied']('Choose a private Worksheet belonging to the NEFT document owner.')
    reconcile(g, b, s, {})
    if body.get('action') == 'sort':
        col, direction = body.get('column'), body.get('direction')
        if type(col) is not int or col not in (0, 1, 2, 3) or direction not in ('asc', 'desc', 'original'):
            E.fail(g, 'Choose S.No, Name or Designation and a valid sorting direction.')
        if direction == 'original': col = 0
        g['DB'].execute('INSERT INTO ew_neft_sort VALUES (?,?,?,?) ON CONFLICT(book,sheet) DO UPDATE SET col=excluded.col,direction=excluded.direction', (b['id'], name, col, direction))
    if body.get('action')=='retry':
        link=ensure_link(g,actor,b,s,body.get('target'))
        target=E.book(g,actor,link['target'],'edit')
        reverse_state=REVERSE.describe(g,target['id'])
        lo,hi=bounds(s)
        has_names=any(str(s.cell(r,2).value or '').strip() for r in range(lo,hi+1))
        state=REVERSE.attempt(g,actor,target,E.data_for(g,target),{'retry':True}) if not has_names or (reverse_state and reverse_state['status']=='error') else attempt(g,actor,b,s,data)
        g['DB'].commit()
        return {'ok':True,'id':b['id'],'revision':g['DB'].execute('SELECT revision FROM ew_books WHERE id=?',(b['id'],)).fetchone()[0],'neft_sync':describe(g,b,s),'worksheet_sync':state}
    if body.get('action')=='designations':
        edits,_=DESIGNATIONS.apply(g,b,s,{},replace=True)
        if edits:
            data=serialize(w,data)
            E.write_version(g,b,actor,data,{'designation_replace':True,'cells':edits})
            b['revision']+=1
            reconcile(g,b,s,{})
    result = attempt(g, actor, b, s, data, body.get('target'))
    if body.get('action')=='designations' and result and result['status']=='synced':
        linked=ensure_link(g,actor,b,s)
        target=E.book(g,actor,linked['target'],'edit')
        REVERSE.attempt(g,actor,target,E.data_for(g,target),{'retry':True})
        result=describe(g,b,s)
    response = E.write_version(g, b, actor, data, {'neft_action': body.get('action', 'sync'), 'sheet': name}) if body.get('action') == 'sort' else {'ok': True, 'id': b['id'], 'revision': b['revision']}
    g['DB'].commit(); response['neft_sync'] = result; return response
