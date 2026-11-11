"""Payroll formulas copied from the reference; all employee inputs are synthetic."""
import io
import json
import os
import unittest
from pathlib import Path
import openpyxl
from support import AppFixture
from test_excel_workspace import seed
import excel_calculation as C
import excel_workspace as EW

MANIFEST = json.loads((Path(__file__).parent/'fixtures/tnou_formula_manifest.json').read_text())

def template():
    w = openpyxl.Workbook(); w.remove(w.active)
    for name, spec in MANIFEST.items():
        s = w.create_sheet(name)
        for row, values in enumerate(spec['layout']['header_rows'], spec['layout']['header_start']):
            for col, value in enumerate(values, 1): s.cell(row,col,value)
        for address, formula in spec['formulas'].items(): s[address] = formula
        for address, fmt in spec['formats'].items(): s[address].number_format = fmt
        if name=='TNOU':
            for employee_row in range(8,spec['layout']['data_end']+1):
                s.cell(employee_row,1,employee_row-7)
                s.cell(employee_row,2,'Synthetic employee '+str(employee_row))
                s.cell(employee_row,3,'Synthetic designation')
        s.cell(spec['layout']['data_end']+1,1,'Total')
        for merged in spec['merges']: s.merge_cells(merged)
    return w

def payload(w):
    out=io.BytesIO();w.save(out);return out.getvalue()

class FormulaTests(unittest.TestCase):
    def test_all_reference_formulas_and_employee_exceptions(self):
        w=template();s=w['TNOU']
        self.assertEqual([len(x['formulas']) for x in MANIFEST.values()],[653,14])
        for row in range(8,62):
            for col,value in {'D':23250,'E':20000,'F':31,'H':25}.items():s[f'{col}{row}']=value
        r=C.Calculator(w).results()
        for row in range(8,62):
            with self.subTest(row=row):
                def value(col):return float(r[('TNOU',f'{col}{row}')]['value'])
                employer_base=13000 if row>=50 else 20000
                esic_base=20000 if 9<=row<=37 else 15000 if 42<=row<=48 else 13000 if row>=50 else 0
                employee_base=20000 if 9<=row<=37 or 42<=row<=48 else 13000 if row>=50 else 0
                self.assertEqual(value('G'),6)
                self.assertAlmostEqual(value('I'),employer_base/31*25*.13)
                self.assertAlmostEqual(value('J'),esic_base/31*25*.0325) if esic_base else self.assertIsNone(s[f'J{row}'].value)
                self.assertAlmostEqual(value('K'),20000/31*25*.12)
                if employee_base:self.assertAlmostEqual(value('L'),employee_base/31*25*.0075)
                contribution=employer_base/31*25*.13+esic_base/31*25*.0325+20000/31*25*.12+employee_base/31*25*.0075
                self.assertAlmostEqual(value('M'),contribution)
                self.assertAlmostEqual(value('N'),23250/31*25-contribution)
                self.assertAlmostEqual(value('P'),20000/31*25*.034)
                self.assertAlmostEqual(value('R'),value('Q')*.18)
                self.assertAlmostEqual(value('S'),(23250/31*25+20000/31*25*.034)*1.18)
        self.assertEqual(r[('TNOU','F68')]['value'],'13000')
        self.assertAlmostEqual(float(r[('TNOU','S62')]['value']),sum(float(r[('TNOU',f'S{i}')]['value']) for i in range(8,62)))

    def test_days_changes_invoice_and_dependency_closure(self):
        w=template();s=w['TNOU']
        for col,value in {'D':23250,'E':20000,'F':31,'H':25}.items():s[col+'9']=value
        for days,present in [(30,25),(31,0),(31,31)]:
            s['F9']=days;s['H9']=present
            r=C.Calculator(w).results(C.affected(w,[{'sheet':'TNOU','address':'F9'}]))
            self.assertEqual(float(r[('TNOU','G9')]['value']),days-present)
            self.assertAlmostEqual(float(r[('TNOU','S9')]['value']),(23250+680)/days*present*1.18)
            self.assertNotIn(('TNOU','I10'),r)
        s=w['In']
        for row in range(9,16):s[f'F{row}']=3100;s[f'E{row}']=25
        s['G16']=100;s['G18']=20;s['G19']=30
        r=C.Calculator(w).results()
        self.assertEqual(float(r[('In','G17')]['value']),17600)
        self.assertAlmostEqual(float(r[('In','G25')]['value']),(17650+17600*.034)*1.18)

    def test_insert_delete_preserves_exceptions_and_expands_totals(self):
        w=template();s=w['TNOU'];book={'origin':'blank','formulas_unlocked':False}
        EW.change_row({},w,s,{'action':'add','row':50},book,False)
        self.assertEqual(s['I51'].value,'=13000/F51*H51*13%')
        self.assertEqual(s['S63'].value,'=SUM(S8:S62)')
        EW.change_row({},w,s,{'action':'delete','row':50},book,False)
        self.assertEqual(s['I50'].value,'=13000/F50*H50*13%')
        self.assertEqual(s['S62'].value,'=SUM(S8:S61)')
        uploaded=template();EW.change_row({},uploaded,uploaded['TNOU'],{'action':'add','row':50},{'origin':'upload','formulas_unlocked':False},False)
        self.assertIsNone(uploaded['TNOU']['I50'].value)

    def test_safe_errors_cross_sheet_and_caches(self):
        w=template();s=w['In'];s['Z1']="='TNOU'!F68*2";s['Z2']='=Z3';s['Z3']='=Z2';s['Z4']='=1/0';s['Z5']='=WEBSERVICE("x")';s['Z6']='=SUM(Y1:Y2)'
        r=C.Calculator(w).results();self.assertEqual(r[('In','Z1')]['value'],'26000')
        for a in ('Z2','Z3','Z4','Z5'):self.assertEqual(r[('In',a)]['status'],'pending')
        self.assertEqual(r[('In','Z6')]['value'],'0')
        data=C.write_caches(payload(w),r);values=openpyxl.load_workbook(io.BytesIO(data),data_only=True)
        self.assertEqual(values['In']['Z1'].value,26000)
        self.assertEqual(openpyxl.load_workbook(io.BytesIO(data))['In']['Z1'].value,"='TNOU'!F68*2")
        self.assertEqual(C.display('1.234567','General'),'1.234567')

    def test_api_preview_save_refresh_sort_and_export(self):
        with_fixture=AppFixture()
        try:
            info=seed(with_fixture,payload(template()));e=info['employees']['Nandha'];token=e['token']
            def request(action,body=None,binary=False):return with_fixture.request('/api/excel/'+action,body,token,binary=binary)
            status,b=request('blank',{'id':e['id']});self.assertEqual(status,200,b);bid=b['id']
            changes=[{'sheet':'TNOU','address':col+'9','value':str(v),'type':'number'} for col,v in {'D':23250,'E':20000,'F':31,'H':25}.items()]
            status,r=request('calculate',{'id':bid,'revision':1,'changes':changes});self.assertEqual(status,200,r)
            self.assertTrue(any(c['address']=='S9' and c['status']=='ready' for c in r['calculations']))
            status,r=request('save',{'id':bid,'revision':1,'changes':changes});self.assertEqual(status,200,r)
            for query in ('','&sort=4&direction=desc'):
                status,g=request('sheet?id='+bid+'&sheet=TNOU&limit=100'+query);self.assertEqual(status,200,g)
                c=next(c for row in g['rows'] for c in row['cells'] if c['address']=='S9');self.assertFalse(c['editable']);self.assertAlmostEqual(float(c['value']),22772.09677419355)
                total=next(c for row in g['rows'] for c in row['cells'] if c['address']=='S'+str(g['data_end']+1));self.assertAlmostEqual(float(total['value']),22772.09677419355)
            status,data=request('download?id='+bid,binary=True);self.assertEqual(status,200)
            self.assertEqual(openpyxl.load_workbook(io.BytesIO(data))['TNOU']['J9'].value,'=20000/F9*H9*3.25%')
            self.assertAlmostEqual(openpyxl.load_workbook(io.BytesIO(data),data_only=True)['TNOU']['S9'].value,22772.09677419355)
        finally:with_fixture.close()

    @unittest.skipUnless(os.environ.get('TNOU_REFERENCE_FILE'),'Set TNOU_REFERENCE_FILE for private reference comparison')
    def test_saved_excel_results_all_667_formulas(self):
        raw=Path(os.environ['TNOU_REFERENCE_FILE']).read_bytes();w=openpyxl.load_workbook(io.BytesIO(raw));v=openpyxl.load_workbook(io.BytesIO(raw),data_only=True);r=C.Calculator(w).results();compared=0
        for s in w:
            self.assertEqual({c.coordinate:c.value for row in s for c in row if c.data_type=='f'},MANIFEST[s.title]['formulas'])
            for row in s:
                for c in row:
                    if c.data_type!='f':continue
                    self.assertEqual(r[(s.title,c.coordinate)]['status'],'ready',s.title+'!'+c.coordinate)
                    saved=v[s.title][c.coordinate].value
                    if isinstance(saved,(int,float)):
                        self.assertEqual(r[(s.title,c.coordinate)]['status'],'ready',c.coordinate)
                        self.assertAlmostEqual(float(r[(s.title,c.coordinate)]['value']),saved,places=7,msg=s.title+'!'+c.coordinate);compared+=1
        print('Excel saved caches compared:',compared,'of 667; missing caches are not comparisons')
