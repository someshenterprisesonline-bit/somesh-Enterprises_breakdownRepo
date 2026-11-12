"""Employee PC launcher and Employee PC Kit.

The batch file is run for real on Windows with SOMESH_LAUNCHER_TEST=1: it then prints "OPEN <url>" instead of
starting Chrome and answers "No" to every prompt, so no certificate is ever installed by the tests.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from support import AppFixture, PROJECT

sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'backend'))

BAT = PROJECT / 'OPEN SOMESH ENTERPRISES (Employee PC).bat'


def run_bat(folder, *args, timeout=90):
    env = dict(os.environ, SOMESH_LAUNCHER_TEST='1')
    p = subprocess.run(['cmd', '/d', '/c', 'call', str(Path(folder) / BAT.name), *args], cwd=folder, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).decode('mbcs' if os.name == 'nt' else 'utf-8', 'replace')


class LauncherSource(unittest.TestCase):
    """Static guarantees that hold on every platform."""

    def setUp(self):
        self.raw = BAT.read_bytes()
        self.text = self.raw.decode('ascii')

    def test_crlf_and_client_only(self):
        self.assertNotIn(b'\n', self.raw.replace(b'\r\n', b''), 'cmd.exe needs CRLF line endings')
        code = '\n'.join(l for l in self.text.splitlines() if not l.lower().startswith(('rem', 'echo')))
        for forbidden in ('python', 'py -3', 'node', 'npm', 'mysql', 'git ', 'app.py', 'launcher.py', '.db'):
            self.assertNotIn(forbidden, code.lower(), f'employee launcher must not run {forbidden!r}')

    def test_certificate_checks_are_never_bypassed(self):
        low = self.text.lower()
        for bypass in (' -k ', '--insecure', 'ignore-certificate-errors', 'servercertificatevalidationcallback',
                       'skipcertificatecheck', 'test-certificate-error'):
            self.assertNotIn(bypass, low)
        self.assertEqual(self.text.count('set "CA_SHA256="'), 1, 'repository copy carries an empty pin placeholder')
        # The CA is only installed after the pinned fingerprint matched and the user confirmed.
        install = self.text.index('certutil -user -addstore Root')
        self.assertLess(self.text.index(':askcert'), install)
        self.assertLess(self.text.index('choice /c YN'), install)
        self.assertIn('if not defined CA_SHA256 goto nopin', self.text)


class KitWriter(unittest.TestCase):
    def test_kit_pins_the_ca_fingerprint_and_holds_no_secrets(self):
        try:
            import make_office_cert as MC
            MC._crypto()
        except SystemExit:
            self.skipTest('cryptography not installed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(BAT, root / BAT.name)
            MC.make(root / 'certs', ['localhost', '127.0.0.1'])
            kit, fp = MC.write_kit(root, 'https://192.168.1.4:8443')
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes
            cert = x509.load_pem_x509_certificate((root / 'certs/office-ca.crt').read_bytes())
            self.assertEqual(fp, cert.fingerprint(hashes.SHA256()).hex().upper())
            bat = (kit / BAT.name).read_bytes()
            self.assertIn(f'set "CA_SHA256={fp}"'.encode(), bat)
            self.assertNotIn(b'\n', bat.replace(b'\r\n', b''))
            self.assertEqual(sorted(p.name for p in kit.iterdir()), sorted([BAT.name, 'office-ca.crt', 'somesh-server-url.txt']))
            self.assertEqual((kit / 'somesh-server-url.txt').read_text().strip(), 'https://192.168.1.4:8443')
            import zipfile
            with zipfile.ZipFile(kit.with_suffix('.zip')) as z:
                self.assertEqual(sorted(z.namelist()), sorted(f'{kit.name}/{n}' for n in (BAT.name, 'office-ca.crt', 'somesh-server-url.txt')))
                self.assertEqual(z.read(f'{kit.name}/{BAT.name}'), bat)


@unittest.skipUnless(os.name == 'nt', 'the launcher is a Windows batch file')
class LauncherRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = AppFixture()

    @classmethod
    def tearDownClass(cls):
        cls.app.close()

    def folder(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy2(BAT, tmp / BAT.name)
        return tmp

    def test_reachable_server_opens_the_shared_address_and_remembers_it(self):
        d = self.folder()
        rc, out = run_bat(d, self.app.origin)
        self.assertEqual(rc, 0, out)
        self.assertIn('[OK] The office server is answering', out)
        self.assertIn('OPEN ' + self.app.origin, out)
        self.assertEqual((d / 'somesh-server-url.txt').read_text().strip(), self.app.origin)
        rc, out = run_bat(d)  # second start: the remembered address is used
        self.assertEqual(rc, 0, out)
        self.assertIn('OPEN ' + self.app.origin, out)
        self.assertFalse(any(p.suffix in ('.db', '.json') for p in d.iterdir()), 'no local database or settings')

    def test_unreachable_server_shows_a_clear_error(self):
        import socket
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        rc, out = run_bat(self.folder(), f'http://127.0.0.1:{port}')
        self.assertEqual(rc, 2, out)
        self.assertIn('cannot be reached', out)
        self.assertIn('SERVER MODE window', out)
        self.assertNotIn('OPEN ', out)

    def test_bad_address_is_refused(self):
        d = self.folder()
        rc, out = run_bat(d, 'http://bad host/&calc')
        self.assertEqual(rc, 1, out)
        self.assertIn('does not look like an address', out)
        self.assertFalse((d / 'somesh-server-url.txt').exists())

    def test_wrong_certificate_is_never_installed(self):
        try:
            import make_office_cert as MC
            MC._crypto()
        except SystemExit:
            self.skipTest('cryptography not installed')
        root = self.folder()
        MC.make(root / 'certs', ['localhost'])
        kit, fp = MC.write_kit(root, self.app.origin, kit=root / 'kit')
        # Swap in a different (attacker's) CA with the same name: the pin no longer matches.
        other = self.folder()
        MC.make(other / 'certs', ['localhost'])
        shutil.copy2(other / 'certs/office-ca.crt', kit / 'office-ca.crt')
        rc, out = run_bat(kit, 'https://127.0.0.1:9')
        self.assertIn('is NOT the office certificate', out)
        self.assertIn('MISMATCH', out)
        self.assertNotIn('Install the office certificate now', out)
        # The genuine kit CA is recognised and offered (test mode answers No, so nothing is installed).
        shutil.copy2(root / 'certs/office-ca.crt', kit / 'office-ca.crt')
        rc, out = run_bat(kit, 'https://127.0.0.1:9')
        self.assertIn(fp, out)
        self.assertNotIn('is NOT the office certificate', out)
        self.assertIn('does not trust the office HTTPS certificate yet', out)  # a fresh test CA is never trusted
        self.assertIn('Not installed', out)

    def test_launcher_without_pin_refuses_to_install(self):
        d = self.folder()
        (d / 'office-ca.crt').write_text('-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n')
        rc, out = run_bat(d, 'https://127.0.0.1:9')
        self.assertIn('no pinned fingerprint', out)
        self.assertNotIn('Install the office certificate now', out)


if __name__ == '__main__':
    unittest.main()
