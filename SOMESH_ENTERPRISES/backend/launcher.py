"""SERVER MODE entry point for the Admin PC (START SOMESH ENTERPRISES.bat).

Reuses this checkout's healthy server and never kills port owners. Before starting a new server it checks the files,
Python packages, settings, HTTPS certificate, database integrity and ports, then makes an automatic online backup
(data/backups/startup-*, newest 14 kept) because the server applies additive schema migrations when it starts.
It never resets or reseeds data; demo bills load only with --demo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def instance_id(root):
    return hashlib.sha256(os.path.normcase(os.path.realpath(root)).encode()).hexdigest()[:20]


def healthy(url, root=ROOT):
    try:
        with urllib.request.urlopen(url + '/api/health', timeout=2) as response:
            data = json.load(response)
        return data.get('app') == 'SOMESH ENTERPRISES' and data.get('instance') == instance_id(root) and data.get('database') == 'ok'
    except (OSError, ValueError, urllib.error.URLError):
        return False


def lan_urls(config):
    import lan as LAN
    port = int(config.get('port', 8080))
    https = LAN.settings(config)['https']
    urls = []
    for ip in LAN.lan_ipv4():
        if https['enabled']: urls.append(f"https://{ip}:{https['port']}")
        if not (https['enabled'] and https['redirect_lan_http']): urls.append(f'http://{ip}:{port}')
    return urls


def print_addresses(config, browser_url):
    print('', flush=True)
    print('  On this Admin PC:   ' + browser_url, flush=True)
    urls = lan_urls(config)
    for u in urls:
        print('  Employee PCs:       ' + u, flush=True)
    if not urls:
        print('  Employee PCs:       no LAN address found. Connect this PC to the office network.', flush=True)
    public = str((config.get('network') or {}).get('public_url') or '')
    if public:
        print('  Office address:     ' + public, flush=True)
    if os.name == 'nt':
        try:
            r = subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule', 'name=SOMESH ENTERPRISES (LAN)'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if r.returncode != 0:
                print('  Firewall:           no "SOMESH ENTERPRISES (LAN)" rule. If employee PCs cannot connect, run as', flush=True)
                print('                      Administrator: powershell -ExecutionPolicy Bypass -File tools\\office_firewall.ps1', flush=True)
        except (OSError, subprocess.SubprocessError):
            pass
    print('', flush=True)


def check_database(root=ROOT):
    db = Path(root) / 'data/monthly_cycle.db'
    if not db.is_file():
        return 'new'
    import sqlite3
    con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True, timeout=10)
    try:
        result = con.execute('PRAGMA quick_check').fetchone()[0]
    finally:
        con.close()
    if result != 'ok':
        raise ValueError('Database check failed (' + str(result)[:120] + '). Restore a backup: see README, Backup and recovery')
    return 'ok'


def startup_backup(root=ROOT):
    if not (Path(root) / 'data/monthly_cycle.db').is_file():
        return None
    sys.path.insert(0, str(Path(root) / 'tools'))
    from backup_db import backup
    return backup(root, 'startup', keep=14)


def open_browser(url):
    candidates = [shutil.which('chrome')]
    for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        candidates.append(str(Path(os.environ.get(base, '')) / 'Google/Chrome/Application/chrome.exe'))
    chrome = next((p for p in candidates if p and Path(p).is_file()), None)
    if chrome:
        subprocess.Popen([chrome, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-pause', action='store_true', help='BAT automation: no prompt on failure')
    parser.add_argument('--check', action='store_true', help='Validate files and dependencies without starting a server')
    parser.add_argument('--skip-backup', action='store_true', help='Start even if the automatic startup backup fails')
    args = parser.parse_args(argv)
    for name in ('config', 'users', 'workflow'):
        target, example = ROOT / f'backend/{name}.json', ROOT / f'backend/{name}.example.json'
        if not target.exists() and example.is_file():
            shutil.copyfile(example, target)
            print('Created local ' + target.name + ' from the safe example.', flush=True)
    for relative in ('backend/app.py', 'backend/config.json', 'backend/users.json', 'backend/workflow.json', 'frontend/index.html'):
        if not (ROOT / relative).is_file():
            print('Missing required file: ' + relative, flush=True)
            return 1
    try:
        import openpyxl
        import reportlab
        config = json.loads((ROOT / 'backend/config.json').read_text(encoding='utf-8'))
        port = int(config.get('port', 8080))
        security = config.get('security', {})
        if not (os.environ.get('SOMESH_ADMIN_PIN') or security.get('admin_pin') or any(security.get('pins', {}).values())):
            raise ValueError('Set SOMESH_ADMIN_PIN or security.admin_pin in your local backend/config.json before starting')
        if not 1 <= port <= 65535:
            raise ValueError('Configured port must be between 1 and 65535')
        sys.path.insert(0, str(ROOT / 'backend'))
        import lan as LAN
        https = LAN.settings(config)['https']
        if https['enabled']:
            for item in ('cert', 'key'):
                if not Path(LAN.resolve(str(ROOT), https[item])).is_file():
                    raise ValueError('HTTPS is enabled but ' + https[item] + ' is missing. Run: python tools\\make_office_cert.py')
            if https['port'] == port or not 1 <= https['port'] <= 65535:
                raise ValueError('network.https.port must be a free port different from the HTTP port')
        db_state = check_database()
    except (ImportError, ValueError, OSError) as error:
        print('Startup configuration/dependency error: ' + str(error), flush=True)
        return 1
    if args.check:
        print('PASS startup files, Python dependencies, configured ports, HTTPS files and database (' + db_state + ')', flush=True)
        return 0
    host = config.get('host', '0.0.0.0')
    connect_host = '127.0.0.1' if host in ('0.0.0.0', '', 'localhost') else host
    url = f'http://{connect_host}:{port}'
    browser_url = f'http://localhost:{port}' if connect_host == '127.0.0.1' else url
    if healthy(url):
        if args.demo:
            print('The app is already running. Demo reload was NOT applied; use the authenticated Admin demo controls.', flush=True)
        else:
            print('Reusing this project\'s existing server at ' + browser_url, flush=True)
            print_addresses(config, browser_url)
        if not args.no_browser:
            open_browser(browser_url)
        return 0
    (ROOT / 'data').mkdir(exist_ok=True)
    with (ROOT / 'data/startup.lock').open('a+b') as lock:
        try:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            for _ in range(25):
                if healthy(url):
                    print('Reusing the server started by the other launcher.', flush=True)
                    if not args.no_browser: open_browser(browser_url)
                    return 0
                time.sleep(.2)
            print('Another launcher is starting this project. Wait and try again.', flush=True)
            return 1
        for busy in [port] + ([https['port']] if https['enabled'] else []):
            with socket.socket() as probe:
                if probe.connect_ex((connect_host, busy)) == 0:
                    print(f'Port {busy} is occupied by another server. No process was stopped. Close that server or change backend/config.json.', flush=True)
                    return 1
        try:
            saved = startup_backup()
            if saved: print('[OK] Database backed up to ' + str(saved.relative_to(ROOT)), flush=True)
        except Exception as error:
            print('Automatic database backup failed: ' + str(error), flush=True)
            if not args.skip_backup:
                print('Nothing was started. Free some disk space, or start with --skip-backup to run without this backup.', flush=True)
                return 1
        command = [sys.executable, '-u', str(ROOT / 'backend/app.py')]
        if args.demo: command.append('--demo')
        child = subprocess.Popen(command, cwd=str(ROOT))
        try:
            for _ in range(150):
                if child.poll() is not None:
                    print('Backend exited before becoming ready.', flush=True)
                    return child.returncode or 1
                if healthy(url): break
                time.sleep(.2)
            else:
                print('Backend did not become ready within 30 seconds.', flush=True)
                child.terminate(); child.wait(timeout=10)
                return 1
            print('Ready: ' + browser_url, flush=True)
            print_addresses(config, browser_url)
            if not args.no_browser: open_browser(browser_url)
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.terminate(); child.wait(timeout=10)
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
