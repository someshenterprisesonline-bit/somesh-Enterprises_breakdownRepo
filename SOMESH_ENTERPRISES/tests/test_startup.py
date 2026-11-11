"""Actual Windows BAT starts against synthetic data in a path containing spaces."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

from support import AppFixture, PROJECT, BACKEND
from launcher import healthy


@unittest.skipUnless(os.name == 'nt', 'Windows BAT tests')
class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='somesh startup spaces ')
        self.root = Path(self.temp.name)
        self.fixture = AppFixture()
        shutil.copytree(BACKEND, self.root / 'backend', ignore=shutil.ignore_patterns('config.json', 'users.json', 'workflow.json', '__pycache__'))
        for name in ('config.json', 'users.json', 'workflow.json'):
            shutil.copyfile(self.fixture.root / 'backend' / name, self.root / 'backend' / name)
        (self.root / 'frontend').mkdir()
        shutil.copyfile(PROJECT / 'frontend/index.html', self.root / 'frontend/index.html')
        for name in ('START SOMESH ENTERPRISES.bat', 'reset_demo_data_windows.bat'):
            shutil.copyfile(PROJECT / name, self.root / name)
        self.config = json.loads((self.root / 'backend/config.json').read_text())
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            self.port = probe.getsockname()[1]
        self.config['port'] = self.port
        self.write_config()
        self.url = f'http://127.0.0.1:{self.port}'
        self.process = None

    def write_config(self):
        (self.root / 'backend/config.json').write_text(json.dumps(self.config))

    def command(self, script='START SOMESH ENTERPRISES.bat', *args):
        return ['cmd', '/d', '/c', 'call', str(self.root / script), '--no-browser', '--no-pause', *args]

    def tearDown(self):
        if self.process and self.process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True, check=True)
            self.process.wait(timeout=15)
        self.fixture.close()
        for attempt in range(30):
            try:
                self.temp.cleanup()
                break
            except PermissionError:
                if attempt == 29: raise
                time.sleep(.1)

    def test_cold_start_reuse_and_demo_wrapper_preserve_data(self):
        self.process = subprocess.Popen(self.command(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            if healthy(self.url, self.root): break
            if self.process.poll() is not None: self.fail('BAT quit before becoming healthy')
            time.sleep(.1)
        self.assertTrue(healthy(self.url, self.root))
        for script in ('START SOMESH ENTERPRISES.bat', 'reset_demo_data_windows.bat'):
            result = subprocess.run(self.command(script), capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Reusing' if script.startswith('START') else 'Demo reload was NOT applied', result.stdout)
        import sqlite3
        with sqlite3.connect(self.root / 'data/monthly_cycle.db') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM bills').fetchone()[0], 0)
        db.close()

    def test_port_conflict_is_non_destructive_and_returns_failure(self):
        self.config['port'] = self.fixture.server.server_port
        self.write_config()
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('occupied by another server', result.stdout)
        self.assertEqual(self.fixture.request('/api/meta')[0], 200)
        self.assertFalse((self.root / 'data/monthly_cycle.db').exists())

    def test_demo_cold_start_uses_only_isolated_database(self):
        self.process = subprocess.Popen(self.command('reset_demo_data_windows.bat'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(300):
            if healthy(self.url, self.root): break
            if self.process.poll() is not None: self.fail('Demo BAT quit before becoming healthy')
            time.sleep(.1)
        self.assertTrue(healthy(self.url, self.root))
        import sqlite3
        with sqlite3.connect(self.root / 'data/monthly_cycle.db') as db:
            self.assertGreater(db.execute('SELECT count(*) FROM bills WHERE demo=1').fetchone()[0], 0)
        db.close()

    def test_missing_file_returns_failure(self):
        (self.root / 'frontend/index.html').unlink()
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing', result.stdout.lower())

    def test_fresh_checkout_creates_safe_config_and_requires_private_pin(self):
        for name in ('config', 'users', 'workflow'):
            (self.root / f'backend/{name}.json').unlink()
        env = dict(os.environ)
        env.pop('SOMESH_ADMIN_PIN', None)
        result = subprocess.run(self.command('START SOMESH ENTERPRISES.bat', '--check'), env=env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set SOMESH_ADMIN_PIN', result.stdout)
        self.assertEqual(json.loads((self.root / 'backend/config.json').read_text())['security']['admin_pin'], '')
        env['SOMESH_ADMIN_PIN'] = self.fixture.pin
        result = subprocess.run(self.command('START SOMESH ENTERPRISES.bat', '--check'), env=env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('database is missing',result.stdout)
        result = subprocess.run(self.command('START SOMESH ENTERPRISES.bat', '--check','--initialize'), env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
