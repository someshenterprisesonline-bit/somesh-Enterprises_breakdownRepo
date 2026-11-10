import base64
import io
import json
import os
import time
import unittest
from pathlib import Path

import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation
from support import AppFixture

EMPLOYEES = [('Nandha', 'Payroll'), ('Jagadeeshwari', 'Payroll'), ('Sudharsan', 'Operations'), ('Rupashri', 'Finance, Contracts & Vault')]


def add_employees(app):
    for name, dept in EMPLOYEES:
        app.g['USERS'].append({'name': name, 'dept': dept, 'role': 'Employee'})
        app.g['USER_NAMES'].add(name)


def sample(rows=3):
    w = openpyxl.Workbook(); s = w.active; s.title = 'Payroll'
    s.merge_cells('A1:F1'); s['A1'] = 'Original title'
    s.append(['S.No', 'Name', 'ACCOUNT NUMBER', 'Salary', 'Calculated', 'Date'])
    for i in range(1, rows + 1):
        s.append([i, 'Person ' + str(i), '001234567890123456', 12345.67, f'=D{i+2}*2', None])
    s['C3'].number_format = '@'; s['F3'] = __import__('datetime').datetime(2026, 11, 7); s['F3'].number_format = 'dd/mm/yyyy'
    validation = DataValidation(type='list', formula1='"Approved,Pending"'); s.add_data_validation(validation); validation.add('B4')
    second = w.create_sheet('Invoice'); second.append(['S.No', 'Original\n Header']); second.append([1, '=Payroll!D3'])
    out = io.BytesIO(); w.save(out); return out.getvalue()


def seed(app, data=None):
    add_employees(app); admin = app.login()
    data = data or sample()
    status, p = app.request('/api/excel/preview', {'name': 'Payroll.xlsx', 'data': base64.b64encode(data).decode()}, admin)
    assert status == 200, p
    status, b = app.request('/api/excel/import', {'preview': p['preview'], 'sheet': p['sheets'][0]['name'], 'slot': 1}, admin)
    assert status == 200, b
    result = {'admin': admin, 'master': b['id'], 'employees': {}}
    for name, _ in EMPLOYEES:
        status, assigned = app.request('/api/excel/assign', {'id': b['id'], 'employee': name}, admin)
        assert status == 200, assigned
        result['employees'][name] = {'token': app.login(name), 'id': assigned['id']}
    return result


class ExcelWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture(); self.info = seed(self.app)
        self.admin = self.info['admin']; self.employee = self.info['employees']['Nandha']

    def tearDown(self):
        self.app.close()

    def request(self, action, body=None, employee=None):
        e = employee or self.employee
        return self.app.request('/api/excel/' + action, body, e['token'])

    def save(self, changes, revision=1, **extra):
        return self.request('save', {'id': self.employee['id'], 'revision': revision, 'changes': changes, **extra})

    def test_four_employees_independent_access_and_unauthorized_endpoints(self):
        for name, e in self.info['employees'].items():
            status, result = self.app.request('/api/excel', token=e['token'])
            self.assertEqual(status, 200); self.assertEqual(len(result['books']), 1)
            self.assertEqual(result['books'][0]['owner'], name)
            for endpoint in ('metadata', 'sheet', 'history', 'download'):
                status, _ = self.app.request('/api/excel/'+endpoint+'?id='+self.info['master'], token=e['token'])
                self.assertEqual(status, 403)
        status, _ = self.app.request('/api/excel', token=self.app.login('Worker One'))
        self.assertEqual(status, 403)
        self.assertEqual(self.app.request('/api/excel')[0], 401)

    def test_persistence_types_headers_formulas_and_download(self):
        bid = self.employee['id']
        status, result = self.save([{'sheet':'Payroll','address':'D3','value':'23456.78'}, {'sheet':'Payroll','address':'C3','value':'009999999999999999'}, {'sheet':'Payroll','address':'F3','value':'2026-12-01','type':'date'}])
        self.assertEqual(status, 200, result)
        status, sheet = self.request('sheet?id='+bid+'&sheet=Payroll')
        self.assertEqual(sheet['book']['revision'], 2)
        self.assertEqual(sheet['rows'][0]['cells'][3]['value'], '23456.78')
        status, data = self.app.request('/api/excel/download?id='+bid, token=self.employee['token'], binary=True)
        self.assertEqual(status, 200)
        w = openpyxl.load_workbook(io.BytesIO(data)); self.assertEqual(w.sheetnames, ['Payroll','Invoice'])
        self.assertEqual(w['Payroll']['C3'].value, '009999999999999999'); self.assertEqual(w['Payroll']['C3'].data_type, 's')
        self.assertEqual(w['Payroll']['D3'].value, 23456.78); self.assertEqual(w['Payroll']['E3'].value, '=D3*2')
        self.assertEqual(w['Invoice']['B2'].value, '=Payroll!D3'); self.assertEqual(w['Payroll']['F3'].number_format, 'dd/mm/yyyy')
        self.assertEqual(list(w['Payroll'].merged_cells.ranges)[0].coord, 'A1:F1')
        self.assertEqual(w['Payroll']['C2'].value, 'ACCOUNT NUMBER')
        self.assertEqual(len(w['Payroll'].data_validations.dataValidation), 1)

    def test_invalid_uploads_and_headers_formula_validation_protected(self):
        for name, data in [('bad.xls', b'bad'), ('bad.xlsx', b'bad')]:
            status, _ = self.request('preview', {'name':name,'data':base64.b64encode(data).decode()})
            self.assertEqual(status, 400)
        for addr, value in [('A2','Rename'),('E3','0'),('D3','NaN'),('D3','1234567890123456'),('B4','Not in list'),('B3','=WEBSERVICE("http://x")')]:
            status, result = self.save([{'sheet':'Payroll','address':addr,'value':value}])
            self.assertEqual(status, 400, result)

    def test_conflict_permissions_audit_and_restore(self):
        bid = self.employee['id']
        status, result = self.save([{'sheet':'Payroll','address':'D3','value':'100'}]); self.assertEqual(status, 200)
        status, result = self.save([{'sheet':'Payroll','address':'D3','value':'200'}]); self.assertEqual(status, 400); self.assertIn('Conflict', result['error'])
        body={'id':bid,'revision':2,'can_edit':False,'can_download':False,'locked':True}
        self.assertEqual(self.app.request('/api/excel/permissions',body,self.admin)[0],200)
        self.assertEqual(self.save([],3)[0],403); self.assertEqual(self.request('download?id='+bid)[0],403)
        self.assertEqual(self.request('permissions',{'id':bid,'revision':3,'can_edit':True})[0],403)
        self.assertEqual(self.app.request('/api/excel/permissions',{'id':bid,'revision':3,'locked':False},self.admin)[0],200)
        self.assertEqual(self.app.request('/api/excel/restore',{'id':bid,'revision':4,'version':1},self.admin)[0],200)
        _, h = self.request('history?id='+bid); self.assertEqual(len(h['versions']),5)
        self.assertIn('cells', json.loads(h['versions'][-2]['changes']))
        self.assertEqual(self.app.request('/api/excel/permissions',{'id':bid,'revision':5,'can_view':False},self.admin)[0],200)
        self.assertEqual(self.request('metadata?id='+bid)[0],403)

    def test_import_versions_mismatch_confirmation_and_private_upload(self):
        status, p = self.request('preview',{'name':'New.xlsx','data':base64.b64encode(sample()).decode()}); self.assertEqual(status,200)
        body={'preview':p['preview'],'sheet':'Payroll','id':self.employee['id'],'revision':1}
        self.assertEqual(self.request('import',body)[0],200)
        self.assertEqual(self.request('history?id='+self.employee['id'])[1]['versions'][0]['revision'],2)
        w=openpyxl.load_workbook(io.BytesIO(sample()));w['Payroll']['B2']='Unexpected';out=io.BytesIO();w.save(out)
        _,p=self.request('preview',{'name':'Different.xlsx','data':base64.b64encode(out.getvalue()).decode()})
        body={'preview':p['preview'],'sheet':'Payroll','id':self.employee['id'],'revision':2}
        _,result=self.request('import',body);self.assertTrue(result['confirmation_required'])
        self.assertEqual(self.request('import',{**body,'confirm_mismatch':True})[0],200)
        _,p=self.request('preview',{'name':'Private.xlsx','data':base64.b64encode(sample()).decode()})
        body={'preview':p['preview'],'sheet':'Payroll'}
        self.assertTrue(self.request('import',body)[1]['confirmation_required'])
        self.assertEqual(self.request('import',{**body,'confirm_mismatch':True})[0],200)

    def test_large_pagination_search_sort_and_row_operations(self):
        _,p=self.request('preview',{'name':'Large.xlsx','data':base64.b64encode(sample(10000)).decode()})
        body={'preview':p['preview'],'sheet':'Payroll','id':self.employee['id'],'revision':1}
        self.assertEqual(self.request('import',body)[0],200)
        start=time.monotonic(); status,result=self.request('sheet?id='+self.employee['id']+'&sheet=Payroll&offset=9000&limit=50')
        self.assertEqual(status,200);self.assertEqual(len(result['rows']),50);self.assertEqual(result['total'],10000)
        self.assertLess(time.monotonic()-start,10)
        _,result=self.request('sheet?id='+self.employee['id']+'&sheet=Payroll&q=Person+9999');self.assertEqual(result['total'],1)
        self.assertEqual(self.save([],2,rows=[{'sheet':'Payroll','action':'add'}])[0],200)
        self.assertEqual(self.save([],3,rows=[{'sheet':'Payroll','action':'delete','row':10003}])[0],200)
        self.assertEqual(self.save([],4,rows=[{'sheet':'Payroll','action':'delete','row':2}])[0],400)

    def test_admin_formula_unlock_and_empty_third_slot(self):
        _,result=self.app.request('/api/excel',token=self.admin);self.assertIsNone(result['slots'][2]['book'])
        bid=self.employee['id']
        self.assertEqual(self.app.request('/api/excel/permissions',{'id':bid,'revision':1,'formulas_unlocked':True},self.admin)[0],200)
        self.assertEqual(self.app.request('/api/excel/save',{'id':bid,'revision':2,'changes':[{'sheet':'Payroll','address':'E3','value':'=D3*3'}]},self.admin)[0],200)
        self.assertEqual(self.save([{'sheet':'Payroll','address':'E3','value':'=D3*4'}],3)[0],400)

    def test_structural_rows_translate_cross_sheet_references_and_preserve_headers(self):
        bid=self.employee['id']
        status,result=self.save([],rows=[{'sheet':'Payroll','action':'add','row':3}]);self.assertEqual(status,200,result)
        _,data=self.app.request('/api/excel/download?id='+bid,token=self.employee['token'],binary=True)
        w=openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual(w['Payroll']['E3'].value,'=D3*2')
        self.assertEqual(w['Payroll']['E4'].value,'=D4*2')
        self.assertEqual(w['Invoice']['B2'].value,'=Payroll!D4')
        self.assertEqual(str(w['Payroll'].data_validations.dataValidation[0].sqref),'B5')
        self.assertEqual(w['Payroll']['B2'].value,'Name')
        self.assertEqual(self.save([],2,rows=[{'sheet':'Payroll','action':'delete','row':2}])[0],400)
        self.assertEqual(self.app.request('/api/excel/permissions',{'id':bid,'revision':2,'formulas_unlocked':True},self.admin)[0],200)
        status,result=self.app.request('/api/excel/save',{'id':bid,'revision':3,'rows':[{'sheet':'Payroll','action':'delete','row':4}]},self.admin)
        self.assertEqual(status,200,result)
        _,data=self.app.request('/api/excel/download?id='+bid,token=self.admin,binary=True)
        w=openpyxl.load_workbook(io.BytesIO(data));self.assertEqual(w['Invoice']['B2'].value,'=#REF!')
        self.assertEqual(w['Payroll']['E4'].value,'=D4*2')

    @unittest.skipUnless(os.environ.get('EXCEL_REFERENCE_ROOT'), 'Set EXCEL_REFERENCE_ROOT to test private real reference workbooks')
    def test_actual_reference_workbooks_round_trip_every_sheet_and_cell(self):
        root = Path(os.environ['EXCEL_REFERENCE_ROOT'])
        for filename in ['538-OMCL-Open University -Sept-26(03-10-2026).xlsx', 'Oct-26-OMCL - TNOU.xlsx']:
            data = (root / filename).read_bytes()
            status, p = self.app.request('/api/excel/preview', {'name':filename,'data':base64.b64encode(data).decode()}, self.admin)
            self.assertEqual(status,200,p)
            status,b = self.app.request('/api/excel/import',{'preview':p['preview'],'sheet':p['sheets'][0]['name'],'slot':2},self.admin)
            self.assertEqual(status,200,b)
            status,download = self.app.request('/api/excel/download?id='+b['id'],token=self.admin,binary=True)
            self.assertEqual(download,data)
            original=openpyxl.load_workbook(io.BytesIO(data))
            sheet=original['TNOU']; address='H8'; value='20.5'
            status,result=self.app.request('/api/excel/save',{'id':b['id'],'revision':1,'changes':[{'sheet':'TNOU','address':address,'value':value}]},self.admin)
            self.assertEqual(status,200,result)
            _,exported=self.app.request('/api/excel/download?id='+b['id'],token=self.admin,binary=True)
            exported=openpyxl.load_workbook(io.BytesIO(exported))
            self.assertEqual(original.sheetnames,exported.sheetnames)
            for s in original:
                out=exported[s.title];self.assertEqual(str(s.merged_cells),str(out.merged_cells))
                self.assertEqual((s.max_row,s.max_column),(out.max_row,out.max_column))
                self.assertEqual(str(s.data_validations),str(out.data_validations))
                for row in s:
                    for c in row:
                        after=out.cell(c.row,c.column)
                        if s.title=='TNOU' and c.coordinate==address:
                            self.assertEqual(after.value,20.5)
                        else:
                            self.assertEqual(c.value,after.value,(filename,s.title,c.coordinate))
                            self.assertEqual(c.data_type,after.data_type)
                        self.assertEqual(c.number_format,after.number_format)


if __name__ == '__main__':
    unittest.main()
