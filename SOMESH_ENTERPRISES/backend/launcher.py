"""Windows BAT entry point. Reuse this checkout's healthy server; never kill port owners."""
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
    except (ImportError, ValueError) as error:
        print('Startup configuration/dependency error: ' + str(error), flush=True)
        return 1
    if args.check:
        print('PASS startup files, Python dependencies and configured port', flush=True)
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
        with socket.socket() as probe:
            if probe.connect_ex((connect_host, port)) == 0:
                print(f'Port {port} is occupied by another server. No process was stopped. Close that server or change backend/config.json.', flush=True)
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
            if not args.no_browser: open_browser(browser_url)
            return child.wait()
        except KeyboardInterrupt:
            if child.poll() is None:
                child.terminate(); child.wait(timeout=10)
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
