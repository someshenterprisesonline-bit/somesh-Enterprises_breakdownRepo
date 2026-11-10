"""Inspect reference files without writing or copying their confidential cell data to docs.

Run from the project root: python tools/inspect_excel_references.py C:/path/to/references
"""
import json
import sys
import zipfile
from pathlib import Path
from collections import Counter
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from excel_workspace import metadata
import openpyxl

NAMES = ['538-OMCL-Open University -Sept-26(03-10-2026).xlsx', 'Oct-26-OMCL - TNOU.xlsx']


def inspect(root):
    report = {'workbooks': []}
    for name in NAMES:
        w = openpyxl.load_workbook(root / name)
        sheets = metadata(w)
        for s, m in zip(w, sheets):
            m['number_formats'] = dict(Counter(c.number_format for row in s for c in row if c.value is not None))
            m['formula_coordinates'] = [c.coordinate for row in s for c in row if c.data_type == 'f']
            m['column_dimensions'] = {k: {'width': d.width, 'hidden': d.hidden} for k, d in s.column_dimensions.items()}
            m['sheet_state'] = s.sheet_state
        report['workbooks'].append({'file': name, 'sheets': sheets})
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    name = '538-September-26-TN-Open University.docx'
    with zipfile.ZipFile(root / name) as z:
        tree = ET.fromstring(z.read('word/document.xml'))
        paragraphs = [''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in tree.findall('.//w:p', ns)]
    report['billing_reference'] = {'file': name, 'paragraphs': [p for p in paragraphs if p.strip()]}
    return report


if __name__ == '__main__':
    report = inspect(Path(sys.argv[1]))
    target = Path('data/excel-reference-analysis.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print('Reference analysis saved privately to', target)
