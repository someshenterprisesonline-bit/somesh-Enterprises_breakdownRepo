import io
import json
import os
import sqlite3
import unittest
from pathlib import Path
import openpyxl
import test_neft_sync as N
from test_formula_engine import template,payload
from support import AppFixture
import employee_management as EM
import runtime_storage as R

class ReverseTests(unittest.TestCase):
    setUp=N.NeftSyncTests.setUp
    tearDown=N.NeftSyncTests.tearDown
    post=N.NeftSyncTests.post
    upload=N.NeftSyncTests.upload
    meta=N.NeftSyncTests.meta
    grid=N.NeftSyncTests.grid
    save=N.NeftSyncTests.save
    book=N.NeftSyncTests.book
    sort=N.NeftSyncTests.sort

    def worksheet(self):
        master=self.upload(payload(template()),'worksheet',master=True)
        status,b=self.post('blank',{'id':master});self.assertEqual(status,200,b);return b['id']

    def enter(self,bid,people):
        edits=[]
        for row,name,role,salary,basis,days,present in people:
            for col,v in {'A':row-6,'B':name,'C':role,'D':salary,'E':basis,'F':days,'H':present}.items():edits.append({'sheet':'TNOU','address':col+str(row),'value':str(v),'type':'text' if col in ('B','C') else 'number'})
        status,r=self.save(bid,edits);self.assertEqual(status,200,r);return r

    def test_two_rows_payable_mapping_bank_identity_and_sort(self):
        bid=self.worksheet();r=self.enter(bid,[(7,'wqe','ew',2323,2323,23,21),(8,'ew','we',2323,2323,32,21)])
        state=r['worksheet_sync'];self.assertEqual(state['status'],'synced',state);self.assertEqual(state['records'],2);neft=state['neft']
        rows=list(self.book(neft)['NEFT'].iter_rows(min_row=2));self.assertEqual([r[1].value for r in rows[:2]],['wqe','ew'])
        self.assertAlmostEqual(rows[0][7].value,1590.75);self.assertAlmostEqual(rows[1][7].value,618.3515625)
        status,r=self.save(neft,[{'sheet':'NEFT','address':c+'2','value':v,'type':'text'} for c,v in {'D':'Bank','E':'001234567','F':'Branch','G':'SBIN0001234','I':'Keep remark'}.items()]);self.assertEqual(status,200,r)
        self.assertEqual(self.book(bid)['TNOU']['D7'].value,2323)
        self.enter(bid,[(7,'wqe','Manager',4000,2323,23,21)])
        for direction in ('asc','desc'):
            status,r=self.sort(neft,2,direction);self.assertEqual(status,200,r)
            row=next(r for r in self.book(neft)['NEFT'].iter_rows(min_row=2) if r[1].value=='wqe')
            self.assertEqual([c.value for c in row[3:7]],['Bank','001234567','Branch','SBIN0001234']);self.assertEqual(row[8].value,'Keep remark');self.assertEqual(row[2].value,'Manager');self.assertEqual(row[9].value,'=H'+str(row[0].row)+'*2')
        ws=self.book(bid)['TNOU'];position=next(r for r in range(7,9) if ws.cell(r,2).value=='wqe')
        state=self.enter(bid,[(position,'wqe','Manager',5000,2323,23,21)])['worksheet_sync'];self.assertEqual(state['status'],'synced',state)
        self.assertEqual(self.book(bid)['TNOU']['D8' if self.book(bid)['TNOU']['B8'].value=='wqe' else 'D7'].value,5000)
        status,g=self.app.request('/api/excel/sheet?id='+neft+'&sheet=NEFT',token=self.user);self.assertEqual(g['neft']['records'],2)

    def test_existing_forward_only_pair_adopts_payable_without_touching_banking(self):
        neft=self.upload(N.neft_file(1),'neft')
        linked=self.grid(neft)['neft']['target']
        self.assertIsNotNone(linked)
        self.assertFalse(self.app.g['DB'].execute('SELECT 1 FROM ew_neft_reverse WHERE worksheet=?',(linked,)).fetchone())
        account=self.book(neft)['NEFT']['E2'].value
        status,result=self.save(linked,[{'sheet':'Worksheet','address':'D2','value':'2323','type':'number'}])
        self.assertEqual(status,200,result);self.assertEqual(result['worksheet_sync']['status'],'synced',result)
        self.assertEqual(self.book(neft)['NEFT']['H2'].value,2323)
        self.assertEqual(self.book(neft)['NEFT']['E2'].value,account)

    def test_delete_duplicate_names_empty_status_and_no_banking_reuse(self):
        bid=self.worksheet();r=self.enter(bid,[(7,'Same','Role',1000,1000,30,30),(8,'Same','Other role',1000,1000,30,30)]);neft=r['worksheet_sync']['neft']
        status,r=self.save(neft,[{'sheet':'NEFT','address':'E2','value':'001','type':'text'}]);self.assertEqual(status,200,r)
        self.assertEqual(self.book(neft)['NEFT']['C2'].value,'Role');self.assertEqual(self.book(neft)['NEFT']['C3'].value,'Other role')
        status,r=self.save(bid,rows=[{'sheet':'TNOU','action':'delete','row':7}]);self.assertEqual(status,200,r);self.assertEqual(r['worksheet_sync']['status'],'synced',r)
        w=self.book(neft)['NEFT'];self.assertEqual(w['E2'].value,'001');self.assertIsNone(w['B2'].value);self.assertEqual(w['B3'].value,'Same')
        status,r=self.save(bid,[{'sheet':'TNOU','address':'B7','value':'','type':'text'}]);self.assertEqual(status,200,r);self.assertEqual(r['worksheet_sync']['status'],'empty');self.assertEqual(r['worksheet_sync']['records'],0)

    def test_failure_retry_and_revision_conflicts_are_non_destructive(self):
        bid=self.worksheet();r=self.enter(bid,[(7,'First','Role',1000,1000,30,30)]);neft=r['worksheet_sync']['neft']
        before=self.book(neft)['NEFT']['H2'].value
        status,p=self.post('permissions',{'id':neft,'revision':self.meta(neft)['book']['revision'],'locked':True},self.admin);self.assertEqual(status,200,p)
        r=self.enter(bid,[(7,'First','Role',2000,1000,30,30)]);self.assertEqual(r['worksheet_sync']['status'],'error');self.assertEqual(self.book(neft)['NEFT']['H2'].value,before)
        status,p=self.post('permissions',{'id':neft,'revision':self.meta(neft)['book']['revision'],'locked':False},self.admin);self.assertEqual(status,200,p)
        status,r=self.post('worksheet-sync',{'id':bid,'revision':self.meta(bid)['book']['revision']});self.assertEqual(status,200,r);self.assertEqual(r['worksheet_sync']['records'],1)
        self.assertNotEqual(self.book(neft)['NEFT']['H2'].value,before)
        old=self.meta(neft)['book']['revision'];self.enter(bid,[(7,'First','Role',3000,1000,30,30)])
        status,r=self.post('save',{'id':neft,'revision':old,'changes':[{'sheet':'NEFT','address':'E2','value':'Stale bank draft'}]});self.assertEqual(status,400);self.assertIn('Conflict',r['error'])
        self.assertIsNone(self.book(neft)['NEFT']['E2'].value)

class ProfileSafetyTests(unittest.TestCase):
    def setUp(self):self.app=AppFixture()
    def tearDown(self):self.app.close()

    def test_authoritative_profiles_survive_stale_json_and_preserve_tasks(self):
        a=self.app;before=a.request('/api/meta')[1]['users'];task=a.task(owner='Worker One');snapshot=a.g['get_task'](task)
        a.g['USERS'][:]=[{'name':'Unexpected replacement','admin':True,'role':'Demo','dept':'Fake'}]
        EM.initialize(a.g)
        self.assertEqual(a.request('/api/meta')[1]['users'],before);self.assertEqual(a.g['get_task'](task),snapshot)
        a.g['save']('users.json',{'users':[{'name':'Unexpected replacement','admin':True}]})
        self.assertEqual(a.g['load']('users.json')['users'],before)
        self.assertEqual(R.stored_profiles(Path(a.g['DB_PATH'])),before)
        self.assertEqual(sum(bool(p.get('admin')) for p in before),2)

    def test_absolute_configured_directory_and_empty_roster_validation(self):
        root=self.app.root
        self.assertEqual(R.database_path(root,{'data_dir':'alternative'}),root/'alternative'/'monthly_cycle.db')
        self.assertEqual(R.database_path(root,{}),root/'data/monthly_cycle.db')
        for value in ([],None,[{'name':'Employee','admin':False}]):
            with self.assertRaises(ValueError):R.validate_profiles(value)
        self.app.g['DB'].execute('UPDATE employees SET deleted_at=?',('archived',));self.app.g['DB'].commit()
        with self.assertRaises(ValueError):R.stored_profiles(Path(self.app.g['DB_PATH']))
        self.assertEqual(self.app.g['DB'].execute('SELECT count(*) FROM employees').fetchone()[0],5)
