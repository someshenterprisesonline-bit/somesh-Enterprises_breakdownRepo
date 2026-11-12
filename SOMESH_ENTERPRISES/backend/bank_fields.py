"""Bank identifier columns in Excel Workspace sheets (NEFT SHEET: ACCOUNT NUMBER and IFSC CODE).

Columns are found by their header text, never by a fixed letter, so reordered templates keep working.
- IFSC CODE: exactly 11 characters (surrounding spaces are ignored), always text. Never truncated.
- ACCOUNT NUMBER: digits only, any length, always text. Never converted to a number, rounded or trimmed of
  leading zeroes. Values Excel already rounded (stored as floating point or as "1.23457E+15") are reported,
  never repaired by guessing digits.
"""
import re

from openpyxl.cell.cell import MergedCell

IFSC_LENGTH = 11
IFSC_TITLE = 'VALIDATION ERROR'
IFSC_MESSAGE = 'IFSC Code must contain exactly 11 characters. Please check the entered IFSC Code.'
IFSC_REQUIRED = 'IFSC Code is required when an account number is entered. Please enter the 11-character IFSC Code.'
ACCOUNT_MESSAGE = 'Account Number must contain digits only (0-9). Please check the entered Account Number.'
ACCOUNT_DAMAGED = ('Account Number was rounded by Excel (shown as a number or in scientific notation), so digits are '
                   'missing. Format the ACCOUNT NUMBER column as Text in Excel, re-enter the full numbers and upload again.')
_ACCOUNT = re.compile(r'\b(?:account|a\s*/\s*c|acc?t)\.?\s*(?:no|number|num)\b', re.I)
_IFSC = re.compile(r'\bifsc\b', re.I)
_SCIENTIFIC = re.compile(r'^\s*[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+\s*$')


def column_kinds(header_rows, columns):
    """{column number: 'account' | 'ifsc'} from the joined header text of each column."""
    kinds = {}
    for col in range(1, columns + 1):
        text = ' '.join(str(row[col - 1] or '') for row in header_rows if col - 1 < len(row))
        if _IFSC.search(text):
            kinds[col] = 'ifsc'
        elif _ACCOUNT.search(text):
            kinds[col] = 'account'
    return kinds


def ifsc_problem(text):
    """None when valid, else {'message', 'length'}. Empty is checked separately (required rule)."""
    value = (text or '').strip()
    if value and len(value) != IFSC_LENGTH:
        return {'message': IFSC_MESSAGE, 'length': len(value)}
    return None


def account_problem(text):
    value = (text or '').strip()
    if not value:
        return None
    if _SCIENTIFIC.match(value):
        return {'message': ACCOUNT_DAMAGED}
    if not value.isdigit() or not value.isascii():
        return {'message': ACCOUNT_MESSAGE}
    return None


def account_text(value):
    """Exact text for a stored account number, or (None, problem) when Excel already lost digits."""
    if value is None or value == '':
        return '', None
    if isinstance(value, bool):
        return str(value), {'message': ACCOUNT_MESSAGE}
    if isinstance(value, int):
        return str(value), None
    if isinstance(value, float):
        # A double holds every integer below 10**15 exactly; Excel keeps 15 significant digits.
        if value.is_integer() and abs(value) < 10 ** 15:
            return str(int(value)), None
        return repr(value), {'message': ACCOUNT_DAMAGED}
    text = str(value)
    return text, account_problem(text)


def validation(field, sheet, address, problem, **extra):
    return {'field': field, 'title': IFSC_TITLE, 'sheet': sheet, 'address': address, **problem, **extra}


def scan(sheet, kinds, first_row, last_row):
    """Every invalid IFSC / damaged account number in data rows (used for uploads)."""
    problems = []
    for row in range(first_row, last_row + 1):
        for col, kind in kinds.items():
            cell = sheet.cell(row, col)
            if isinstance(cell, MergedCell) or cell.value is None or cell.data_type == 'f':
                continue
            if kind == 'ifsc':
                problem = ifsc_problem(str(cell.value))
            else:
                problem = account_text(cell.value)[1]
            if problem:
                problems.append(validation(kind, sheet.title, cell.coordinate, problem))
    return problems


def describe(problems, limit=5):
    parts = []
    for p in problems[:limit]:
        where = f"{p['sheet']} {p['address']}"
        parts.append(f"{where}: {p['length']} characters" if 'length' in p else where)
    more = len(problems) - limit
    return '; '.join(parts) + (f' (and {more} more)' if more > 0 else '')
