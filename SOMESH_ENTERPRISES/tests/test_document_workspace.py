import base64
import io
import json
import os
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlencode

import openpyxl
from openpyxl.workbook.properties import CalcProperties
from support import AppFixture
from test_excel_workspace import add_employees, sample
import excel_calculation as CALC
import word_workspace as WORD


def letter_sample():
    out=io.BytesIO()
    parts={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
      '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
      'word/document.xml':'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:jc w:val="right"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>Date: 05/10/2026</w:t></w:r></w:p><w:p><w:r><w:t>For SOMESH ENTERPRISES</w:t></w:r></w:p><w:p><w:r><w:t>Invoice No:SE-538/2026-27 Rs 12,29,773/- In Words (Twelve Lakh Only) September-2026</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>ADVANCE STAMP RECEIPT</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="720" w:bottom="720" w:left="720" w:right="720"/></w:sectPr></w:body></w:document>'}
    with zipfile.ZipFile(out,'w') as z:
        for name,data in parts.items():z.writestr(name,data)
    return out.getvalue()


def seed_documents(app,actual=False,assign=True):
    add_employees(app);admin=app.login();info={'admin':admin,'masters':{},'employees':{}}
    root=Path(os.environ.get('EXCEL_REFERENCE_ROOT',''))
    names={'neft':'538-OMCL-Open University -Sept-26(03-10-2026).xlsx','worksheet':'Oct-26-OMCL - TNOU (1).xlsx','letter':'538-September-26-TN-Open University.docx'}
    for slot,(cat,name) in enumerate(names.items(),1):
        actual_name=name.replace(' (1)','')
        data=(root/actual_name).read_bytes() if actual and (root/actual_name).is_file() else letter_sample() if cat=='letter' else sample()
        status,p=app.request('/api/excel/preview',{'name':name,'data':base64.b64encode(data).decode()},admin);assert status==200,p
        status,b=app.request('/api/excel/import',{'preview':p['preview'],'completed':True,'master':True,'slot':slot,'category':cat},admin);assert status==200,b
        info['masters'][cat]=b['id']
    for name in ('Nandha','Jagadeeshwari','Sudharsan','Rupashri'):
        info['employees'][name]={'token':app.login(name),'books':{}}
        for cat,bid in (info['masters'].items() if assign else []):
            status,b=app.request('/api/excel/assign',{'id':bid,'employee':name},admin);assert status==200,b
            info['employees'][name]['books'][cat]=b['id']
    return info


class DocumentWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app=AppFixture();self.info=seed_documents(self.app);self.e=self.info['employees']['Rupashri'];self.admin=self.info['admin']
    def tearDown(self):self.app.close()
    def post(self,action,body,token=None):return self.app.request('/api/excel/'+action,body,token or self.e['token'])
    def get(self,action,bid,**args):return self.app.request('/api/excel/'+action+'?'+urlencode({'id':bid,**args}),token=self.e['token'])
    def blank(self,cat='worksheet'):
        status,b=self.post('blank',{'id':self.e['books'][cat]});self.assertEqual(status,200,b);return b['id']
    def download(self,bid):
        status,data=self.app.request('/api/excel/download?id='+bid,token=self.e['token'],binary=True);self.assertEqual(status,200);return data

    def test_blank_headers_all_manual_records_empty_and_original_independent(self):
        bid=self.blank();w=openpyxl.load_workbook(io.BytesIO(self.download(bid)))
        self.assertEqual(w.sheetnames,['Payroll','Invoice']);self.assertEqual(w['Payroll']['C2'].value,'ACCOUNT NUMBER')
        self.assertEqual(w['Payroll']['E3'].value,'=D3*2');self.assertIsNone(w['Payroll']['B3'].value);self.assertIsNone(w['Payroll']['D3'].value)
        _,grid=self.get('sheet',bid,sheet='Payroll');self.assertTrue(all(c['value']=='' for c in grid['rows'][0]['cells']))
        self.assertNotIn('=D3',json.dumps(grid));self.assertEqual(grid['rows'][0]['cells'][4]['calculation'],'blank')
        original=openpyxl.load_workbook(io.BytesIO(self.download(self.e['books']['worksheet'])));self.assertEqual(original['Payroll']['B3'].value,'Person 1')

    def test_unsaved_calculation_and_persistent_caches_without_formula_injection(self):
        bid=self.blank();changes=[{'sheet':'Payroll','address':'D3','value':'1200.25','type':'number'},{'sheet':'Payroll','address':'C3','value':'000012345678901234','type':'number'}]
        before=self.download(bid)
        status,result=self.post('calculate',{'id':bid,'revision':1,'changes':changes});self.assertEqual(status,200,result)
        calc=next(c for c in result['calculations'] if c['address']=='E3');self.assertEqual(calc['value'],'2400.50')
        self.assertEqual(self.download(bid),before)
        status,result=self.post('save',{'id':bid,'revision':1,'changes':changes});self.assertEqual(status,200,result)
        raw=self.download(bid);w=openpyxl.load_workbook(io.BytesIO(raw));cached=openpyxl.load_workbook(io.BytesIO(raw),data_only=True)
        self.assertEqual(w['Payroll']['E3'].value,'=D3*2');self.assertEqual(cached['Payroll']['E3'].value,2400.5)
        self.assertEqual(w['Payroll']['C3'].value,'000012345678901234');self.assertEqual(w['Payroll']['C3'].data_type,'s')
        self.assertEqual(self.post('save',{'id':bid,'revision':1,'changes':changes})[0],400)

    def test_row_creation_copies_only_existing_formulas_and_delete_preserves_headers(self):
        bid=self.blank()
        status,result=self.post('save',{'id':bid,'revision':1,'rows':[{'sheet':'Payroll','action':'add','row':4}]});self.assertEqual(status,200,result)
        w=openpyxl.load_workbook(io.BytesIO(self.download(bid)));self.assertEqual(w['Payroll']['E4'].value,'=D4*2');self.assertIsNone(w['Payroll']['B4'].value)
        status,result=self.post('save',{'id':bid,'revision':2,'rows':[{'sheet':'Payroll','action':'delete','row':4}]});self.assertEqual(status,200,result)
        w=openpyxl.load_workbook(io.BytesIO(self.download(bid)));self.assertEqual(w['Payroll']['C2'].value,'ACCOUNT NUMBER');self.assertEqual(w['Payroll']['E4'].value,'=D4*2')

    def test_completed_upload_cached_values_preserved_until_relevant_edit(self):
        w=openpyxl.load_workbook(io.BytesIO(sample()));w['Payroll']['E4']='=D4*3';out=io.BytesIO();w.save(out)
        raw=CALC.write_caches(out.getvalue(),{('Payroll','E3'):{'status':'ready','value':'777'},('Payroll','E4'):{'status':'ready','value':'888'}})
        _,p=self.post('preview',{'name':'Completed.xlsx','data':base64.b64encode(raw).decode()})
        status,b=self.post('import',{'preview':p['preview'],'completed':True,'category':'worksheet'});self.assertEqual(status,200,b);bid=b['id']
        self.assertEqual(self.download(bid),raw)
        _,g=self.get('sheet',bid,sheet='Payroll');self.assertEqual(g['rows'][0]['cells'][4]['value'],'777')
        self.assertEqual(self.download(bid),raw)
        self.assertEqual(self.post('save',{'id':bid,'revision':1,'changes':[{'sheet':'Payroll','address':'D3','value':'100'}]})[0],200)
        raw=self.download(bid);cached=openpyxl.load_workbook(io.BytesIO(raw),data_only=True);self.assertEqual(cached['Payroll']['E3'].value,200);self.assertEqual(cached['Payroll']['E4'].value,888)
        w=openpyxl.load_workbook(io.BytesIO(raw));self.assertEqual(w['Payroll']['E3'].value,'=D3*2');self.assertEqual(w['Payroll']['E4'].value,'=D4*3')

    def test_upload_without_formulas_never_injects_template_formulas(self):
        w=openpyxl.load_workbook(io.BytesIO(sample()))
        for s in w:
            for row in s:
                for c in row:
                    if c.data_type=='f':c.value=999
        out=io.BytesIO();w.save(out);raw=out.getvalue()
        _,p=self.post('preview',{'name':'Manual.xlsx','data':base64.b64encode(raw).decode()})
        _,b=self.post('import',{'preview':p['preview'],'completed':True,'category':'worksheet'});bid=b['id'];self.assertEqual(self.download(bid),raw)
        self.assertEqual(self.post('save',{'id':bid,'revision':1,'changes':[{'sheet':'Payroll','address':'D3','value':'100'}]})[0],200)
        w=openpyxl.load_workbook(io.BytesIO(self.download(bid)));self.assertFalse(any(c.data_type=='f' for s in w for row in s for c in row));self.assertEqual(w['Payroll']['E3'].value,999)

    def test_unsupported_calculation_and_missing_inputs_are_not_incorrect_results(self):
        w=openpyxl.Workbook();s=w.active;s['A1']=5;s['B1']='=FOOBAR(A1)';s['C1']='=A2/A3';s['D1']='=SUM(A2:A3)';s['E1']='=A1*13%'
        r=CALC.Calculator(w).results();self.assertEqual(r[('Sheet','B1')]['status'],'pending');self.assertEqual(r[('Sheet','C1')]['status'],'blank');self.assertEqual(r[('Sheet','D1')]['status'],'blank');self.assertEqual(r[('Sheet','E1')]['value'],'0.65')

    def test_word_blank_edit_preserves_format_tables_and_package_parts(self):
        bid=self.blank('letter');raw=self.download(bid);_,tree=WORD.read(raw);txt=' '.join(WORD.text(p) for p in tree.findall('.//w:p',WORD.NS))
        self.assertNotIn('538/2026',txt);self.assertNotIn('12,29,773',txt);self.assertNotIn('September-2026',txt);self.assertIn('SOMESH ENTERPRISES',txt);self.assertIn('ADVANCE STAMP RECEIPT',txt)
        self.assertIn('[Date]',txt);self.assertEqual(len(tree.findall('.//w:tbl',WORD.NS)),1)
        status,result=self.post('save',{'id':bid,'revision':1,'paragraphs':[{'paragraph':0,'text':'Date: 07/11/2026'}]});self.assertEqual(status,200,result)
        out=self.download(bid);_,after=WORD.read(out);self.assertEqual(WORD.text(after.findall('.//w:p',WORD.NS)[0]),'Date: 07/11/2026')
        self.assertIsNotNone(after.find('.//w:pPr/w:jc',WORD.NS));self.assertIsNotNone(after.find('.//w:rPr/w:b',WORD.NS))
        with zipfile.ZipFile(io.BytesIO(raw)) as a,zipfile.ZipFile(io.BytesIO(out)) as b:
            for name in a.namelist():
                if name!='word/document.xml':self.assertEqual(a.read(name),b.read(name))
        self.assertEqual(self.get('document',bid)[0],200)
        other=self.info['employees']['Nandha']['token'];self.assertEqual(self.app.request('/api/excel/document?id='+bid,token=other)[0],403)

    def test_download_filename_sanitization(self):
        import excel_workspace as EW
        self.assertEqual(EW.filename('payroll:<Nov>.xlsx','xlsx'),'payroll__Nov_.xlsx')
        self.assertEqual(EW.filename('Letter.docx','docx'),'Letter.docx')
        with self.assertRaises(ValueError):EW.filename(' ... ','xlsx')
        self.assertEqual(self.get('download',self.e['books']['worksheet'],filename=' ... ')[0],400)

    @unittest.skipUnless(os.environ.get('EXCEL_REFERENCE_ROOT'),'Private reference paths required')
    def test_real_blank_payroll_and_covering_letter(self):
        root=Path(os.environ['EXCEL_REFERENCE_ROOT']);data=(root/'Oct-26-OMCL - TNOU.xlsx').read_bytes()
        import excel_workspace as EW
        raw,schema=EW.blank_workbook(data,self.app.g);w=openpyxl.load_workbook(io.BytesIO(raw));s=w['TNOU']
        self.assertIsNone(s['B8'].value);self.assertIsNone(s['H8'].value);self.assertEqual(s['I8'].value,'=E8/F8*H8*13%')
        s['E8']=30000;s['F8']=30;s['H8']=23
        self.assertEqual(CALC.Calculator(w).results()[('TNOU','I8')]['value'],'2990.00')
        original=(root/'538-September-26-TN-Open University.docx').read_bytes();blank=WORD.blank(original)
        _,t=WORD.read(blank);txt=' '.join(WORD.text(p) for p in t.findall('.//w:p',WORD.NS));self.assertNotIn('September-2026',txt);self.assertNotIn('SE-538/2026-27',txt);self.assertNotIn('12,29,773',txt)
        self.assertIn('Overseas Manpower Corporation Limited',txt);self.assertIn('Proprietor',txt)

    @unittest.skipUnless(os.environ.get('EXCEL_REFERENCE_ROOT'),'Private reference paths required')
    def test_real_payroll_row_expands_summary_range_and_preserves_formula_pattern(self):
        import excel_workspace as EW
        root=Path(os.environ['EXCEL_REFERENCE_ROOT']);data=(root/'Oct-26-OMCL - TNOU.xlsx').read_bytes()
        raw,_=EW.blank_workbook(data,self.app.g);w=openpyxl.load_workbook(io.BytesIO(raw));s=w['TNOU'];last=EW.layout(s)['data_end']
        from openpyxl.formula.translate import Translator
        expected=Translator(s.cell(last,9).value,origin=s.cell(last,9).coordinate).translate_formula(s.cell(last+1,9).coordinate)
        EW.change_row(self.app.g,w,s,{'action':'add','row':last+1},{'formulas_unlocked':False},False)
        self.assertEqual(s.cell(last+1,9).value,expected)
        self.assertEqual(s.cell(last+2,9).value,f'=SUM(I8:I{last+1})')
        self.assertEqual(s.cell(last+1,9).number_format,'0')


if __name__=='__main__':unittest.main()
