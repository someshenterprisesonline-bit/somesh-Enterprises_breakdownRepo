import json
import unittest
from support import AppFixture
import employee_management as EM


class EmployeeTests(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture()
        self.token = self.app.login()

    def tearDown(self):
        self.app.close()

    def post(self, **data):
        return self.app.request('/api/employees', data, self.token)

    def test_crud_persistence_duplicates_and_history(self):
        a = self.app
        data = dict(name='New Person', designation='Analyst', dept='Operations', access_role='employee')
        self.assertEqual(self.post(action='add', **data)[0], 200)
        self.assertEqual(self.post(action='add', **{**data, 'name': ' new   PERSON '})[0], 400)
        self.assertEqual(self.post(action='add', **{**data, 'name': ''})[0], 400)
        token = a.login('New Person')
        task = a.task(owner='New Person')
        a.g['claim'](task, 'New Person')
        self.assertEqual(self.post(action='edit', original='New Person', **{**data, 'name': 'Updated Person', 'dept': 'Finance'})[0], 200)
        self.assertEqual(a.request('/api/me', token=token)[0], 401)
        self.assertEqual(a.g['get_task'](task)['assignee'], 'Updated Person')
        self.assertEqual(a.g['q']('SELECT user FROM work_log WHERE task_id=?', (task,))[0]['user'], 'Updated Person')
        token = a.login('Updated Person')
        before = {t: a.g['q']('SELECT * FROM ' + t) for t in ('tasks', 'work_log', 'alerts')}
        self.assertEqual(self.post(action='delete', original='Updated Person')[0], 400)
        self.assertEqual(self.post(action='delete', original='Updated Person', confirmed=True)[0], 200)
        for table, records in before.items():
            self.assertEqual(a.g['q']('SELECT * FROM ' + table), records)
        self.assertEqual(a.request('/api/me', token=token)[0], 401)
        self.assertEqual(a.request('/api/login', {'user': 'Updated Person'})[0], 400)
        self.assertNotIn('Updated Person', [u['name'] for u in a.request('/api/meta')[1]['users']])
        EM.initialize(a.g)
        self.assertNotIn('Updated Person', a.g['USER_NAMES'])
        self.assertTrue(a.g['q']('SELECT deleted_at FROM employees WHERE name_key=?', ('updated person',))[0]['deleted_at'])
        self.assertEqual(a.request('/api/dashboard', token=self.token)[0], 200)
        self.assertEqual(a.request('/api/tracker', token=self.token)[0], 200)

    def test_direct_api_authorization_and_role_guards(self):
        a = self.app
        worker = a.login('Worker One')
        for token, expected in ((worker, 403), (None, 401)):
            self.assertEqual(a.request('/api/employees', token=token)[0], expected)
            for action in ('add', 'edit', 'delete'):
                self.assertEqual(a.request('/api/employees', {'action': action}, token)[0], expected)
        self.assertEqual(self.post(action='delete', original='Admin One', confirmed=True)[0], 400)
        data = dict(action='add', name='New Admin', designation='Lead', dept='Management', access_role='admin')
        self.assertEqual(self.post(**data)[0], 400)
        self.assertEqual(self.post(**data, confirmation_pin=a.pin)[0], 200)
        EM.initialize(a.g)
        self.assertTrue(a.g['is_admin']('New Admin'))

    def test_rename_keeps_document_permissions_and_reserves_old_identity(self):
        from test_document_workspace import seed_documents
        a = self.app
        info = seed_documents(a)
        EM.sync(a.g)
        old_token = info['employees']['Nandha']['token']
        bid = info['employees']['Nandha']['books']['worksheet']
        data = dict(name='Renamed Payroll', designation='Payroll', dept='Payroll', access_role='employee')
        self.assertEqual(self.post(action='edit', original='Nandha', **data)[0], 200)
        self.assertEqual(a.request('/api/me', token=old_token)[0], 401)
        token = a.login('Renamed Payroll')
        self.assertEqual(a.request('/api/excel', token=token)[0], 200)
        self.assertEqual(a.request('/api/excel/download?id=' + bid, token=token, binary=True)[0], 200)
        self.assertEqual(self.post(action='add', **{**data, 'name': 'Nandha'})[0], 400)
        EM.initialize(a.g)
        self.assertNotIn('Nandha', a.g['USER_NAMES'])
        parsed = dict(flow=a.g['FLOW'], users=[*a.g['USERS'], {'name':'Nandha','dept':'Payroll','role':'Employee'}])
        with self.assertRaises(a.g['FlowError']):
            a.g['apply_definitions'](parsed, 'Admin One', 'test', open_bills=False)
        self.assertNotIn('Nandha', a.g['USER_NAMES'])

    def test_failed_mirror_write_rolls_back_database_and_roster(self):
        a = self.app
        save = a.g['save']
        failed = False
        def failing(name, data):
            nonlocal failed
            if name == 'users.json' and not failed:
                failed = True
                raise OSError('Synthetic disk failure')
            return save(name, data)
        a.g['save'] = failing
        with self.assertRaises(OSError):
            EM.change(a.g, 'Admin One', dict(action='add', name='Rollback Person', designation='Tester', dept='Operations', access_role='employee'))
        self.assertNotIn('Rollback Person', a.g['USER_NAMES'])
        self.assertFalse(a.g['q']('SELECT name_key FROM employees WHERE name_key=?', ('rollback person',)))
