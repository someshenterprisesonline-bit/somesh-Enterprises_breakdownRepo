"""Bounded Excel arithmetic evaluator. Never executes Python or external formulas.

Only supported formulas produce values; missing inputs stay blank and unsupported
or erroneous expressions are pending. Imports are never evaluated on arrival.
"""
import io
import html
import re
import zipfile
from collections import defaultdict, deque
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries


class Missing(Exception): pass
class Pending(Exception): pass


class Calculator:
    def __init__(self, workbook):
        self.w = workbook
        self.memo = {}
        self.stack = set()
        self.budget = 300000

    def reference(self, text, sheet):
        if '!' in text:
            sheet, text = text.rsplit('!', 1)
            sheet = sheet.strip("'").replace("''", "'")
        if sheet not in self.w.sheetnames or not re.fullmatch(r'\$?[A-Z]{1,3}\$?[1-9][0-9]*(?::\$?[A-Z]{1,3}\$?[1-9][0-9]*)?', text):
            raise Pending()
        c1, r1, c2, r2 = range_boundaries(text)
        if (r2-r1+1)*(c2-c1+1) > 100000:
            raise Pending()
        keys = [(sheet, self.w[sheet].cell(r,c).coordinate) for r in range(r1,r2+1) for c in range(c1,c2+1)]
        return keys

    def cell(self, sheet, address):
        key = (sheet,address)
        if key in self.memo:
            return self.memo[key]
        self.budget -= 1
        if self.budget < 0 or key in self.stack or len(self.stack) > 100:
            raise Pending()
        c = self.w[sheet][address]
        if c.data_type != 'f':
            if c.value is None or c.value == '':
                return None
            if isinstance(c.value, (int,float,bool)):
                return Decimal(str(int(c.value) if isinstance(c.value,bool) else c.value))
            return c.value
        self.stack.add(key)
        try:
            if not any(t.subtype=='RANGE' for t in Tokenizer(c.value).items) and not any(x.value not in (None,'') and x.data_type!='f' for x in self.w[sheet].iter_rows(min_row=c.row,max_row=c.row).__next__()):
                raise Missing()
            value = self.expression(c.value, sheet)
            if not isinstance(value, (str,Decimal)):
                raise Pending()
            self.memo[key] = value
        except Missing:
            self.memo[key] = None
        except Exception:
            self.memo[key] = Pending
        finally:
            self.stack.discard(key)
        return self.memo[key]

    def expression(self, formula, sheet):
        tokens = [t for t in Tokenizer(formula).items if t.type != 'WHITE-SPACE']
        pos = 0
        def number(value):
            if value is None:
                raise Missing()
            if value is Pending:
                raise Pending()
            if isinstance(value,list):
                if len(value)!=1: raise Pending()
                return number(value[0])
            try: return Decimal(value)
            except Exception: raise Pending()
        def atom():
            nonlocal pos
            if pos >= len(tokens): raise Pending()
            t=tokens[pos];pos+=1
            if t.type=='OPERATOR-PREFIX' and t.value in ('+','-'):
                value=number(atom());return value if t.value=='+' else -value
            if t.type=='PAREN' and t.subtype=='OPEN':
                value=expr(0)
                if pos>=len(tokens) or tokens[pos].type!='PAREN' or tokens[pos].subtype!='CLOSE': raise Pending()
                pos+=1;return value
            if t.type=='FUNC' and t.subtype=='OPEN':
                name=t.value[:-1].upper();args=[]
                if name not in ('SUM','ROUND','MIN','MAX'):raise Pending()
                while pos<len(tokens) and not (tokens[pos].type=='FUNC' and tokens[pos].subtype=='CLOSE'):
                    args.append(expr(0))
                    if pos<len(tokens) and tokens[pos].type=='SEP':pos+=1
                    elif pos<len(tokens) and not(tokens[pos].type=='FUNC' and tokens[pos].subtype=='CLOSE'):raise Pending()
                if pos>=len(tokens):raise Pending()
                pos+=1
                if name=='SUM':
                    flat=[x for a in args for x in (a if isinstance(a,list) else [a])]
                    if any(x is Pending for x in flat):raise Pending()
                    nums=[x for x in flat if isinstance(x,Decimal)]
                    return sum(nums,Decimal(0)) if nums else None
                if name=='ROUND' and len(args)==2:
                    digits=int(number(args[1]))
                    if abs(digits)>20:raise Pending()
                    return number(args[0]).quantize(Decimal(10)**-digits,rounding=ROUND_HALF_UP)
                if name in ('MIN','MAX'):
                    nums=[number(x) for a in args for x in (a if isinstance(a,list) else [a]) if x is not None]
                    return (min(nums) if name=='MIN' else max(nums)) if nums else None
                raise Pending()
            if t.type=='OPERAND':
                if t.subtype=='NUMBER':return Decimal(t.value)
                if t.subtype=='TEXT':return t.value[1:-1].replace('""','"')
                if t.subtype=='LOGICAL':return Decimal(t.value=='TRUE')
                if t.subtype=='RANGE':
                    values=[self.cell(*key) for key in self.reference(t.value,sheet)]
                    return values if ':' in t.value else values[0]
            raise Pending()
        def expr(level):
            nonlocal pos
            left=atom()
            powers={'=':1,'<>':1,'<':1,'>':1,'<=':1,'>=':1,'&':2,'+':3,'-':3,'*':4,'/':4,'^':5}
            while pos<len(tokens):
                t=tokens[pos]
                if t.type=='OPERATOR-POSTFIX' and t.value=='%':
                    pos+=1;left=number(left)/100;continue
                if t.type!='OPERATOR-INFIX' or powers.get(t.value,0)<level or t.value not in powers:break
                pos+=1;right=expr(powers[t.value]+(0 if t.value=='^' else 1))
                if t.value=='&':left=str(left)+str(right);continue
                a=number(left);b=number(right)
                if t.value=='+':left=a+b
                elif t.value=='-':left=a-b
                elif t.value=='*':left=a*b
                elif t.value=='/':left=a/b
                elif t.value=='^':
                    if abs(b)>20:raise Pending()
                    left=a**b
                else:left=Decimal({'=':a==b,'<>':a!=b,'<':a<b,'>':a>b,'<=':a<=b,'>=':a>=b}[t.value])
            return left
        value=expr(0)
        if pos!=len(tokens):raise Pending()
        if value is None:raise Missing()
        return value

    def results(self):
        output={}
        for s in self.w:
            for row in s:
                for c in row:
                    if c.data_type!='f':continue
                    v=self.cell(s.title,c.coordinate)
                    status='pending' if v is Pending else ('blank' if v is None else 'ready')
                    output[(s.title,c.coordinate)]={'status':status,'value':str(v) if status=='ready' else ''}
        return output


def display(value,number_format):
    if value in ('',None):return ''
    try:
        n=Decimal(str(value));fmt=number_format.split(';')[0]
        if '%' in fmt:n*=100
        match=re.search(r'[0#][0#,]*(?:\.([0#]+))?',fmt)
        if not match:return str(value)
        places=len(match.group(1) or '')
        if places>15:return str(value)
        text=format(n.quantize(Decimal(10)**-places,rounding=ROUND_HALF_UP),(',' if ',' in fmt else '')+'.'+str(places)+'f')
        return text+('%' if '%' in fmt else '')
    except Exception:return str(value)


def cached(workbook):
    return {(s.title,c.coordinate):c.value for s in workbook for row in s for c in row if c.value is not None}


def affected(workbook, changes):
    """Dependency closure; unrelated imported formula caches remain untouched."""
    touched={(c['sheet'],c['address']) for c in changes};calc=Calculator(workbook);deps={}
    for s in workbook:
        for row in s:
            for c in row:
                if c.data_type!='f':continue
                refs=set()
                for t in Tokenizer(c.value).items:
                    if t.subtype=='RANGE':
                        try:refs.update(calc.reference(t.value,s.title))
                        except Pending:pass
                if not refs:refs.update((x['sheet'],x['address']) for x in changes if x['sheet']==s.title and re.search(r'\d+$',x['address']).group()==str(c.row))
                deps[(s.title,c.coordinate)]=refs
    reverse=defaultdict(list)
    for formula,references in deps.items():
        for reference in references:reverse[reference].append(formula)
    changed=set();queue=deque(touched)
    while queue:
        for formula in reverse[queue.popleft()]:
            if formula not in changed:changed.add(formula);queue.append(formula)
    return changed


def write_caches(data, results, previous=None):
    """Patch only formula <v> caches in freshly saved OOXML, retaining <f>."""
    previous=previous or {};ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(data)) as src:
        wb=ET.fromstring(src.read('xl/workbook.xml'))
        rel=ET.fromstring(src.read('xl/_rels/workbook.xml.rels'))
        targets={r.attrib['Id']:r.attrib['Target'] for r in rel}
        sheets={}
        for s in wb.find('s:sheets',ns):
            target=targets[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            sheets[target.lstrip('/') if target.startswith('/') else 'xl/'+target]=s.attrib['name']
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
            for item in src.infolist():
                raw=src.read(item.filename)
                if item.filename in sheets:
                    sheet=sheets[item.filename]
                    def patch(m):
                        cell=m.group();address=re.search(rb'\br="([^"]+)"',cell).group(1).decode()
                        if b'<f' not in cell:return cell
                        key=(sheet,address);r=results.get(key)
                        value=r['value'] if r and r['status']=='ready' else (previous.get(key) if r is None else None)
                        cell=re.sub(rb'\s+t="[^"]*"',b'',cell,count=1)
                        cell=re.sub(rb'<v(?:\s[^>]*)?>.*?</v>|<v\s*/>',b'',cell,flags=re.S)
                        if value is not None:
                            if isinstance(value,bool):
                                return cell.replace(b'<c ',b'<c t="b" ',1).replace(b'</c>',b'<v>'+str(int(value)).encode()+b'</v></c>')
                            try:Decimal(str(value))
                            except Exception:
                                kind=b'e' if str(value).startswith('#') else b'str'
                                return cell.replace(b'<c ',b'<c t="'+kind+b'" ',1).replace(b'</c>',b'<v>'+html.escape(str(value),quote=False).encode()+b'</v></c>')
                            cell=cell.replace(b'</c>',b'<v>'+str(value).encode()+b'</v></c>')
                        return cell
                    raw=re.sub(rb'<c\b[^>]*(?<!/)>.*?</c>',patch,raw,flags=re.S)
                dest.writestr(item,raw)
        return out.getvalue()
