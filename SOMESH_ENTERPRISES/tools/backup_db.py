"""Online backup of the SOMESH ENTERPRISES database and private settings. Safe while the server is running.

    python tools/backup_db.py                         -> data/backups/manual-YYYYMMDD-HHMMSS/
    python tools/backup_db.py --dest "E:\\SOMESH Backups" --keep 30
    python tools/backup_db.py --label nightly --keep 14

Each backup folder holds monthly_cycle.db (a consistent SQLite snapshot made with the SQLite backup API, which includes
committed WAL data), copies of backend/config.json, users.json and workflow.json, and manifest.json with row counts and the
integrity-check result. Backups contain personal data and the admin PIN: keep them off GitHub and off shared drives.
The storage/ folder (Data Center files) is not included; copy it separately (see README, "Backup and recovery").
"""
import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = Path('data') / 'monthly_cycle.db'
PRIVATE = ('config.json', 'users.json', 'workflow.json')


def counts(con):
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def backup(root=ROOT, label='manual', keep=0, dest=None):
    root = Path(root)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
    from runtime_storage import database_path
    config=json.loads((root/'backend/config.json').read_text(encoding='utf-8'))
    src_path = database_path(root,config)
    if not src_path.is_file():
        raise FileNotFoundError(f'No database at {src_path}')
    base = Path(dest) if dest else root / 'data' / 'backups'
    folder = base / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while folder.exists():
        n += 1
        folder = base / f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{n}"
    folder.mkdir(parents=True)
    target = folder / 'monthly_cycle.db'
    src = sqlite3.connect(f'file:{src_path.as_posix()}?mode=ro', uri=True, timeout=30)
    dst = sqlite3.connect(target)
    try:
        src.execute('PRAGMA busy_timeout=30000')
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')  # a single self-contained file
        check = dst.execute('PRAGMA integrity_check').fetchone()[0]
        rows = counts(dst)
    finally:
        dst.close()
        src.close()
    if check != 'ok':
        raise RuntimeError(f'Backup integrity check failed: {check}')
    for name in PRIVATE:
        if (root / 'backend' / name).is_file():
            shutil.copy2(root / 'backend' / name, folder / name)
    (folder / 'manifest.json').write_text(json.dumps({'created': datetime.now().isoformat(timespec='seconds'), 'label': label,
                                                      'source': str(src_path), 'integrity': check, 'rows': rows}, indent=2), encoding='utf-8')
    if keep and keep > 0:
        # Newest first by write time (names can repeat within one second); the backup just made is always kept.
        old = sorted((p for p in base.glob(f'{label}-*') if p.is_dir() and p != folder and (p / 'manifest.json').is_file()),
                     key=lambda p: (p / 'manifest.json').stat().st_mtime_ns, reverse=True)
        for stale in old[keep - 1:]:
            shutil.rmtree(stale, ignore_errors=True)
    return folder


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--label', default='manual', help='folder name prefix (letters, digits, - and _)')
    ap.add_argument('--keep', type=int, default=0, help='keep only the newest N backups with this label (0 = keep all)')
    ap.add_argument('--dest', help='backup folder (default data/backups)')
    a = ap.parse_args(argv)
    if not a.label.replace('-', '').replace('_', '').isalnum():
        ap.error('--label may contain letters, digits, - and _ only')
    try:
        folder = backup(ROOT, a.label, a.keep, a.dest)
    except Exception as e:
        print('BACKUP FAILED:', e)
        return 1
    rows = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['rows']
    print(f'Backup OK: {folder}')
    print(f"  integrity ok; {rows.get('employees', 0)} employees, {rows.get('tasks', 0)} tasks, {rows.get('ew_versions', 0)} Excel versions")
    return 0


if __name__ == '__main__':
    sys.exit(main())
