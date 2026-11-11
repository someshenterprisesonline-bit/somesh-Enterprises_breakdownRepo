import base64
import io
import json
import os
import unittest
import threading
from pathlib import Path
from urllib.parse import urlencode

import openpyxl
from openpyxl.styles import PatternFill
from support import AppFixture, BACKEND, PROJECT
from test_excel_workspace import add_employees


def neft_file(count=10):
    w = openpyxl.Workbook(); s = w.active; s.title = 'NEFT'
    s.append(['S.No', 'Name', 'Designation', 'Bank', 'Account Number', 'Branch', 'IFSC Code', 'Salary Amount', 'Remarks', 'Existing formula'])
    for i in range(count):
        serial = [10, 2, 1][i] if i < 3 else i + 1
        s.append([serial, f'Employee {count-i:03}', ['Guard','Cleaner','Supervisor'][i % 3], 'Bank '+str(i), '0000'+str(i), 'Branch '+str(i), 'IFSC'+str(i), 1000+i, 'Remark '+str(i), f'=H{i+2}*2'])
        s.cell(i+2, 5).number_format = '@'; s.cell(i+2, 2).fill = PatternFill('solid', fgColor='DDEEFF')
    other = w.create_sheet('Reference'); other['A1'] = 'Keep this sheet'; other['B1'] = '=NEFT!H2'
    out = io.BytesIO(); w.save(out); return out.getvalue()


def worksheet_file(count=10, salary_formula=False):
    w = openpyxl.Workbook(); s = w.active; s.title = 'Worksheet'
    s.append(['S.No','Name of the Employees','Designation','Net Salary','Manual allowance','Existing calculation','Remarks'])
    for i in range(count):
        row = i+2
        s.append([i+1,'Template person','Guard', f'=E{row}*2' if salary_formula else 1, 1, f'=D{row}+E{row}', 'Historical input'])
        s.cell(row, 2).fill = PatternFill('solid', fgColor='DDFFEE')
    other=w.create_sheet('Other'); other['A1']='Preserved'; other['B1']='=SUM(Worksheet!D2:D11)'
    out=io.BytesIO(); w.save(out); return out.getvalue()


class NeftSyncTests(unittest.TestCase):
    def setUp(self):
        self.app=AppFixture(); add_employees(self.app); self.admin=self.app.login(); self.user=self.app.login('Nandha')
        self.master_neft=self.upload(neft_file(), 'neft', master=True)
        self.master_work=self.upload(worksheet_file(), 'worksheet', master=True)

    def tearDown(self): self.app.close()

    def post(self, action, data, token=None): return self.app.request('/api/excel/'+action, data, token or self.user)

    def upload(self, data, category, master=False, token=None):
        token=token or (self.admin if master else self.user)
        status,p=self.post('preview', {'name':category+'.xlsx','data':base64.b64encode(data).decode()}, token); self.assertEqual(status,200,p)
        status,b=self.post('import', {'preview':p['preview'],'completed':True,'category':category,'master':master,'slot':1 if category=='neft' else 2},token); self.assertEqual(status,200,b)
        return b['id']

    def meta(self, bid, token=None):
        status,data=self.app.request('/api/excel/metadata?id='+bid,token=token or self.user);self.assertEqual(status,200,data);return data

    def grid(self,bid,sheet='NEFT',**query):
        status,data=self.app.request('/api/excel/sheet?'+urlencode(dict(id=bid,sheet=sheet,limit=100,**query)),token=self.user);self.assertEqual(status,200,data);return data

    def save(self,bid,changes=None,rows=None):
        return self.post('save',dict(id=bid,revision=self.meta(bid)['book']['revision'],changes=changes or [],rows=rows or []))

    def sort(self,bid,column=0,direction='original'):
        return self.post('neft',dict(id=bid,revision=self.meta(bid)['book']['revision'],sheet='NEFT',action='sort',column=column,direction=direction))

    def pair(self,bid):
        info=self.grid(bid)['neft'];self.assertEqual(info['status'],'synced',info);return info['target']

    def book(self,bid,**query):
        status,data=self.app.request('/api/excel/download?'+urlencode(dict(id=bid,**query)),token=self.user,binary=True);self.assertEqual(status,200,data);return openpyxl.load_workbook(io.BytesIO(data))

    def test_manual_entry_sort_restore_and_preserve_employee_fields(self):
        status,b=self.post('blank',{'id':self.master_neft});self.assertEqual(status,200,b);bid=b['id']
        changes=[]
        for i in range(10):
            for c,v in [('A',str([10,2,1][i] if i<3 else i+1)),('B',f'Person {10-i:03}'),('C',['Guard','Cleaner'][i%2]),('E','000'+str(i)),('H',str(1000+i)),('I','Remark '+str(i))]:
                changes.append(dict(sheet='NEFT',address=c+str(i+2),value=v,type='text' if c in ('B','C','E','I') else 'number'))
        status,result=self.save(bid,changes);self.assertEqual(status,200,result);target=self.pair(bid)
        original=self.book(bid);initial=[tuple(c.value for c in row) for row in original['NEFT'].iter_rows(min_row=2)]
        status,result=self.save(target,[dict(sheet='Worksheet',address='E2',value='777',type='number'),dict(sheet='Worksheet',address='G2',value='Keep payroll note',type='text')]);self.assertEqual(status,200,result)
        for col,direction in [(2,'asc'),(2,'desc'),(3,'asc'),(3,'desc'),(1,'asc'),(1,'desc'),(0,'original')]:
            status,result=self.sort(bid,col,direction);self.assertEqual(status,200,result);self.assertEqual(result['neft_sync']['status'],'synced',result)
            neft=self.book(bid);work=self.book(target);nr=list(neft['NEFT'].iter_rows(min_row=2));wr=list(work['Worksheet'].iter_rows(min_row=2))
            self.assertEqual([[c.value for c in r[:3]] for r in nr],[[c.value for c in r[:3]] for r in wr])
            for r in nr:
                before=next(x for x in initial if x[1]==r[1].value);self.assertEqual([c.value for c in r[:9]],list(before[:9]));self.assertEqual(r[9].value,f'=H{r[0].row}*2')
            payroll=next(r for r in wr if r[1].value=='Person 010');self.assertEqual(payroll[4].value,777);self.assertEqual(payroll[6].value,'Keep payroll note');self.assertEqual(payroll[5].value,f'=D{payroll[0].row}+E{payroll[0].row}')
            if col==1:self.assertEqual([r[0].value for r in nr],sorted([x[0] for x in initial],reverse=direction=='desc'))
            if col in (2,3):self.assertEqual([r[col-1].value for r in nr],sorted([x[col-1] for x in initial],key=str.casefold,reverse=direction=='desc'))
        self.assertEqual([[c.value for c in r[:9]] for r in nr],[list(x[:9]) for x in initial])

    def test_upload_100_immutable_original_versions_idempotence_and_isolation(self):
        raw=neft_file(100);bid=self.upload(raw,'neft');target=self.pair(bid)
        self.assertEqual(len(self.grid(target,'Worksheet')['rows']),100)
        status,version=self.app.request('/api/excel/download?'+urlencode(dict(id=bid,version=1)),token=self.user,binary=True);self.assertEqual(status,200);self.assertEqual(version,raw)
        self.assertEqual(self.app.g['q']('SELECT COUNT(*) n FROM ew_neft_members WHERE book=?',(bid,))[0]['n'],100)
        rev=self.meta(target)['book']['revision']
        for _ in range(3):
            status,result=self.post('neft',dict(id=bid,revision=self.meta(bid)['book']['revision'],sheet='NEFT',action='sync'));self.assertEqual(status,200,result)
        self.assertEqual(self.meta(target)['book']['revision'],rev)
        self.assertEqual(self.app.g['q']('SELECT COUNT(*) n FROM ew_neft_members WHERE book=?',(bid,))[0]['n'],100)
        second=self.upload(raw,'neft');self.assertNotEqual(self.pair(second),target)
        foreign=self.upload(raw,'neft',token=self.app.login('Rupashri'))
        self.assertEqual(self.app.request('/api/excel/download?id='+foreign,token=self.user)[0],403)
        self.assertEqual(self.post('neft',dict(id=foreign,revision=1,sheet='NEFT',action='sync'))[0],403)
        self.assertEqual(self.book(target)['Other']['A1'].value,'Preserved')

    def test_edit_add_delete_ids_salary_and_manual_conflict(self):
        bid=self.upload(neft_file(),'neft');target=self.pair(bid);rid=self.grid(bid)['rows'][0]['row_id']
        status,result=self.save(bid,[dict(sheet='NEFT',address='B2',value='Renamed employee',type='text'),dict(sheet='NEFT',address='H2',value='9123',type='number')]);self.assertEqual(status,200,result)
        self.assertEqual(self.grid(bid)['rows'][0]['row_id'],rid);work=self.book(target)['Worksheet'];self.assertEqual(work['B2'].value,'Renamed employee');self.assertEqual(work['D2'].value,9123)
        status,result=self.save(bid,rows=[dict(sheet='NEFT',action='delete',row=2)]);self.assertEqual(status,200,result);self.assertNotIn('Renamed employee',[r[1].value for r in self.book(target)['Worksheet'].iter_rows(min_row=2)])
        status,result=self.save(bid,rows=[dict(sheet='NEFT',action='add',row=2)]);self.assertEqual(status,200,result)
        self.assertEqual(self.save(bid,[dict(sheet='NEFT',address='B2',value='New employee',type='text'),dict(sheet='NEFT',address='C2',value='Guard',type='text')])[0],200)
        row=next(r for r in self.book(target)['Worksheet'].iter_rows(min_row=2) if r[1].value=='New employee')
        self.assertEqual(self.save(target,[dict(sheet='Worksheet',address=row[1].coordinate,value='Manual override',type='text')])[0],200)
        before=self.app.g['q']('SELECT * FROM ew_versions WHERE book=?',(target,))
        status,result=self.save(bid,[dict(sheet='NEFT',address='C2',value='Supervisor',type='text')]);self.assertEqual(status,200,result);self.assertEqual(result['neft_sync']['status'],'synced')
        self.assertIn('Manual override',[r[1].value for r in self.book(bid)['NEFT'].iter_rows(min_row=2)])
        self.assertNotEqual(self.app.g['q']('SELECT * FROM ew_versions WHERE book=?',(target,)),before)

    def test_calculated_net_salary_is_never_overwritten(self):
        self.master_work=self.upload(worksheet_file(salary_formula=True),'worksheet',master=True)
        bid=self.upload(neft_file(),'neft');target=self.pair(bid);w=self.book(target)
        for row in range(2,12):self.assertEqual(w['Worksheet'].cell(row,4).value,f'=E{row}*2')
        self.assertIn('formulas preserved',self.grid(bid)['neft']['salary_note'])

    def test_link_completed_worksheet_preserves_manual_rows_without_new_formulas(self):
        bid=self.upload(neft_file(),'neft');target=self.upload(worksheet_file(2),'worksheet')
        original=self.book(target);formula_count=sum(c.data_type=='f' for s in original for row in s for c in row)
        status,result=self.post('neft',dict(id=bid,revision=self.meta(bid)['book']['revision'],sheet='NEFT',action='sync',target=target))
        self.assertEqual(status,200,result);self.assertEqual(result['neft_sync']['status'],'synced',result)
        saved=self.book(target);rows=list(saved['Worksheet'].iter_rows(min_row=2))
        self.assertEqual([r[1].value for r in rows[:10]],[f'Employee {i:03}' for i in range(10,0,-1)])
        self.assertEqual(sum(c.data_type=='f' for s in saved for row in s for c in row),formula_count)
        self.assertEqual([r[1].value for r in rows[10:]],['Template person','Template person'])
        self.assertEqual([r[6].value for r in rows[10:]],['Historical input','Historical input'])
        self.assertEqual([r[4].value for r in rows[10:]],[1,1])

    def test_restart_persists_sort_pair_ids_and_salary_clear(self):
        bid=self.upload(neft_file(),'neft');target=self.pair(bid);rid=self.grid(bid)['rows'][0]['row_id']
        status,result=self.save(bid,[dict(sheet='NEFT',address='H2',value='',type='number')]);self.assertEqual(status,200,result)
        self.assertIsNone(self.book(target)['Worksheet']['D2'].value)
        self.assertEqual(self.sort(bid,2,'asc')[0],200)
        self.app.g['EM'].sync(self.app.g)  # Persist fixture-only profiles before a genuine restart.
        self.app.server.shutdown();self.app.server.server_close();self.app.thread.join();self.app.g['DB'].close()
        g={'__file__':str(self.app.root/'backend/app.py'),'__name__':'somesh_test_app'}
        exec(compile((BACKEND/'app.py').read_text(encoding='utf-8'),g['__file__'],'exec'),g)
        g['FRONTEND']=str(PROJECT/'frontend');g['load_adhoc']();self.app.g=g
        self.app.server=g['ThreadingHTTPServer'](('127.0.0.1',0),g['H']);self.app.server.daemon_threads=True
        self.app.thread=threading.Thread(target=lambda:self.app.server.serve_forever(poll_interval=.02),daemon=True);self.app.thread.start()
        self.app.origin=f'http://127.0.0.1:{self.app.server.server_port}';self.user=self.app.login('Nandha')
        grid=self.grid(bid);self.assertEqual(grid['neft']['column'],2);self.assertEqual(grid['neft']['direction'],'asc');self.assertEqual(self.pair(bid),target)
        self.assertEqual(next(r for r in grid['rows'] if r['number']==2)['row_id'],rid)
        self.assertEqual(self.book(target)['Worksheet']['B2'].value,'Employee 001')

    @unittest.skipUnless(os.environ.get('EXCEL_REFERENCE_ROOT'),'Private reference templates required')
    def test_real_neft_row_changes_keep_conditional_formatting_and_original(self):
        raw=(Path(os.environ['EXCEL_REFERENCE_ROOT'])/'538-OMCL-Open University -Sept-26(03-10-2026).xlsx').read_bytes()
        bid=self.upload(raw,'neft');sheet='Office Copy';before=self.book(bid);rules=len(before[sheet].conditional_formatting)
        status,result=self.save(bid,rows=[dict(sheet=sheet,action='add',row=4)]);self.assertEqual(status,200,result)
        added=self.book(bid);self.assertEqual(len(added[sheet].conditional_formatting),rules)
        self.assertNotEqual(added[sheet]['B3'].value,None)
        status,result=self.save(bid,rows=[dict(sheet=sheet,action='delete',row=4)]);self.assertEqual(status,200,result)
        after=self.book(bid);self.assertEqual(len(after[sheet].conditional_formatting),rules)
        self.assertEqual([[c.value for c in row] for row in before[sheet]],[[c.value for c in row] for row in after[sheet]])
        status,version=self.app.request('/api/excel/download?'+urlencode(dict(id=bid,version=1)),token=self.user,binary=True);self.assertEqual(status,200);self.assertEqual(version,raw)

    def test_locked_worksheet_failure_is_atomic_retry_and_owner_checks(self):
        bid=self.upload(neft_file(),'neft');target=self.pair(bid)
        status,r=self.post('permissions',dict(id=target,revision=self.meta(target)['book']['revision'],locked=True),self.admin);self.assertEqual(status,200,r)
        before=self.app.g['q']('SELECT * FROM ew_versions WHERE book=?',(target,))
        status,r=self.save(bid,[dict(sheet='NEFT',address='B2',value='Saved while locked',type='text')]);self.assertEqual(status,200,r);self.assertEqual(r['neft_sync']['status'],'error')
        self.assertEqual(self.app.g['q']('SELECT * FROM ew_versions WHERE book=?',(target,)),before)
        self.assertEqual(self.book(bid)['NEFT']['B2'].value,'Saved while locked')
        self.post('permissions',dict(id=target,revision=self.meta(target)['book']['revision'],locked=False),self.admin)
        status,r=self.post('neft',dict(id=bid,revision=self.meta(bid)['book']['revision'],sheet='NEFT',action='sync'));self.assertEqual(status,200,r);self.assertEqual(r['neft_sync']['status'],'synced')
        other=self.upload(worksheet_file(),'worksheet',token=self.app.login('Rupashri'))
        self.assertEqual(self.post('neft',dict(id=bid,revision=self.meta(bid)['book']['revision'],sheet='NEFT',action='sync',target=other),self.admin)[0],403)

    @unittest.skipUnless(os.environ.get('EXCEL_REFERENCE_ROOT'),'Private reference templates required')
    def test_real_worksheet_100_rows_headers_formulas_images_and_salary_guard(self):
        raw=(Path(os.environ['EXCEL_REFERENCE_ROOT'])/'Oct-26-OMCL - TNOU.xlsx').read_bytes()
        self.master_work=self.upload(raw,'worksheet',master=True)
        original=openpyxl.load_workbook(io.BytesIO(raw));header=[[c.value for c in row] for row in original['TNOU'].iter_rows(min_row=4,max_row=6)]
        bid=self.upload(neft_file(100),'neft');target=self.pair(bid);before=self.book(target);formula_count=sum(c.data_type=='f' for ws in before for row in ws for c in row);status,result=self.sort(bid,2,'asc');self.assertEqual(status,200,result);self.assertEqual(result['neft_sync']['status'],'synced',result);target_book=self.book(target)
        self.assertEqual(target_book.sheetnames,original.sheetnames)
        self.assertEqual([[c.value for c in row] for row in target_book['TNOU'].iter_rows(min_row=4,max_row=6)],header)
        self.assertEqual([target_book['TNOU'].cell(r,2).value for r in range(7,107)],[f'Employee {i:03}' for i in range(1,101)])
        self.assertIn('Salary Amount',self.grid(bid)['neft']['salary_note'])
        self.assertEqual(sum(c.data_type=='f' for ws in target_book for row in ws for c in row),formula_count)
        self.assertEqual(len(target_book['In']._images),len(original['In']._images))
        self.assertIn('A107:C107',{str(m) for m in target_book['TNOU'].merged_cells.ranges})
