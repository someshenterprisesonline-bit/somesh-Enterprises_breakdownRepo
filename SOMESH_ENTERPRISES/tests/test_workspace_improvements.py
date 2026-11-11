"""Designation ownership, ambiguity and first-row mapping with isolated synthetic data."""
import io
import json
import unittest
import openpyxl
import test_neft_sync as N
from test_neft_sync import worksheet_file
from test_formula_engine import template,payload
import excel_workspace as E
import excel_calculation as C

class DesignationTests(unittest.TestCase):
    setUp=N.NeftSyncTests.setUp
    tearDown=N.NeftSyncTests.tearDown
    post=N.NeftSyncTests.post
    upload=N.NeftSyncTests.upload
    meta=N.NeftSyncTests.meta
    grid=N.NeftSyncTests.grid
    save=N.NeftSyncTests.save
    book=N.NeftSyncTests.book
    pair=N.NeftSyncTests.pair
    sort=N.NeftSyncTests.sort

    def prepare(self,people):
        w=openpyxl.load_workbook(io.BytesIO(worksheet_file()))
        for row in w['Worksheet'].iter_rows(min_row=2):
            for c in row:
                if c.data_type!='f':c.value=None
        for i,(name,designation) in enumerate(people,2):
            w['Worksheet'].cell(i,1,i-1);w['Worksheet'].cell(i,2,name);w['Worksheet'].cell(i,3,designation)
        target=self.upload(payload(w),'worksheet')
        status,b=self.post('blank',{'id':self.master_neft});self.assertEqual(status,200,b)
        bid=b['id']
        status,result=self.post('neft',{'id':bid,'revision':1,'sheet':'NEFT','action':'sync','target':target});self.assertEqual(status,200,result)
        return bid,target

    def enter(self,bid,name,designation=None):
        changes=[{'sheet':'NEFT','address':'A2','value':'1','type':'number'},{'sheet':'NEFT','address':'B2','value':name,'type':'text'}]
        if designation is not None:changes.append({'sheet':'NEFT','address':'C2','value':designation,'type':'text'})
        status,result=self.save(bid,changes);self.assertEqual(status,200,result);return result

    def test_normalized_lookup_update_clear_and_refresh(self):
        bid,target=self.prepare([(' Ramesh  Kumar ','Data Entry Operator')])
        result=self.enter(bid,'  rAMESH   kumar ')
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Data Entry Operator')
        self.assertEqual(result['revision'],self.meta(bid)['book']['revision'])
        w=self.book(target);row=next(c.row for row in w['Worksheet'] for c in row if c.column==2 and c.value and str(c.value).strip().casefold().startswith('ramesh'))
        status,r=self.save(target,[{'sheet':'Worksheet','address':'C'+str(row),'value':'Accountant','type':'text'}]);self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Accountant')
        status,r=self.save(bid,[{'sheet':'NEFT','address':'B2','value':'','type':'text'}]);self.assertEqual(status,200,r)
        self.assertIsNone(self.book(bid)['NEFT']['C2'].value)

    def test_unknown_duplicate_blank_and_manual_values(self):
        for people,name,status in [([('Kumar','Guard'),(' kumar ','Clerk')],'KUMAR','ambiguous'),([('Priya',None)],'Priya','blank'),([('Ramesh','DEO')],'Unknown','unknown')]:
            with self.subTest(status=status):
                bid,target=self.prepare(people);self.enter(bid,name)
                self.assertIsNone(self.book(bid)['NEFT']['C2'].value)
                self.assertIn(status,[n['status'] for n in self.grid(bid)['neft']['designation_notes']])
        bid,target=self.prepare([('Ramesh','DEO')]);self.enter(bid,'Ramesh','Manual designation')
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Manual designation')
        self.enter(bid,'Unknown');self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Manual designation')
        self.enter(bid,'');self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Manual designation')

    def test_name_change_sort_and_export_preserve_designation(self):
        bid,target=self.prepare([('Ramesh','DEO'),('Kumar','Office Assistant')]);self.enter(bid,'Ramesh')
        self.enter(bid,'Kumar');self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Office Assistant')
        status,r=self.sort(bid,2,'desc');self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Office Assistant')
        self.assertEqual(self.book(bid)['NEFT']['J2'].value,'=H2*2')

    def test_completed_upload_original_bytes_and_manual_designation(self):
        bid,target=self.prepare([('Ramesh','DEO'),('Priya','Accountant')])
        from test_neft_sync import neft_file
        w=openpyxl.load_workbook(io.BytesIO(neft_file(1)));w['NEFT']['B2']='Ramesh';w['NEFT']['C2']='Manual'
        raw=payload(w);uploaded=self.upload(raw,'neft')
        status,original=self.app.request('/api/excel/download?id='+uploaded+'&version=1',token=self.user,binary=True)
        self.assertEqual(original,raw);self.assertEqual(self.book(uploaded)['NEFT']['C2'].value,'Manual')
        w['NEFT']['C2']=None;w['NEFT']['B2']='Priya'
        automatic=self.upload(payload(w),'neft')
        self.assertEqual(self.book(automatic)['NEFT']['C2'].value,'Accountant')

    def test_blank_source_manual_override_and_explicit_replace(self):
        bid,target=self.prepare([('Ramesh','DEO')]);self.enter(bid,'Ramesh')
        status,r=self.save(target,[{'sheet':'Worksheet','address':'C2','value':'','type':'text'}]);self.assertEqual(status,200,r)
        self.assertIsNone(self.book(bid)['NEFT']['C2'].value)
        self.enter(bid,'Ramesh','Personal role')
        status,r=self.save(target,[{'sheet':'Worksheet','address':'C2','value':'Manager','type':'text'}]);self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Personal role')
        status,r=self.post('neft',{'id':bid,'revision':self.meta(bid)['book']['revision'],'sheet':'NEFT','action':'designations'});self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Manager')

    def test_generated_mirrors_do_not_hide_changes_in_original_lookup_source(self):
        source=openpyxl.load_workbook(io.BytesIO(worksheet_file(1)));source['Worksheet']['B2']='Unique person';source['Worksheet']['C2']='DEO'
        original=self.upload(payload(source),'worksheet')
        status,b=self.post('blank',{'id':self.master_neft});self.assertEqual(status,200,b);bid=b['id']
        self.enter(bid,'Unique person');self.assertEqual(self.book(bid)['NEFT']['C2'].value,'DEO')
        self.assertNotEqual(self.pair(bid),original)
        status,r=self.save(original,[{'sheet':'Worksheet','address':'C2','value':'Updated role','type':'text'}]);self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['NEFT']['C2'].value,'Updated role')
        self.enter(bid,'Unknown person');self.enter(bid,'Unknown person')
        self.assertIn('unknown',[n['status'] for n in self.grid(bid)['neft']['designation_notes']])

    def test_lookup_never_reads_another_owners_employee_designation(self):
        source=openpyxl.load_workbook(io.BytesIO(worksheet_file(1)));source['Worksheet']['B2']='Private person';source['Worksheet']['C2']='Private role'
        self.upload(payload(source),'worksheet',token=self.app.login('Rupashri'))
        status,b=self.post('blank',{'id':self.master_neft});self.assertEqual(status,200,b)
        self.enter(b['id'],'Private person');self.assertIsNone(self.book(b['id'])['NEFT']['C2'].value)

    def test_row7_uses_actual_first_employee_rules_and_preserves_upload(self):
        raw=payload(template());blank,_=E.blank_workbook(raw,self.app.g);w=openpyxl.load_workbook(io.BytesIO(blank));s=w['TNOU']
        self.assertEqual(s['I7'].value,'=E7/F7*H7*13%');self.assertIsNone(s['J7'].value);self.assertIsNone(s['L7'].value)
        self.assertEqual(s['Q7'].value,'=O7+P7');self.assertEqual(s['J8'].value,'=20000/F8*H8*3.25%')
        original_template=template()['TNOU']
        from openpyxl.formula.translate import Translator
        for original_row in range(8,62):
            for c in original_template[original_row]:
                if c.data_type=='f':self.assertEqual(s.cell(original_row-1,c.column).value,Translator(c.value,origin=c.coordinate).translate_formula(s.cell(original_row-1,c.column).coordinate))
        self.assertEqual(sum(c.data_type=='f' for sheet in w for row in sheet for c in row),667)
        self.assertEqual(s['I49'].value,'=13000/F49*H49*13%');self.assertEqual(s['S61'].value,'=SUM(S7:S60)')
        for c,v in {'D':40000,'E':50000,'F':31,'H':31}.items():s[c+'7']=v
        results=C.Calculator(w).results()
        for c,value in {'G':0,'I':6500,'K':6000,'M':12500,'N':27500,'P':1700,'Q':41700,'R':7506,'S':49206}.items():self.assertEqual(float(results[('TNOU',c+'7')]['value']),value)
        original=openpyxl.load_workbook(io.BytesIO(raw));self.assertIsNone(original['TNOU']['I7'].value)
        master=self.upload(raw,'worksheet',master=True)
        status,b=self.post('blank',{'id':master});self.assertEqual(status,200,b)
        patches=[{'sheet':'TNOU','address':c+'7','value':str(v),'type':'number'} for c,v in {'D':40000,'E':50000,'F':31,'H':31}.items()]
        status,r=self.save(b['id'],patches);self.assertEqual(status,200,r)
        self.assertEqual(self.book(b['id'])['TNOU']['I7'].value,'=E7/F7*H7*13%')
        grid=self.grid(b['id'],'TNOU');c=next(c for row in grid['rows'] for c in row['cells'] if c['address']=='S7');self.assertEqual(float(c['value']),49206);self.assertFalse(c['editable'])

    def test_legacy_manual_spacer_is_repaired_without_replacing_records(self):
        raw=payload(template());master=self.upload(raw,'worksheet',master=True)
        status,b=self.post('blank',{'id':master});self.assertEqual(status,200,b)
        legacy=template();legacy['TNOU']['D7']=40000;legacy['TNOU']['E7']=50000;legacy['TNOU']['F7']=31;legacy['TNOU']['H7']=31;legacy['TNOU']['B8']='Keep existing record'
        book=E.book(self.app.g,'Nandha',b['id']);repaired=E.read(payload(legacy),self.app.g);E.repair_manual_start(self.app.g,book,repaired)
        self.assertEqual(repaired['TNOU']['I7'].value,'=E7/F7*H7*13%');self.assertEqual(repaired['TNOU']['B8'].value,'Keep existing record');self.assertEqual(repaired['TNOU']['S62'].value,'=SUM(S7:S61)')
        schema=json.loads(book['schema_json']);schema['TNOU']['B7']='n';schema['TNOU']['C7']='n'
        self.app.g['DB'].execute('UPDATE ew_books SET schema_json=? WHERE id=?',(json.dumps(schema),book['id']))
        E.write_version(self.app.g,book,'Nandha',payload(legacy),{'legacy_fixture':True});self.app.g['DB'].commit()
        status,result=self.save(book['id'],[{'sheet':'TNOU','address':'B7','value':'Ramesh','type':'text'},{'sheet':'TNOU','address':'C7','value':'DEO','type':'text'}]);self.assertEqual(status,200,result)
        self.assertEqual(self.book(book['id'])['TNOU']['B7'].value,'Ramesh')
        saved=E.book(self.app.g,'Nandha',book['id']);self.assertEqual(json.loads(saved['schema_json'])['TNOU']['B7'],'s')
