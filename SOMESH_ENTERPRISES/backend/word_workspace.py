"""DOCX text editing by patching original paragraph XML, preserving package/layout."""
import difflib
import base64
import html
import io
import re
import zipfile
from xml.etree import ElementTree as ET

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def read(data):
    if not data or len(data)>10*1024*1024:raise ValueError('Word upload limit is 10 MB.')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if len(z.infolist())>5000 or sum(x.file_size for x in z.infolist())>80*1024*1024:raise ValueError('Word file exceeds safe expansion limits.')
        for name in z.namelist():
            if any(x in name.lower() for x in ('vbaproject','embeddings/','activex/')):raise ValueError('Macros and embedded objects are unsupported.')
            if name.endswith(('.xml','.rels')):
                raw=z.read(name)
                if b'<!ENTITY' in raw or b'<!DOCTYPE' in raw:raise ValueError('Unsafe document XML.')
                if name.endswith('.rels') and re.search(rb'TargetMode\s*=\s*[\'"]External',raw):raise ValueError('External document relationships are unsupported.')
        xml=z.read('word/document.xml').decode('utf-8');tree=ET.fromstring(xml)
        if len(tree.findall('.//w:p',NS))>2000:raise ValueError('Word files are limited to 2,000 paragraphs.')
        return xml,tree


def text(p):return ''.join(t.text or '' for t in p.findall('.//w:t',NS))


def replace_paragraph(raw,new):
    tags=list(re.finditer(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>',raw,re.S))
    if not tags:
        if not new:return raw
        return raw.replace('</w:p>','<w:r><w:t xml:space="preserve">'+html.escape(new,quote=False)+'</w:t></w:r></w:p>')
    strings=[html.unescape(t.group(1)) for t in tags];old=''.join(strings)
    positions=[]
    for i,s in enumerate(strings):positions.extend((i,j) for j in range(len(s)))
    for op,a,b,c,d in reversed(difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes()):
        if op=='equal':continue
        if a<len(positions):index,offset=positions[a]
        else:index,offset=len(strings)-1,len(strings[-1])
        if b>a:
            stop,stopoffset=positions[b-1]
            if stop==index:strings[index]=strings[index][:offset]+new[c:d]+strings[index][stopoffset+1:]
            else:
                strings[index]=strings[index][:offset]+new[c:d]
                for j in range(index+1,stop):strings[j]=''
                strings[stop]=strings[stop][stopoffset+1:]
        else:strings[index]=strings[index][:offset]+new[c:d]+strings[index][offset:]
    for match,value in reversed(list(zip(tags,strings))):
        tag='<w:t xml:space="preserve">'+html.escape(value,quote=False)+'</w:t>'
        raw=raw[:match.start()]+tag+raw[match.end():]
    return raw


def edit(data,changes):
    xml,tree=read(data)
    paragraphs=list(re.finditer(r'<w:p(?=[\s>])[^>]*>.*?</w:p>',xml,re.S))
    if len(paragraphs)!=len(tree.findall('.//w:p',NS)):raise ValueError('Nested text boxes require Word for editing.')
    changes={int(c['paragraph']):c['text'] for c in changes}
    if len(changes)>2000 or any(i<0 or i>=len(paragraphs) or not isinstance(v,str) or len(v)>30000 for i,v in changes.items()):raise ValueError('Invalid paragraph edit.')
    for i,m in reversed(list(enumerate(paragraphs))):
        if i in changes:xml=xml[:m.start()]+replace_paragraph(m.group(),changes[i])+xml[m.end():]
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
        for item in src.infolist():dest.writestr(item,xml.encode('utf-8') if item.filename=='word/document.xml' else src.read(item.filename))
    read(out.getvalue())
    return out.getvalue()


def blank(data):
    _,tree=read(data);changes=[]
    for i,p in enumerate(tree.findall('.//w:p',NS)):
        old=text(p);new=old
        new=re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b','[Date]',new)
        new=re.sub(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)[- ]\d{4}\b','[Month]',new,flags=re.I)
        new=re.sub(r'SE-\d+/\d{4}-\d{2,4}','[Invoice number]',new)
        new=re.sub(r'(Rs\s*)[\d,]+(?:\.\d+)?(?:/-)?',r'\1[Amount]',new)
        new=re.sub(r'(In Words\s*)\([^)]*\)',r'\1([Amount in words])',new,flags=re.I)
        new=re.sub(r'(File No:\s*)[^\n]*?(?=\s+Dt:)',r'\1[Reference number]',new)
        if new!=old:changes.append({'paragraph':i,'text':new})
    return edit(data,changes)


def preview(data):
    _,tree=read(data);allp=tree.findall('.//w:p',NS);indices={id(p):i for i,p in enumerate(allp)}
    images={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if 'word/_rels/document.xml.rels' in z.namelist():
            for rel in ET.fromstring(z.read('word/_rels/document.xml.rels')):
                target=rel.attrib.get('Target','')
                if target.startswith('media/') and target.lower().endswith(('.jpg','.jpeg','.png')):
                    raw=z.read('word/'+target)
                    if len(raw)<=2*1024*1024:images[rel.attrib['Id']]={'mime':'image/png' if target.lower().endswith('.png') else 'image/jpeg','data':base64.b64encode(raw).decode()}
    def paragraph(p):
        align=p.find('w:pPr/w:jc',NS);runs=[]
        for r in p.findall('w:r',NS):
            size=r.find('w:rPr/w:sz',NS);font=r.find('w:rPr/w:rFonts',NS)
            flag=lambda name: r.find('w:rPr/w:'+name,NS) is not None and r.find('w:rPr/w:'+name,NS).get('{'+NS['w']+'}val','1') not in ('0','false','none')
            runs.append({'text':text(r),'bold':flag('b'),'italic':flag('i'),'underline':flag('u'),
                         'size':int(size.get('{'+NS['w']+'}val','24'))/2 if size is not None else 12,
                         'font':font.get('{'+NS['w']+'}ascii','Times New Roman') if font is not None else 'Times New Roman'})
        embedded=[images[n.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed']] for n in p.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip') if n.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed') in images]
        return {'type':'paragraph','index':indices[id(p)],'text':text(p),'alignment':align.get('{'+NS['w']+'}val','left') if align is not None else 'left','runs':runs,'images':embedded}
    blocks=[]
    for node in tree.find('w:body',NS):
        if node.tag=='{'+NS['w']+'}p':blocks.append(paragraph(node))
        elif node.tag=='{'+NS['w']+'}tbl':blocks.append({'type':'table','rows':[[[paragraph(p) for p in cell.findall('w:p',NS)] for cell in row.findall('w:tc',NS)] for row in node.findall('w:tr',NS)]})
    sect=tree.find('.//w:sectPr',NS);page={}
    if sect is not None:
        for tag in ('pgSz','pgMar'):
            el=sect.find('w:'+tag,NS)
            if el is not None:page[tag]={k.split('}')[-1]:v for k,v in el.attrib.items()}
    return {'blocks':blocks,'page':page}
