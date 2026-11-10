"""Shared reference access must work without pre-created employee document copies."""
import base64
import io
import json
import unittest
from urllib.parse import urlencode

import openpyxl
from support import AppFixture
from test_document_workspace import seed_documents
from test_excel_workspace import sample
import excel_workspace as EW
import word_workspace as WORD


class SharedTemplateLibraryTests(unittest.TestCase):
    def setUp(self):
        self.app=AppFixture();self.info=seed_documents(self.app,assign=False)
    def tearDown(self):self.app.close()
    def get(self,name,path):return self.app.request(path,token=self.info['employees'][name]['token'])
    def post(self,name,action,body):return self.app.request('/api/excel/'+action,body,self.info['employees'][name]['token'])
    def download(self,name,bid):return self.app.request('/api/excel/download?id='+bid,token=self.info['employees'][name]['token'],binary=True)

    def test_all_four_catalogs_use_same_three_masters_without_document_copies(self):
        for name in self.info['employees']:
            status,data=self.get(name,'/api/excel');self.assertEqual(status,200,data)
            self.assertEqual(data['books'],[])
            self.assertEqual({t['category']:t['id'] for t in data['templates']},self.info['masters'])
            self.assertTrue(all(t['shared'] and t['can_edit'] and t['can_download'] for t in data['templates']))
            for category,bid in self.info['masters'].items():
                status,meta=self.get(name,'/api/excel/metadata?'+urlencode({'id':bid,'template':1}))
                self.assertEqual(status,200,meta)
                if category=='letter':
                    text=json.dumps(meta['document']);self.assertIn('[Date]',text);self.assertNotIn('12,29,773',text)
                else:
                    self.assertEqual([s['name'] for s in meta['sheets']],['Payroll','Invoice'])
                    status,sheet=self.get(name,'/api/excel/sheet?'+urlencode({'id':bid,'template':1,'sheet':'Payroll'}))
                    self.assertEqual(status,200,sheet);self.assertEqual(sheet['header_rows'][0][2],'ACCOUNT NUMBER')
                    self.assertTrue(all(c['value']=='' for c in sheet['rows'][0]['cells']))
                    self.assertNotIn('=D3',json.dumps(sheet))
        self.assertEqual(self.app.g['DB'].execute('SELECT COUNT(*) FROM ew_books').fetchone()[0],3)
        self.assertEqual(self.app.g['DB'].execute('SELECT COUNT(*) FROM ew_versions').fetchone()[0],3)
        self.assertEqual(self.app.g['DB'].execute('SELECT COUNT(*) FROM ew_template_access').fetchone()[0],12)

    def test_all_four_create_edit_save_download_three_independent_documents(self):
        documents={}
        for index,name in enumerate(self.info['employees'],1):
            documents[name]={}
            for category,master in self.info['masters'].items():
                status,b=self.post(name,'blank',{'id':master});self.assertEqual(status,200,b);bid=b['id'];documents[name][category]=bid
                if category=='letter':payload={'paragraphs':[{'paragraph':0,'text':'Private letter '+name}]}
                else:payload={'changes':[{'sheet':'Payroll','address':'B3','value':'Private '+name},{'sheet':'Payroll','address':'D3','value':str(index*100)}]}
                status,result=self.post(name,'save',{'id':bid,'revision':1,**payload});self.assertEqual(status,200,result)
                status,raw=self.download(name,bid);self.assertEqual(status,200)
                if category=='letter':
                    _,tree=WORD.read(raw);self.assertIn('Private letter '+name,json.dumps(WORD.preview(raw)))
                else:
                    w=openpyxl.load_workbook(io.BytesIO(raw));self.assertEqual(w['Payroll']['B3'].value,'Private '+name)
                    self.assertEqual(w['Payroll']['E3'].value,'=D3*2');self.assertEqual(w.sheetnames,['Payroll','Invoice'])
                    cached=openpyxl.load_workbook(io.BytesIO(raw),data_only=True);self.assertEqual(cached['Payroll']['E3'].value,index*200)
                status,listed=self.get(name,'/api/excel');self.assertEqual(status,200)
                self.assertTrue(all(book['owner']==name for book in listed['books']))
        self.assertEqual(len({bid for books in documents.values() for bid in books.values()}),12)
        for owner,books in documents.items():
            for other in self.info['employees']:
                if other==owner:continue
                for category,bid in books.items():
                    for path in ('metadata','history','download','sheet','document'):
                        self.assertEqual(self.get(other,'/api/excel/'+path+'?id='+bid+'&template=1')[0],403)
                    self.assertEqual(self.post(other,'blank',{'id':bid})[0],403)
        self.assertEqual(self.app.g['DB'].execute('SELECT COUNT(*) FROM ew_books WHERE master=1').fetchone()[0],3)
        self.assertTrue(all(r[0]==1 for r in self.app.g['DB'].execute('SELECT revision FROM ew_books WHERE master=1')))

    def test_grant_does_not_expose_raw_historical_reference_or_allow_master_save(self):
        for name in self.info['employees']:
            for master in self.info['masters'].values():
                for path in ('metadata','sheet','document','history','download'):
                    self.assertEqual(self.get(name,'/api/excel/'+path+'?id='+master)[0],403)
                for path in ('history','download'):
                    self.assertEqual(self.get(name,'/api/excel/'+path+'?id='+master+'&template=1')[0],403)
                self.assertEqual(self.post(name,'save',{'id':master,'revision':1,'changes':[]})[0],403)
                self.assertEqual(self.post(name,'calculate',{'id':master,'revision':1,'changes':[]})[0],403)
        worker=self.app.login('Worker One')
        self.assertEqual(self.app.request('/api/excel',token=worker)[0],403)

    def test_migration_is_idempotent_preserves_saved_work_and_individual_access(self):
        name='Sudharsan';_,b=self.post(name,'blank',{'id':self.info['masters']['neft']})
        original=self.download(name,b['id'])[1]
        db=self.app.g['DB'];before=[tuple(r) for r in db.execute('SELECT * FROM ew_books')]
        for _ in range(3):EW.init(self.app.g)
        self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM ew_books')])
        self.assertEqual(self.download(name,b['id'])[1],original)
        db.execute('UPDATE ew_template_access SET can_view=0 WHERE slot=2 AND user=?',(name,));db.commit()
        _,data=self.get(name,'/api/excel');self.assertEqual(len(data['templates']),2)
        self.assertEqual(self.get(name,'/api/excel/metadata?id='+self.info['masters']['worksheet']+'&template=1')[0],403)
        db.execute('UPDATE ew_template_access SET can_edit=0,can_download=0 WHERE slot=1 AND user=?',('Nandha',));db.commit()
        _,data=self.get('Nandha','/api/excel');template=next(t for t in data['templates'] if t['category']=='neft')
        self.assertFalse(template['can_edit']);self.assertFalse(template['can_download'])
        self.assertEqual(self.post('Nandha','blank',{'id':template['id']})[0],403)

    def test_all_four_completed_uploads_are_unchanged_and_formula_free_files_stay_formula_free(self):
        for name in self.info['employees']:
            w=openpyxl.load_workbook(io.BytesIO(sample()));w['Payroll']['B3']=name
            for s in w:
                for row in s:
                    for cell in row:
                        if cell.data_type=='f':cell.value=999
            out=io.BytesIO();w.save(out);raw=out.getvalue()
            status,p=self.post(name,'preview',{'name':'Completed.xlsx','data':base64.b64encode(raw).decode()});self.assertEqual(status,200,p)
            status,b=self.post(name,'import',{'preview':p['preview'],'completed':True,'category':'worksheet'});self.assertEqual(status,200,b)
            self.assertEqual(self.download(name,b['id'])[1],raw)
            self.assertEqual(self.post(name,'save',{'id':b['id'],'revision':1,'changes':[{'sheet':'Payroll','address':'D3','value':'100'}]})[0],200)
            result=openpyxl.load_workbook(io.BytesIO(self.download(name,b['id'])[1]))
            self.assertEqual(result['Payroll']['B3'].value,name)
            self.assertFalse(any(c.data_type=='f' for s in result for row in s for c in row))


if __name__=='__main__':unittest.main()
