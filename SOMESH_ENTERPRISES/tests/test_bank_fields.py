"""NEFT SHEET bank fields: IFSC Code is exactly 11 characters; ACCOUNT NUMBER is exact text through the whole lifecycle.

Synthetic data only (AppFixture temporary database). Never touches data/monthly_cycle.db.
"""
import base64
import io
import sys
import unittest
from urllib.parse import urlencode

import openpyxl
from support import AppFixture, BACKEND
from test_excel_workspace import add_employees
import test_neft_sync as NT
from test_neft_sync import neft_file, worksheet_file

sys.path.insert(0, str(BACKEND))
import bank_fields as BANK  # noqa: E402

IFSC_MSG = 'IFSC Code must contain exactly 11 characters. Please check the entered IFSC Code.'
ACCOUNTS = {  # label -> exact digits (stored and shown as text, never a number)
    '10 digits': '1234567890',
    '16 digits': '1234567890123456',
    '20 digits': '12345678901234567890',
    '30 digits': '123456789012345678901234567890',
    'leading zero': '000012345678901234',
}


def neft_with(accounts=None, ifsc=None, numeric_accounts=()):
    """A NEFT upload; `numeric_accounts` are written as real Excel numbers (as many old files have them)."""
    w = openpyxl.Workbook(); s = w.active; s.title = 'NEFT'
    s.append(['S.No', 'Name', 'Designation', 'Bank', 'Account Number', 'Branch', 'IFSC Code', 'Salary Amount', 'Remarks'])
    accounts = list(accounts or ['0001', '0002', '0003'])
    for i, account in enumerate(accounts):
        s.append([i + 1, f'Employee {i + 1:03}', 'Guard', 'Bank', account, 'Branch',
                  (ifsc or {}).get(i, f'SBIN{i:07d}'), 1000 + i, ''])
        if isinstance(account, str):
            s.cell(i + 2, 5).number_format = '@'
    for i, number in enumerate(numeric_accounts, len(accounts)):
        s.append([i + 1, f'Employee {i + 1:03}', 'Guard', 'Bank', number, 'Branch', f'SBIN{i:07d}', 1000 + i, ''])
    out = io.BytesIO(); w.save(out); return out.getvalue()


class BankFieldRules(unittest.TestCase):
    def test_column_detection_and_rules(self):
        kinds = BANK.column_kinds([['S.No', 'Name', 'Designation', 'BANK NAME', 'ACCOUNT NUMBER', 'BRANCH', 'IFSC CODE', 'Salary']], 8)
        self.assertEqual(kinds, {5: 'account', 7: 'ifsc'})
        self.assertEqual(BANK.column_kinds([['A/C No', 'Acct. Number', 'ifsc']], 3), {1: 'account', 2: 'account', 3: 'ifsc'})
        for n in (5, 10, 12, 15):
            self.assertEqual(BANK.ifsc_problem('S' * n), {'message': IFSC_MSG, 'length': n})
        self.assertIsNone(BANK.ifsc_problem('SBIN0001234'))
        self.assertIsNone(BANK.ifsc_problem('  SBIN0001234  '), 'surrounding spaces are not characters of the code')
        self.assertEqual(BANK.account_text(123456789012345), ('123456789012345', None))
        self.assertEqual(BANK.account_text(1234567890.0), ('1234567890', None))
        self.assertIsNotNone(BANK.account_text(1.2345678901234568e16)[1], 'rounded float reported, not repaired')
        self.assertIsNotNone(BANK.account_problem('1.23457E+15'))
        self.assertIsNotNone(BANK.account_problem('12 34'))
        self.assertIsNone(BANK.account_problem('0' * 40))


class BankFieldApi(unittest.TestCase):
    # reuse the NEFT test helpers (upload, save, grid, book, pair, ...)
    for _name in ('post', 'upload', 'meta', 'grid', 'save', 'pair', 'book'):
        locals()[_name] = getattr(NT.NeftSyncTests, _name)

    def setUp(self):
        self.app = AppFixture(); add_employees(self.app); self.admin = self.app.login(); self.user = self.app.login('Nandha')
        self.master_neft = self.upload(neft_file(), 'neft', master=True)
        self.master_work = self.upload(worksheet_file(), 'worksheet', master=True)

    def tearDown(self):
        self.app.close()

    def cell(self, bid, address, sheet='NEFT'):
        for row in self.grid(bid, sheet)['rows']:
            for c in row['cells']:
                if c['address'] == address:
                    return c
        raise AssertionError(address)

    def change(self, address, value):
        return dict(sheet='NEFT', address=address, value=value, type='text')

    # ------------------------------------------------------------------ IFSC
    def test_ifsc_must_be_exactly_11_characters_on_save(self):
        bid = self.upload(neft_with(), 'neft')
        for n in (5, 10, 12, 15):
            value = ('SBIN0' + '1' * 20)[:n]
            status, r = self.save(bid, [self.change('G2', value)])
            self.assertEqual(status, 400, r)
            self.assertEqual(r['error'], IFSC_MSG)
            v = r['validation']
            self.assertEqual((v['field'], v['title'], v['sheet'], v['address'], v['length'], v['value']),
                             ('ifsc', 'VALIDATION ERROR', 'NEFT', 'G2', n, value))
            self.assertEqual(self.cell(bid, 'G2')['value'], 'SBIN0000000', 'invalid IFSC never reaches the database')
        status, r = self.save(bid, [self.change('G2', '  0BIN0001234 ')])
        self.assertEqual(status, 200, r)
        stored = self.cell(bid, 'G2')
        self.assertEqual((stored['value'], stored['type']), ('0BIN0001234', 's'), 'leading zero kept, stored as text, spaces trimmed')
        self.assertEqual(self.book(bid)['NEFT']['G2'].value, '0BIN0001234')

    def test_ifsc_is_required_when_an_account_number_is_entered(self):
        bid = self.upload(neft_with(), 'neft')
        status, r = self.save(bid, [self.change('G2', '')])  # removing the IFSC of a row with an account number
        self.assertEqual(status, 400, r)
        self.assertEqual((r['validation']['address'], r['validation']['required']), ('G2', True))
        self.assertIn('required', r['error'])
        self.assertEqual(self.cell(bid, 'G2')['value'], 'SBIN0000000')
        # A row still being filled in (account first, IFSC later) saves, so autosave never loses progress.
        status, r = self.save(bid, [self.change('E5', '9876543210')])
        self.assertEqual(status, 200, r)
        status, r = self.save(bid, [self.change('G5', 'HDFC0001234')])
        self.assertEqual(status, 200, r)
        status, r = self.save(bid, [self.change('E2', ''), self.change('G2', '')])  # clearing both is allowed
        self.assertEqual(status, 200, r)

    def test_a_rejected_batch_changes_nothing_and_typing_is_not_interrupted(self):
        bid = self.upload(neft_with(), 'neft')
        status, r = self.save(bid, [self.change('B2', 'Renamed'), self.change('G3', 'SBIN01')])
        self.assertEqual(status, 400, r)
        self.assertEqual(self.cell(bid, 'B2')['value'], 'Employee 001', 'atomic: the browser keeps the whole draft')
        # Live recalculation runs while the user is still typing: it must not raise the IFSC error.
        status, r = self.post('calculate', dict(id=bid, revision=self.meta(bid)['book']['revision'], changes=[self.change('G3', 'SBI')]))
        self.assertEqual(status, 200, r)

    def test_invalid_ifsc_upload_is_refused_with_the_cells_to_fix(self):
        data = neft_with(ifsc={0: 'SBIN01', 2: 'SBIN000000001'})
        status, r = self.post('preview', {'name': 'neft.xlsx', 'data': base64.b64encode(data).decode()})
        self.assertEqual(status, 400, r)
        v = r['validation']
        self.assertEqual((v['field'], v['upload'], v['count'], v['address'], v['length']), ('ifsc', True, 2, 'G2', 6))
        self.assertIn('NEFT G2: 6 characters; NEFT G4: 13 characters', r['error'])
        self.assertIn('not uploaded', r['error'])
        pending = self.app.g['DB'].execute('SELECT COUNT(*) FROM ew_pending WHERE actor=?', ('Nandha',)).fetchone()[0]
        self.assertEqual(pending, 0, 'nothing stored for a refused upload')

    # ------------------------------------------------------------------ account numbers
    def test_account_numbers_stay_exact_text_through_save_reload_download_and_reimport(self):
        bid = self.upload(neft_with(['1', '2', '3', '4', '5']), 'neft')
        changes = [self.change(f'E{i + 2}', v) for i, v in enumerate(ACCOUNTS.values())]
        status, r = self.save(bid, changes)
        self.assertEqual(status, 200, r)
        for i, (label, digits) in enumerate(ACCOUNTS.items()):
            c = self.cell(bid, f'E{i + 2}')
            self.assertEqual((c['value'], c['type']), (digits, 's'), label)
        sheet = self.book(bid)['NEFT']
        for i, (label, digits) in enumerate(ACCOUNTS.items()):
            c = sheet.cell(i + 2, 5)
            self.assertEqual((c.value, c.data_type, c.number_format), (digits, 's', '@'), label + ' downloads as an Excel Text cell')
        out = io.BytesIO(); sheet.parent.save(out)
        again = self.upload(out.getvalue(), 'neft')
        for i, (label, digits) in enumerate(ACCOUNTS.items()):
            self.assertEqual(self.cell(again, f'E{i + 2}')['value'], digits, label + ' after re-import')

    def test_numeric_account_numbers_from_old_files_show_and_download_exactly(self):
        bid = self.upload(neft_with(['0001'], numeric_accounts=[123456789012345, 9876543210, 1234567890.0]), 'neft')
        self.assertEqual([self.cell(bid, a)['value'] for a in ('E3', 'E4', 'E5')], ['123456789012345', '9876543210', '1234567890'])
        sheet = self.book(bid)['NEFT']
        self.assertEqual([(sheet[a].value, sheet[a].number_format) for a in ('E3', 'E4', 'E5')],
                         [('123456789012345', '@'), ('9876543210', '@'), ('1234567890', '@')])

    def test_regenerated_downloads_are_byte_stable(self):
        """Downloads rebuilt on the fly (numeric account numbers -> Text cells; blank-origin workbooks) used to carry
        the current time in each ZIP entry, so two downloads of an unchanged document differed after 2 seconds."""
        import time
        numeric = self.upload(neft_with(['0001'], numeric_accounts=[123456789012345]), 'neft')
        status, b = self.post('blank', {'id': self.master_neft}); self.assertEqual(status, 200, b)
        raw = lambda bid: self.app.request('/api/excel/download?' + urlencode(dict(id=bid)), token=self.user, binary=True)[1]
        first = {bid: raw(bid) for bid in (numeric, b['id'])}
        time.sleep(2.2)  # ZIP timestamps have 2-second resolution
        for bid, data in first.items():
            self.assertEqual(raw(bid), data, 'same document, same bytes')
        self.assertEqual(self.book(numeric)['NEFT']['E3'].value, '123456789012345')

    def test_account_numbers_rounded_by_excel_are_reported_not_invented(self):
        for bad in (1.2345678901234568e16, '1.23457E+15'):
            status, r = self.post('preview', {'name': 'neft.xlsx', 'data': base64.b64encode(neft_with(['0001'], numeric_accounts=[bad]) if isinstance(bad, float) else neft_with([bad])).decode()})
            self.assertEqual(status, 400, (bad, r))
            self.assertEqual(r['validation']['field'], 'account')
            self.assertIn('rounded by Excel', r['error'])

    def test_account_number_digits_only(self):
        bid = self.upload(neft_with(), 'neft')
        for bad in ('ABC123', '1234 5678', '12-34', '1.2e5'):
            status, r = self.save(bid, [self.change('E2', bad)])
            self.assertEqual((status, r['validation']['field']), (400, 'account'), bad)
        self.assertEqual(self.cell(bid, 'E2')['value'], '0001')

    def test_worksheet_sync_keeps_bank_fields_exact(self):
        status, b = self.post('blank', {'id': self.master_neft}); self.assertEqual(status, 200, b); bid = b['id']
        changes = []
        for i, digits in enumerate(ACCOUNTS.values()):
            changes += [self.change(f'A{i + 2}', str(i + 1)), self.change(f'B{i + 2}', f'Person {i:03}'), self.change(f'C{i + 2}', 'Guard'),
                        self.change(f'E{i + 2}', digits), self.change(f'G{i + 2}', f'SBIN{i:07d}')]
        status, r = self.save(bid, changes); self.assertEqual(status, 200, r)
        target = self.pair(bid)
        status, r = self.save(target, [dict(sheet='Worksheet', address='E2', value='777', type='number')])
        self.assertEqual(status, 200, r)
        for i, digits in enumerate(ACCOUNTS.values()):
            self.assertEqual(self.cell(bid, f'E{i + 2}')['value'], digits)
            self.assertEqual(self.cell(bid, f'G{i + 2}')['value'], f'SBIN{i:07d}')


if __name__ == '__main__':
    unittest.main()
