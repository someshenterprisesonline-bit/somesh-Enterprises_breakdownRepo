"""Same-owner Worksheet designation lookup; UUID ownership protects manual NEFT values."""
import json
import re

SCHEMA = '''CREATE TABLE IF NOT EXISTS ew_designations(
 row_id TEXT PRIMARY KEY, book TEXT, sheet TEXT, name TEXT, value TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS ew_designation_sources(source_id TEXT PRIMARY KEY,value TEXT);'''

def name_key(value):
    return ' '.join(str(value or '').split()).casefold()

def candidates(g, b, sheet):
    import excel_workspace as E
    import neft_sync as N
    link=g['DB'].execute('SELECT target,target_sheet FROM ew_neft_links WHERE book=? AND sheet=?',(b['id'],sheet)).fetchone()
    output=[]
    for row in g['DB'].execute("SELECT * FROM ew_books WHERE owner=? AND master=0 AND category IN ('worksheet','') AND can_view=1",(b['owner'],)).fetchall():
        book=dict(row)
        if E.category(book)!='worksheet':continue
        w=E.read(E.data_for(g,book),g)
        for s in w:
            if not N.columns(s):continue
            lo,hi=N.bounds(s)
            mirrors={m['position'] for m in g['DB'].execute("SELECT m.position FROM ew_neft_members m JOIN ew_neft_links l ON l.book=m.book AND l.sheet=m.sheet JOIN ew_designations d ON d.row_id=m.source_id LEFT JOIN ew_designation_sources o ON o.source_id=m.source_id WHERE l.target=? AND l.target_sheet=? AND d.status!='manual' AND o.source_id IS NULL",(book['id'],s.title))}
            for r in range(lo,hi+1):
                if r in mirrors:continue  # Generated mirrors are not independent lookup evidence.
                n=s.cell(r,2);d=s.cell(r,3)
                if n.data_type=='f' or d.data_type=='f':continue
                key=name_key(n.value)
                if key:output.append((key,str(d.value or '').strip(), bool(link and row['id']==link['target'] and s.title==link['target_sheet']),book['id'],(s.title,r)))
    return output

def apply(g, b, s, changes, replace=False):
    import neft_sync as N
    db=g['DB'];source=candidates(g,b,s.title);changed=[];notes=[]
    edited={x['address'] for x in changes.get('cells',[]) if x.get('sheet')==s.title}
    rows=db.execute('SELECT id,position FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1',(b['id'],s.title)).fetchall()
    for row in rows:
        rid,position=row['id'],row['position'];cell=s.cell(position,3);name=name_key(s.cell(position,2).value)
        old=db.execute('SELECT * FROM ew_designations WHERE row_id=?',(rid,)).fetchone()
        if old and old['status']=='manual' and str(cell.value or '')==old['value'] and not replace:continue
        owned=bool(old and old['status']=='automatic' and str(cell.value or '')==str(old['value'] or ''))
        if cell.coordinate in edited and not replace:
            db.execute('DELETE FROM ew_designations WHERE row_id=?',(rid,));continue
        if cell.data_type=='f' or (cell.value not in (None,'') and not owned and not replace):continue
        matches=[x for x in source if x[0]==name]
        bound=db.execute('SELECT l.target,l.target_sheet,m.position FROM ew_neft_members m JOIN ew_neft_links l ON l.book=m.book AND l.sheet=m.sheet JOIN ew_neft_reverse v ON v.row_id=m.source_id WHERE m.source_id=?',(rid,)).fetchone()
        exact=[x for x in matches if bound and x[3]==bound['target'] and x[4]==(bound['target_sheet'],bound['position'])]
        linked=[x for x in matches if x[2]]
        if exact:matches=exact
        elif linked:matches=linked
        values={x[1] for x in matches if x[1]}
        blank=any(not x[1] for x in matches)
        status='automatic' if len(values)==1 and not blank else 'ambiguous' if len(values)>1 or (values and blank) else 'blank' if matches else 'unknown' if name else 'empty'
        value=next(iter(values)) if status=='automatic' else ''
        if owned or cell.value in (None,'') or (replace and status=='automatic'):
            if str(cell.value or '')!=value:
                cell.value=value or None
                if value:cell.data_type='s'
                changed.append({'sheet':s.title,'address':cell.coordinate})
        db.execute('INSERT INTO ew_designations VALUES (?,?,?,?,?,?) ON CONFLICT(row_id) DO UPDATE SET name=excluded.name,value=excluded.value,status=excluded.status',(rid,b['id'],s.title,name,value,status))
        if status in ('ambiguous','unknown','blank'):notes.append({'row':position,'status':status,'message':{'ambiguous':'Conflicting Worksheet designations; select a designation manually.','unknown':'Employee name not found in Worksheet.','blank':'Worksheet designation is blank.'}[status]})
    return changed,notes

def refresh_sources(g,actor,worksheet,changes=None):
    """Only generated designation cells flow back. Never invoke the forward-sync hook."""
    import excel_workspace as E
    import neft_sync as N
    db=g['DB']
    source=E.read(E.data_for(g,worksheet),g)
    for change in (changes or {}).get('cells',[]):
        if re.fullmatch(r'C[0-9]+',change.get('address','')) and change.get('sheet') in source.sheetnames:
            cell=source[change['sheet']][change['address']]
            for member in db.execute('SELECT m.source_id FROM ew_neft_members m JOIN ew_neft_links l ON l.book=m.book AND l.sheet=m.sheet WHERE l.target=? AND l.target_sheet=? AND m.position=?',(worksheet['id'],change['sheet'],cell.row)).fetchall():
                db.execute('INSERT OR REPLACE INTO ew_designation_sources VALUES (?,?)',(member['source_id'],str(cell.value or '')))
    links=db.execute('SELECT book,sheet FROM ew_neft_links WHERE target=?',(worksheet['id'],)).fetchall()
    # Also refresh unlinked lookups derived from other same-owner worksheets.
    source_ids={r['book'] for r in links}
    source_ids.update(r['book'] for r in db.execute("SELECT DISTINCT d.book FROM ew_designations d JOIN ew_books b ON b.id=d.book WHERE b.owner=?",(worksheet['owner'],)))
    linked_ids={r['book'] for r in links}
    for bid in source_ids:
        if bid in linked_ids:continue  # Full reverse sync updates this pair atomically.
        b=E.book(g,actor,bid)
        if b['owner']!=worksheet['owner'] or b['locked'] or not b['can_edit']:continue
        raw=E.data_for(g,b);w=E.read(raw,g);changed=[]
        for s in w:
            if not N.columns(s,True):continue
            edits,_=apply(g,b,s,{});changed.extend(edits)
            for edit in edits:
                row=s[edit['address']].row
                member=db.execute('SELECT m.source_id,m.last_values FROM ew_neft_members m JOIN ew_neft_rows r ON r.id=m.source_id WHERE r.book=? AND r.sheet=? AND r.position=?',(bid,s.title,row)).fetchone()
                if member:
                    values=json.loads(member['last_values']);values['3']=s.cell(row,3).value
                    db.execute('UPDATE ew_neft_members SET last_values=? WHERE source_id=?',(json.dumps(values),member['source_id']))
            if edits:N.reconcile(g,b,s,{})
        if changed:E.write_version(g,b,actor,N.serialize(w,raw),{'designation_sync':worksheet['id'],'cells':changed})
