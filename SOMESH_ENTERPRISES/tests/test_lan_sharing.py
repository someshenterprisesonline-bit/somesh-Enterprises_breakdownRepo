"""Shared-host (office LAN) behaviour: access restriction, same-origin POSTs, sessions, live sync, HTTPS, backup/restore."""
import gzip
import json
import queue
import socket
import sqlite3
import ssl
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from support import AppFixture, PROJECT
from test_excel_workspace import EMPLOYEES, seed

sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'backend'))
import lan as LAN  # noqa: E402


def drain(qu):
    out = []
    while True:
        try:
            out.append(qu.get_nowait())
        except queue.Empty:
            return out


class NetworkRules(unittest.TestCase):
    def test_default_allows_loopback_and_private_ranges_only(self):
        net = LAN.settings({})
        for ip in ('127.0.0.1', '::1', '192.168.1.25', '10.4.0.9', '172.20.1.1', '::ffff:192.168.0.7', 'fe80::1%12'):
            self.assertTrue(LAN.client_allowed(ip, net), ip)
        for ip in ('8.8.8.8', '172.32.0.1', '2001:4860::8888', 'not-an-ip'):
            self.assertFalse(LAN.client_allowed(ip, net), ip)

    def test_configured_networks_replace_defaults(self):
        net = LAN.settings({'network': {'allowed_networks': ['127.0.0.1/32', '192.168.50.0/24', 'bogus']}})
        self.assertTrue(LAN.client_allowed('192.168.50.9', net))
        self.assertFalse(LAN.client_allowed('192.168.1.9', net))

    def test_origin_rules(self):
        self.assertTrue(LAN.origin_ok(None, '192.168.1.5:8080'))
        self.assertTrue(LAN.origin_ok('http://192.168.1.5:8080', '192.168.1.5:8080'))
        self.assertTrue(LAN.origin_ok('https://ADMIN-PC:8443', 'admin-pc:8443'))
        self.assertFalse(LAN.origin_ok('http://evil.example', '192.168.1.5:8080'))
        self.assertFalse(LAN.origin_ok('null', '192.168.1.5:8080'))
        self.assertTrue(LAN.origin_ok('https://intranet.example', 'x:1', {'https://intranet.example'}))

    def test_redirect_host_is_sanitised(self):
        self.assertEqual(LAN.host_only('192.168.1.5:8080'), '192.168.1.5')
        self.assertEqual(LAN.host_only('admin-pc'), 'admin-pc')
        self.assertIsNone(LAN.host_only('evil.example/@x'))
        self.assertIsNone(LAN.host_only('[::1]:8080'))


class SharedHost(unittest.TestCase):
    def setUp(self):
        self.app = AppFixture()

    def tearDown(self):
        self.app.close()

    def raw(self, path, body=None, headers=None):
        req = urllib.request.Request(self.app.origin + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_requests_from_outside_the_office_network_are_refused(self):
        g = self.app.g
        g['NET']['networks'] = LAN.settings({'network': {'allowed_networks': ['10.99.0.0/16']}})['networks']
        status, _, body = self.raw('/api/meta')
        self.assertEqual(status, 403)
        self.assertIn('approved office network', json.loads(body)['error'])
        status, _, _ = self.raw('/api/login', {'user': 'Worker One'})
        self.assertEqual(status, 403)

    def test_cross_site_post_is_blocked_and_same_origin_post_works(self):
        status, _, body = self.raw('/api/login', {'user': 'Worker One'}, {'Origin': 'http://evil.example'})
        self.assertEqual((status, json.loads(body)['error']), (403, 'Cross-site request blocked.'))
        host = self.app.origin.split('//')[1]
        status, _, body = self.raw('/api/login', {'user': 'Worker One'}, {'Origin': self.app.origin, 'Host': host})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['token'])

    def test_security_headers_and_gzip(self):
        status, headers, _ = self.raw('/')
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(headers.get('Referrer-Policy'), 'no-referrer')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        token = self.app.login()
        self.app.seed_browser()
        status, headers, body = self.raw('/api/pipeline', headers={'X-Session': token, 'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200)
        if headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        self.assertIn('bills', json.loads(body))
        status, headers, body = self.raw('/api/meta', headers={'Accept-Encoding': 'gzip'})
        meta = json.loads(gzip.decompress(body) if headers.get('Content-Encoding') == 'gzip' else body)
        self.assertIn('users', meta)

    def test_sessions_expire(self):
        token = self.app.login('Worker One')
        self.assertEqual(self.app.request('/api/me', token=token)[0], 200)
        self.app.g['x']("UPDATE sessions SET created_at='2020-01-01 00:00:00' WHERE token=?", (token,))
        status, body = self.app.request('/api/me', token=token)
        self.assertEqual((status, body.get('login')), (401, True))
        self.assertEqual(self.app.g['q']('SELECT COUNT(*) n FROM sessions WHERE token=?', (token,))[0]['n'], 0)

    def test_live_messages_are_sequenced_and_admin_changes_reach_other_admins(self):
        g = self.app.g
        admin2, worker = g['queue'].Queue(), g['queue'].Queue()
        g['SUBS'].setdefault('Admin Two', []).append(admin2); g['SUBS'].setdefault('Worker One', []).append(worker)
        token = self.app.login()
        status, _ = self.app.request('/api/templates', {'templates': [{'name': 'Live template', 'hours': 1}]}, token)
        self.assertEqual(status, 200)
        got = drain(admin2)
        self.assertTrue(any(m['type'] == 'refresh' for m in got))
        self.assertTrue(all(m['boot'] == g['BOOT'] and isinstance(m['seq'], int) for m in got))
        self.assertEqual(drain(worker), [])  # employees do not need admin configuration refreshes
        tid = self.app.task('Shared task', 'Worker One')
        drain(admin2)
        wtoken = self.app.login('Worker One')
        self.assertEqual(self.app.request(f'/api/tasks/{tid}/claim', {}, wtoken)[0], 200)
        seqs = [m['seq'] for m in drain(admin2)]
        self.assertTrue(seqs, 'another admin sees the employee starting the task')
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_excel_saves_notify_owner_and_admins_only_after_success(self):
        data = seed(self.app)
        g = self.app.g
        owner, other = EMPLOYEES[0][0], EMPLOYEES[1][0]
        queues = {name: g['queue'].Queue() for name in (owner, other, 'Admin Two')}
        for name, qu in queues.items():
            g['SUBS'].setdefault(name, []).append(qu)
        mine = data['employees'][owner]
        status, result = self.app.request('/api/excel/save', {'id': mine['id'], 'revision': 1,
                                                              'changes': [{'sheet': 'Payroll', 'address': 'D3', 'value': '500'}]}, mine['token'])
        self.assertEqual(status, 200, result)
        for name in (owner, 'Admin Two'):
            msgs = [m for m in drain(queues[name]) if m['type'] == 'excel_changed']
            self.assertEqual([(m['id'], m['revision'], m['actor']) for m in msgs], [(mine['id'], result['revision'], owner)], name)
        self.assertEqual([m for m in drain(queues[other]) if m['type'] == 'excel_changed'], [])
        # A stale save is rejected (conflict) and announces nothing.
        status, _ = self.app.request('/api/excel/save', {'id': mine['id'], 'revision': 1,
                                                         'changes': [{'sheet': 'Payroll', 'address': 'D3', 'value': '600'}]}, mine['token'])
        self.assertEqual(status, 400)
        self.assertEqual([m for m in drain(queues['Admin Two']) if m['type'] == 'excel_changed'], [])

    def test_ca_certificate_download(self):
        status, _, _ = self.raw('/office-ca.crt')
        self.assertEqual(status, 404)
        certs = self.app.root / 'certs'
        certs.mkdir()
        (certs / 'office-ca.crt').write_text('-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n')
        status, headers, body = self.raw('/office-ca.crt')
        self.assertEqual((status, headers['Content-Type']), (200, 'application/x-x509-ca-cert'))
        self.assertIn(b'BEGIN CERTIFICATE', body)


class HttpsListener(unittest.TestCase):
    def test_https_serves_the_app_with_the_office_ca(self):
        import make_office_cert as MC
        app = AppFixture()
        try:
            certs = app.root / 'certs'
            MC.make(certs, ['localhost', '127.0.0.1'])
            ctx = LAN.tls_context(str(certs / 'server.crt'), str(certs / 'server.key'))
            srv = LAN.TLSServer(('127.0.0.1', 0), app.g['HS'], ctx)
            threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': .02}, daemon=True).start()
            try:
                port = srv.server_address[1]
                client = ssl.create_default_context(cafile=str(certs / 'office-ca.crt'))
                with urllib.request.urlopen(f'https://localhost:{port}/api/health', context=client, timeout=10) as r:
                    self.assertEqual(json.load(r)['database'], 'ok')
                with urllib.request.urlopen(f'https://127.0.0.1:{port}/', context=client, timeout=10) as r:
                    self.assertIn(b'<html', r.read().lower())
                with self.assertRaises(urllib.error.URLError):  # untrusted without the office CA
                    urllib.request.urlopen(f'https://localhost:{port}/api/health', context=ssl.create_default_context(), timeout=10)
                with socket.create_connection(('127.0.0.1', port), timeout=5) as s:  # plain HTTP on the TLS port is dropped quietly
                    s.sendall(b'GET / HTTP/1.0\r\n\r\n')
                    s.recv(100)
                with urllib.request.urlopen(f'https://localhost:{port}/api/health', context=client, timeout=10) as r:
                    self.assertEqual(r.status, 200)  # still serving after the bad client
            finally:
                srv.shutdown(); srv.server_close()
            created_again, _ = MC.make(certs, ['localhost'])
            self.assertFalse(created_again, 'the office CA is reused so employee PCs keep trusting it')
        finally:
            app.close()


class BackupRestore(unittest.TestCase):
    def test_online_backup_and_guarded_restore(self):
        import backup_db
        import restore_db
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir(); (root / 'backend').mkdir()
            (root / 'backend/config.json').write_text(json.dumps({'port': 1}), encoding='utf-8')
            db = sqlite3.connect(root / 'data/monthly_cycle.db')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT)')
            db.execute("INSERT INTO tasks(title) VALUES ('kept')"); db.commit()
            folder = backup_db.backup(root, 'nightly', keep=2)  # while a writer holds the WAL database open
            manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual((manifest['integrity'], manifest['rows']['tasks']), ('ok', 1))
            self.assertTrue((folder / 'config.json').is_file())
            for _ in range(3):
                folder = backup_db.backup(root, 'nightly', keep=2)
            self.assertEqual(len(list((root / 'data/backups').glob('nightly-*'))), 2)
            db.execute("INSERT INTO tasks(title) VALUES ('later')"); db.commit(); db.close()
            safety, _ = restore_db.restore(root, folder)
            with sqlite3.connect(root / 'data/monthly_cycle.db') as check:
                self.assertEqual([r[0] for r in check.execute('SELECT title FROM tasks')], ['kept'])
            check.close()
            with sqlite3.connect(safety / 'monthly_cycle.db') as pre:
                self.assertEqual(pre.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 2)
            pre.close()
            from unittest import mock
            with mock.patch.object(restore_db, 'server_running', return_value=None):
                self.assertEqual(restore_db.main([str(folder)]), 2)  # refuses without --yes
            with mock.patch.object(restore_db, 'server_running', return_value=8080):
                self.assertEqual(restore_db.main([str(folder), '--yes']), 2)  # refuses while the app runs

    def test_launcher_check_reports_database_and_https_problems(self):
        import launcher
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'data').mkdir()
            self.assertEqual(launcher.check_database(root), 'new')
            sqlite3.connect(root / 'data/monthly_cycle.db').close()
            self.assertEqual(launcher.check_database(root), 'ok')
            (root / 'data/monthly_cycle.db').write_bytes(b'SQLite format 3\x00' + b'\x00' * 200)
            with self.assertRaises(Exception):
                launcher.check_database(root)


if __name__ == '__main__':
    unittest.main()
