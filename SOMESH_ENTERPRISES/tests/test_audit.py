"""Additional audit coverage; all destructive operations use synthetic fixtures."""
import json
import unittest
import urllib.request
import urllib.error

from support import AppFixture


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture()
        self.admin = self.app.login()
        self.worker = self.app.login('Worker One')

    def tearDown(self):
        self.app.close()

    def test_task_deletion_and_template_edit_permissions(self):
        a = self.app
        task = a.task()
        other = a.task('Keep this task', owner='Worker Two')
        a.g['claim'](task, 'Worker One')
        before = a.g['get_task'](other)
        self.assertEqual(a.request(f'/api/admin-task/{task}/delete', {}, self.worker)[0], 403)
        self.assertEqual(a.request(f'/api/admin-task/{task}/delete', {}, self.admin)[0], 200)
        self.assertFalse(a.g['q']('SELECT id FROM tasks WHERE id=?', (task,)))
        self.assertEqual(a.g['get_task'](other), before)
        self.assertTrue(a.g['q']("SELECT id FROM events WHERE kind='deleted'"))
        template = {'name':'Synthetic edited task', 'hours':1.5, 'docs':True, 'about':'Edited before assignment'}
        self.assertEqual(a.request('/api/templates', {'templates':[template]}, self.worker)[0], 403)
        self.assertEqual(a.request('/api/templates', {'templates':[template]}, self.admin)[0], 200)
        self.assertEqual(a.request('/api/templates', token=self.admin)[1]['templates'], [template])

    def test_invalid_json_and_task_ids_return_client_errors(self):
        a = self.app
        request = urllib.request.Request(a.origin + '/api/login', data=b'{invalid', headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 400)
        for value in ('not-a-number', '-1', str(2**100)):
            self.assertEqual(a.request(f'/api/tasks/{value}/claim', {}, self.worker)[0], 400)
            self.assertEqual(a.request(f'/api/admin-task/{value}/delete', {}, self.admin)[0], 400)

    def test_sqlite_health_and_read_only_navigation(self):
        a = self.app
        task = a.task()
        before = a.g['get_task'](task)
        status, health = a.request('/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(health['database'], 'ok')
        self.assertEqual(health['version'], '2.0')
        self.assertNotIn(str(a.root), json.dumps(health))
        for path in ('/api/dashboard', '/api/tracker', '/api/timetable', '/api/adhoc', '/api/workflow', '/api/automation', '/api/rules', '/api/workflow-model', '/api/storage', '/api/action-center'):
            self.assertEqual(a.request(path, token=self.admin)[0], 200, path)
        self.assertEqual(a.g['get_task'](task), before)
        self.assertEqual(a.g['q']('PRAGMA integrity_check')[0]['integrity_check'], 'ok')
