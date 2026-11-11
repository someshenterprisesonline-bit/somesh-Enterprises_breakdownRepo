"""Read-only reference audit. Writes formula/format metadata, never employee values."""
import argparse
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path
import openpyxl
from openpyxl.formula.tokenizer import Tokenizer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from excel_calculation import Calculator
from excel_workspace import layout

def inspect(path):
    raw=Path(path).read_bytes();w=openpyxl.load_workbook(io.BytesIO(raw));cached=openpyxl.load_workbook(io.BytesIO(raw),data_only=True)
    calc=Calculator(w);results=calc.results();report={'sha256':hashlib.sha256(raw).hexdigest(),'sheets':{}}
    for s in w:
        formulas={c.coordinate:c.value for row in s for c in row if c.data_type=='f'}
        dependencies={}
        for address,formula in formulas.items():
            dependencies[address]=[list(key) for t in Tokenizer(formula).items if t.subtype=='RANGE' for key in calc.reference(t.value,s.title)]
        comparisons=[];missing=0
        for address in formulas:
            saved=cached[s.title][address].value;computed=results[(s.title,address)]
            if isinstance(saved,(int,float)):
                if computed['status']!='ready' or abs(float(computed['value'])-saved)>1e-7:comparisons.append(address)
            else:missing+=1
        info=layout(s)
        report['sheets'][s.title]={'dimensions':s.calculate_dimension(),'layout':info,'formula_count':len(formulas),'formulas':formulas,'dependencies':dependencies,'merged_cells':[str(r) for r in s.merged_cells.ranges], 'formats':dict(Counter(c.number_format for row in s for c in row if c.value is not None)), 'styles':dict(Counter(c.style_id for row in s for c in row if c.value is not None)), 'manual_cells':[c.coordinate for row in s for c in row if not isinstance(c,openpyxl.cell.cell.MergedCell) and c.data_type!='f' and c.row>info['header_end']], 'column_dimensions':{k:{'width':d.width,'hidden':d.hidden} for k,d in s.column_dimensions.items()}, 'row_dimensions':{k:{'height':d.height,'hidden':d.hidden} for k,d in s.row_dimensions.items()},'missing_saved_caches':missing,'cache_discrepancies':comparisons}
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('reference');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=inspect(args.reference);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    for name,sheet in report['sheets'].items():print(name,sheet['formula_count'],'formulas;',sheet['missing_saved_caches'],'missing saved caches; discrepancies:',sheet['cache_discrepancies'])
