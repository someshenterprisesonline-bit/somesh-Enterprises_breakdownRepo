"""Absolute runtime storage paths and read-only profile validation shared by launchers."""
import json
import hashlib
import os
import sqlite3
from pathlib import Path

def database_path(root,config):
    directory=Path(config.get('data_dir') or 'data').expanduser()
    if not directory.is_absolute():directory=Path(root)/directory
    return (directory/'monthly_cycle.db').resolve()

def stored_profiles(path):
    if not Path(path).is_file():return None
    con=sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='employees'").fetchone():return None
        count=con.execute('SELECT count(*) FROM employees').fetchone()[0]
        if not count:raise ValueError('The existing SQLite profile store is empty. Restore verified account records; no default accounts were seeded.')
        profiles=[json.loads(row[0]) for row in con.execute('SELECT profile FROM employees WHERE deleted_at IS NULL ORDER BY rowid')]
        validate_profiles(profiles)
        return profiles
    finally:con.close()

def validate_profiles(profiles):
    if not isinstance(profiles,list) or not profiles or any(not isinstance(p,dict) or not isinstance(p.get('name'),str) or not p['name'].strip() for p in profiles):
        raise ValueError('The authoritative profile store is empty or invalid. Review configuration and verified backups; no demo profiles were substituted.')
    if not any(p.get('admin') for p in profiles):raise ValueError('The authoritative profile store has no active Admin. Review existing account records; no replacement account was created.')

def storage_id(path):
    return hashlib.sha256(os.path.normcase(os.path.realpath(path)).encode()).hexdigest()[:20]
