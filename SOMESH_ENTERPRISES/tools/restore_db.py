"""Restore the SOMESH ENTERPRISES database from a backup made by tools/backup_db.py (or the automatic startup backup).

    1. Close the SERVER MODE window on the Admin PC (the app must be stopped).
    2. python tools/restore_db.py "data/backups/startup-20261110-090000" --yes
       add --with-settings to also restore config.json, users.json and workflow.json from that folder.

Before anything is replaced, the current database is itself backed up as data/backups/pre-restore-*. The backup is checked
with PRAGMA integrity_check first, and the restore is written through SQLite (never a raw file copy over a live database).
"""
import argparse
import json
import os
import shutil
import socket
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from backup_db import backup, DB, PRIVATE  # noqa: E402


def server_running(root):
    try:
        cfg = json.loads((Path(root) / 'backend/config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cfg = {}
    ports = {int(cfg.get('port', 8080))}
    https = (cfg.get('network') or {}).get('https') or {}
    if https.get('enabled'):
        ports.add(int(https.get('port', 8443)))
    for port in ports:
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return port
    return None


def restore(root, source, with_settings=False):
    root, source = Path(root), Path(source)
    folder = source if source.is_dir() else source.parent
    db_file = source / 'monthly_cycle.db' if source.is_dir() else source
    if not db_file.is_file():
        raise FileNotFoundError(f'No database file in {source}')
    src = sqlite3.connect(f'file:{db_file.as_posix()}?mode=ro', uri=True)
    try:
        check = src.execute('PRAGMA integrity_check').fetchone()[0]
        if check != 'ok':
            raise RuntimeError(f'The backup failed its integrity check: {check}')
        live = root / DB
        safety = backup(root, 'pre-restore') if live.is_file() else None
        live.parent.mkdir(parents=True, exist_ok=True)
        dst = sqlite3.connect(live)
        try:
            src.backup(dst)
            dst.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('The restored database failed its integrity check; the pre-restore backup is untouched')
        finally:
            dst.close()
    finally:
        src.close()
    restored = []
    if with_settings:
        for name in PRIVATE:
            if (folder / name).is_file():
                shutil.copy2(folder / name, root / 'backend' / name)
                restored.append(name)
    return safety, restored


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('backup', help='backup folder (or a .db file) to restore')
    ap.add_argument('--yes', action='store_true', help='confirm replacing the current database')
    ap.add_argument('--with-settings', action='store_true', help='also restore config.json, users.json and workflow.json')
    a = ap.parse_args(argv)
    port = server_running(ROOT)
    if port:
        print(f'The app is still running (port {port}). Close the SERVER MODE window first, then run this again.')
        return 2
    if not a.yes:
        print('This replaces the current database with', a.backup)
        print('The current database is backed up first. Re-run with --yes to continue.')
        return 2
    try:
        safety, restored = restore(ROOT, a.backup, a.with_settings)
    except Exception as e:
        print('RESTORE FAILED:', e)
        return 1
    if safety:
        print('Previous database saved to', safety)
    print('Database restored from', a.backup + (f"; settings restored: {', '.join(restored)}" if restored else ''))
    print('Start the app again with START SOMESH ENTERPRISES.bat')
    return 0


if __name__ == '__main__':
    sys.exit(main())
