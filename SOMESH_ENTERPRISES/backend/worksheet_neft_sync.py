"""Worksheet-to-NEFT synchronization using the existing row UUID relationship.

Mapped employee fields are versioned atomically. Banking columns never participate
in the mapping. Forward synchronization skips reverse-generated payroll amounts.
"""
import json
import re
import uuid
from decimal import Decimal

SCHEMA='''CREATE TABLE IF NOT EXISTS ew_neft_reverse(
 row_id TEXT PRIMARY KEY,worksheet TEXT,sheet TEXT,last_values TEXT,source_values TEXT);
CREATE TABLE IF NOT EXISTS ew_reverse_status(worksheet TEXT PRIMARY KEY,status TEXT,error TEXT,
 records INTEGER DEFAULT 0,updated INTEGER DEFAULT 0,neft TEXT,sheet TEXT);'''

def same_value(a,b):
    # OOXML/openpyxl round-trips numeric cells at Excel's 15-digit precision.
    # Compare at that boundary so harmless serialization does not look like a
    # manual salary override (or feed a take-home amount back into gross pay).
    if isinstance(a,(int,float,Decimal)) and isinstance(b,(int,float,Decimal)):
        return format(float(a),'.15g')==format(float(b),'.15g')
    return a==b

def modules():
    import excel_workspace as E
    import neft_sync as N
    return E,N

def payable_column(s):
    E,N=modules();info=E.layout(s)
    labels=[N.normalized(' '.join(str(row[i] or '') for row in info['header_rows'])) for i in range(s.max_column)]
    for label in ('takehomesalary','salaryamount','netsalary'):
        found=[i+1 for i,x in enumerate(labels) if x==label]
        if len(found)>1:raise ValueError('Ambiguous salary headers; review the Worksheet mapping.')
        if found:return found[0],label
    return None,'unmapped'

def describe(g,bid):
    row=g['DB'].execute('SELECT * FROM ew_reverse_status WHERE worksheet=?',(bid,)).fetchone()
    return dict(row) if row else None

def ensure_pair(g,actor,b,w):
    E,N=modules();db=g['DB']
    links=[dict(r) for r in db.execute('SELECT * FROM ew_neft_links WHERE target=?',(b['id'],))]
    if links:return links
    sheets=[s for s in w if N.columns(s)]
    if len(sheets)!=1:raise ValueError('Select a Worksheet with one unambiguous employee table.')
    ws=sheets[0];lo,hi=N.bounds(ws)
    if not any(str(ws.cell(r,2).value or '').strip() for r in range(lo,hi+1)):return []
    templates=[t for t in E.template_library(g,b['owner']) if t['category']=='neft' and t['can_edit'] and not t['locked']]
    if len(templates)!=1:raise ValueError('Configure one editable NEFT template for this employee before synchronization.')
    source=E.template_book(g,b['owner'],templates[0]['id'],'edit');data,schema=E.blank_data(g,source);nw=E.read(data,g)
    tables=[s for s in nw if N.columns(s,True)]
    if not tables:raise ValueError('NEFT template needs S.No, Name, Designation and Salary Amount headers.')
    # Existing NEFT documents choose an explicit sheet. A new counterpart starts
    # on the template's first employee table; unrelated workbook tabs stay intact.
    ns=tables[0];neft=E.create(g,actor,'NEFT - '+b['name'],b['owner'],1,source=source['id'])
    db.execute("UPDATE ew_books SET category='neft',origin='blank',schema_json=? WHERE id=?",(json.dumps(schema),neft['id']))
    E.write_version(g,neft,actor,data,{'created_for_worksheet':b['id']})
    db.execute("INSERT INTO ew_neft_links VALUES (?,?,?,?,'pending','','')",(neft['id'],ns.title,b['id'],ws.title))
    return [dict(db.execute('SELECT * FROM ew_neft_links WHERE book=? AND sheet=?',(neft['id'],ns.title)).fetchone())]

def fingerprint(values):
    return tuple(' '.join(str(values.get(str(c)) or '').split()).casefold() for c in (1,2,3))

def sync(g,actor,b,data,changes):
    E,N=modules();db=g['DB'];w=E.read(data,g);E.repair_manual_start(g,b,w)
    links=ensure_pair(g,actor,b,w);total=updated=0;neft_id=sheet_name=None
    for link in links:
        neft=E.book(g,actor,link['book'],'edit')
        if neft['owner']!=b['owner']:raise g['Denied']('Linked workbook owners do not match.')
        raw=E.data_for(g,neft);nw=E.read(raw,g);ns=nw[link['sheet']];ws=w[link['target_sheet']]
        if not N.columns(ws) or not N.columns(ns,True):raise ValueError('Linked employee headers changed. Review the mapping.')
        N.reconcile(g,neft,ns,{})
        registry={r['position']:dict(r) for r in db.execute('SELECT * FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1',(neft['id'],ns.title))}
        members={r['position']:dict(r) for r in db.execute('SELECT * FROM ew_neft_members WHERE book=? AND sheet=?',(neft['id'],ns.title))}
        reverse={r['row_id']:dict(r) for r in db.execute('SELECT * FROM ew_neft_reverse WHERE worksheet=?',(b['id'],))}
        pay,label=payable_column(ws);salary=N.columns(ns,True)['salary'];calc=E.CALC.Calculator(w)
        lo,hi=N.bounds(ws);used=set();edits=[]
        for r in range(lo,hi+1):
            name=ws.cell(r,2).value
            if not str(name or '').strip():continue
            if ws.cell(r,2).data_type=='f' or ws.cell(r,3).data_type=='f':raise ValueError('Employee identity formulas require manual mapping review.')
            source={str(c):ws.cell(r,c).value for c in (1,2,3)};incoming=dict(source)
            if pay and salary:
                pc=ws.cell(r,pay)
                if pc.data_type=='f':
                    value=calc.cell(ws.title,pc.coordinate)
                    if value is E.CALC.Pending:raise ValueError('Salary calculation is pending at '+pc.coordinate+'. Correct its inputs before retrying.')
                    if isinstance(value,Decimal):value=int(value) if value==value.to_integral() else float(value)
                else:value=pc.value
                if value is not None:incoming[str(salary)]=value
            member=members.get(r);rid=member['source_id'] if member else None
            # Whole-file replacements cannot safely inherit identities by position.
            if changes.get('import') or changes.get('restored_from'):
                matches=[rid for rid,v in reverse.items() if fingerprint(json.loads(v['source_values']))==fingerprint(source)]
                if len(matches)>1:raise ValueError('Mapping conflict: duplicate identities in replacement Worksheet.')
                rid=matches[0] if matches else None
            position=next((p for p,v in registry.items() if v['id']==rid),None)
            if position is None:
                matches=[p for p,v in registry.items() if v['id'] not in used and fingerprint({str(c):ns.cell(p,c).value for c in (1,2,3)})==fingerprint(source)]
                if len(matches)>1:raise ValueError('Mapping conflict: duplicate NEFT identities; banking data was retained.')
                if matches:position=matches[0];rid=registry[position]['id']
            if position is None:
                free=[p for p,v in registry.items() if v['id'] not in used and v['id'] not in reverse and not db.execute('SELECT 1 FROM ew_neft_members WHERE source_id=?',(v['id'],)).fetchone() and all(c.value in (None,'') or c.data_type=='f' for c in ns[p])]
                if free:position=min(free);rid=registry[position]['id']
                else:
                    position=N.bounds(ns)[1]+1;E.change_row(g,nw,ns,{'action':'add','row':position},neft,g['is_admin'](actor));N.reconcile(g,neft,ns,{})
                    registry={rr['position']:dict(rr) for rr in db.execute('SELECT * FROM ew_neft_rows WHERE book=? AND sheet=? AND active=1',(neft['id'],ns.title))};rid=registry[position]['id']
            if rid in used:raise ValueError('Mapping conflict: multiple Worksheet rows target one employee identity.')
            used.add(rid);old=reverse.get(rid);last=json.loads(old['last_values']) if old else {}
            legacy=next((m for m in members.values() if m['source_id']==rid),None)
            baseline=json.loads(legacy['last_values']) if legacy else {}
            row_changed=False
            for key,value in incoming.items():
                c=ns.cell(position,int(key));current=c.value
                if c.data_type=='f':raise ValueError('Mapped NEFT field '+c.coordinate+' contains a formula; it was preserved.')
                ownership=db.execute('SELECT status FROM ew_designations WHERE row_id=?',(rid,)).fetchone()
                if key=='3' and ownership and ownership['status']=='manual' and current!=value:raise ValueError('Mapping conflict at NEFT '+c.coordinate+': manual designation preserved. Use Worksheet designations explicitly to replace it.')
                # The Worksheet is authoritative for already linked employee
                # fields. Conflicting independently saved NEFT fields require review.
                allowed=current in (None,'') or same_value(current,value) or (key in last and same_value(current,last[key])) or (legacy is not None and key in ('1','2','3') and current==baseline.get(key))
                if not allowed and legacy is not None and not old and salary and key==str(salary):
                    gross=N.columns(ws)['salary']
                    # Adopt an existing forward-only pair only when the NEFT
                    # amount is unchanged from its last saved Worksheet baseline.
                    # A separately changed bank-payment amount remains a conflict.
                    if gross and str(gross) in baseline:allowed=same_value(current,baseline[str(gross)])
                if not allowed and key in ('1','2','3'):allowed=N.DESIGNATIONS.name_key(current)==N.DESIGNATIONS.name_key(value)
                if not allowed:raise ValueError('Mapping conflict at NEFT '+c.coordinate+'. Review the independently edited value; banking fields were retained.')
                if not same_value(current,value):
                    c.value=value
                    if isinstance(value,str):c.data_type='s'
                    edits.append({'sheet':ns.title,'address':c.coordinate});row_changed=True
            updated+=int(row_changed);total+=1
            db.execute('INSERT OR REPLACE INTO ew_neft_members VALUES (?,?,?,?,?)',(rid,neft['id'],ns.title,r,json.dumps(source)))
            db.execute('INSERT OR REPLACE INTO ew_neft_reverse VALUES (?,?,?,?,?)',(rid,b['id'],ws.title,json.dumps(incoming),json.dumps(source)))
            ownership=db.execute('SELECT status FROM ew_designations WHERE row_id=?',(rid,)).fetchone()
            if not ownership or ownership['status']!='manual':db.execute("INSERT OR REPLACE INTO ew_designations VALUES (?,?,?,?,?,'automatic')",(rid,neft['id'],ns.title,N.DESIGNATIONS.name_key(name),str(source['3'] or '')))
            db.execute('INSERT OR REPLACE INTO ew_designation_sources VALUES (?,?)',(rid,str(source['3'] or '')))
        # Removing an employee clears only generated mapped values. Bank/IFSC,
        # remarks and formulas remain attached to the old UUID in the versioned row.
        for rid,old in reverse.items():
            if rid in used:continue
            position=next((p for p,v in registry.items() if v['id']==rid),None)
            if position is None:continue
            last=json.loads(old['last_values'])
            for key,value in last.items():
                c=ns.cell(position,int(key))
                if c.value not in (None,'') and not same_value(c.value,value):raise ValueError('Mapping conflict in removed employee '+c.coordinate+'. No banking data was discarded.')
                if c.value not in (None,''):
                    c.value=None;edits.append({'sheet':ns.title,'address':c.coordinate})
            db.execute('DELETE FROM ew_neft_members WHERE source_id=?',(rid,))
            db.execute('DELETE FROM ew_designations WHERE row_id=?',(rid,))
        if edits:
            affected=E.CALC.affected(nw,edits);result=E.CALC.Calculator(nw).results(affected)
            output=N.serialize(nw,raw,calculations=result)
            E.write_version(g,neft,actor,output,{'worksheet_sync':b['id'],'cells':edits,'records':total})
        N.reconcile(g,neft,ns,{})
        state='synced' if total else 'empty';note='Worksheet '+label+' -> NEFT Salary Amount; bank fields preserved.'
        db.execute('UPDATE ew_neft_links SET status=?,error=?,salary_note=? WHERE book=? AND sheet=?',(state,'',note,neft['id'],ns.title))
        neft_id=neft['id'];sheet_name=ns.title
    return {'status':'synced' if total else 'empty','error':'','records':total,'updated':updated,'neft':neft_id,'sheet':sheet_name}

def attempt(g,actor,b,data,changes=None):
    db=g['DB'];db.execute('SAVEPOINT worksheet_neft')
    try:
        state=sync(g,actor,b,data,changes or {});db.execute('RELEASE SAVEPOINT worksheet_neft')
    except (g['FlowError'],g['Denied'],ValueError) as error:
        db.execute('ROLLBACK TO SAVEPOINT worksheet_neft');db.execute('RELEASE SAVEPOINT worksheet_neft')
        state={'status':'error','error':str(error),'records':0,'updated':0,'neft':None,'sheet':None}
        db.execute("UPDATE ew_neft_links SET status='error',error=? WHERE target=?",(str(error),b['id']))
    db.execute('INSERT OR REPLACE INTO ew_reverse_status VALUES (?,?,?,?,?,?,?)',(b['id'],state['status'],state['error'],state['records'],state['updated'],state['neft'],state['sheet']))
    return state
