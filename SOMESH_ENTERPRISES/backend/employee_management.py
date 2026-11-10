"""Employee roster stored in the application's SQLite database."""
import copy
import json
import unicodedata


def key(name):
    return ' '.join(unicodedata.normalize('NFKC', name).split()).casefold()


def initialize(g):
    db = g['DB']
    db.execute('CREATE TABLE IF NOT EXISTS employees (name_key TEXT PRIMARY KEY, profile TEXT NOT NULL, deleted_at TEXT)')
    for user in g['USERS']:
        db.execute('INSERT OR IGNORE INTO employees VALUES (?,?,NULL)', (key(user['name']), json.dumps(user)))
    db.commit()
    refresh(g)


def refresh(g):
    users = [json.loads(r['profile']) for r in g['q']('SELECT profile FROM employees WHERE deleted_at IS NULL ORDER BY rowid')]
    g['USERS'][:] = users
    g['USER_NAMES'].clear()
    g['USER_NAMES'].update(u['name'] for u in users)


def validate_roster(g, users):
    keys = [key(u['name']) for u in users]
    if len(keys) != len(set(keys)):
        raise g['FlowError']('Employee names must be unique')
    archived = {r['name_key'] for r in g['q']('SELECT name_key FROM employees WHERE deleted_at IS NOT NULL')}
    if archived.intersection(keys):
        raise g['FlowError']('Workflow input contains an archived employee. Remove that profile before applying.')
    if not any(u.get('admin') for u in users):
        raise g['FlowError']('Keep at least one active Admin')


def sync(g):
    # Existing workflow import and Admin management also update the same roster.
    validate_roster(g, g['USERS'])
    db = g['DB']
    active = {key(u['name']) for u in g['USERS']}
    for row in db.execute('SELECT name_key FROM employees WHERE deleted_at IS NULL').fetchall():
        if row[0] not in active:
            db.execute('UPDATE employees SET deleted_at=? WHERE name_key=?', (g['ts'](), row[0]))
    for user in g['USERS']:
        db.execute('INSERT INTO employees VALUES (?,?,NULL) ON CONFLICT(name_key) DO UPDATE SET profile=excluded.profile WHERE employees.deleted_at IS NULL', (key(user['name']), json.dumps(user)))
    db.commit()
    refresh(g)


def replace(value, old, new):
    if isinstance(value, str):
        return new if value == old else ('person:' + new if value == 'person:' + old else value)
    if isinstance(value, list):
        return [replace(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: replace(v, old, new) for k, v in value.items()}
    return value


def change(g, actor, body):
    error = g['FlowError']
    with g['LOCK']:
        if not g['is_admin'](actor):
            raise g['Denied']('Only admins can manage employees')
        action = body.get('action')
        if action not in ('add', 'edit', 'delete'):
            raise error('Choose add, edit or delete')
        old = next((u for u in g['USERS'] if u['name'] == body.get('original')), None)
        if action != 'add' and not old:
            raise error('Employee no longer active. Refresh the list.')
        if action == 'delete':
            if body.get('confirmed') is not True:
                raise error('Confirm employee deletion')
            if old['name'] == actor:
                raise error('You cannot delete your own profile')
            profile = old
        else:
            profile = dict(old or {})
            if old: profile.setdefault('identity_name', old.get('identity_name', old['name']))
            for field in ('name', 'designation', 'dept'):
                value = body.get(field)
                if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120 or any(ord(c) < 32 for c in value):
                    raise error('Name, designation and department are required (maximum 120 characters)')
                profile[field] = ' '.join(value.split())
            role = body.get('access_role')
            if role not in ('employee', 'admin'):
                raise error('Choose Employee or Admin role')
            profile['admin'] = role == 'admin'
            profile['role'] = profile['designation']
            if old and old['name'] == actor and (profile['name'] != actor or not profile['admin']):
                raise error('Use another Admin to change your own name or access')
            duplicate = g['q']('SELECT name_key FROM employees WHERE name_key=?', (key(profile['name']),))
            if duplicate and (not old or key(old['name']) != key(profile['name'])):
                raise error('An employee with this name already exists (including archived profiles)')
        if old and old.get('admin') and (action == 'delete' or not profile.get('admin')) and len(g['admins']()) <= 1:
            raise error('The last active Admin cannot be removed')
        if bool(profile.get('admin')) != bool(old and old.get('admin')) or (action == 'delete' and old.get('admin')):
            g['verify_admin_pin'](actor, body.get('confirmation_pin'))
        db = g['DB']
        old_flow, old_config = copy.deepcopy(g['FLOW']), copy.deepcopy(g['CONFIG'])
        saved_files = []
        try:
            db.execute('BEGIN IMMEDIATE')
            if action == 'delete':
                db.execute('UPDATE employees SET deleted_at=? WHERE name_key=?', (g['ts'](), key(old['name'])))
            elif old and key(old['name']) == key(profile['name']):
                db.execute('UPDATE employees SET profile=? WHERE name_key=?', (json.dumps(profile), key(old['name'])))
            else:
                if old:
                    # Reserve former names so stale JSON cannot recreate an identity after a rename.
                    db.execute('UPDATE employees SET deleted_at=? WHERE name_key=?', (g['ts'](), key(old['name'])))
                db.execute('INSERT INTO employees VALUES (?,?,NULL)', (key(profile['name']), json.dumps(profile)))
            if old:
                db.execute('DELETE FROM sessions WHERE user=?', (old['name'],)) if action == 'delete' or profile['name'] != old['name'] or bool(profile.get('admin')) != bool(old.get('admin')) else None
                if action == 'edit' and old['name'] != profile['name']:
                    before, after = old['name'], profile['name']
                    for table, columns in {'tasks': ['assignee', 'validator'], 'work_log': ['user'], 'alerts': ['user'], 'ew_books': ['owner'], 'ew_template_access': ['user'], 'ew_pending': ['actor']}.items():
                        if not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (table,)).fetchone():
                            continue
                        for col in columns:
                            db.execute(f'UPDATE {table} SET {col}=? WHERE {col}=?', (after, before))
                    for table, column, ident in [('tasks', 'owners', 'id'), ('adhoc', 'def', 'code'), ('rules', 'actions', 'id'), ('rules', 'conditions', 'id')]:
                        for row in db.execute(f'SELECT {ident},{column} FROM {table}').fetchall():
                            if row[1]:
                                value = replace(json.loads(row[1]), before, after)
                                db.execute(f'UPDATE {table} SET {column}=? WHERE {ident}=?', (json.dumps(value), row[0]))
                    flow = replace(g['FLOW'], before, after)
                    saved_files.append(('workflow.json', old_flow))
                    g['save']('workflow.json', flow)
                    g['FLOW'].clear(); g['FLOW'].update(flow)
                    g['STAGES'].clear(); g['STAGES'].update({s['code']: s for s in flow['stages']})
                    g['load_adhoc']()
                    pins = g['CONFIG'].get('security', {}).get('pins', {})
                    if before in pins:
                        pins[after] = pins.pop(before)
                        saved_files.append(('config.json', old_config))
                        g['save']('config.json', g['CONFIG'])
            db.execute('INSERT INTO events(ts,kind,actor,text) VALUES (?,?,?,?)', (g['ts'](), 'employee_management', actor, f'{action}: {profile["name"]}'))
            roster = [json.loads(r[0]) for r in db.execute('SELECT profile FROM employees WHERE deleted_at IS NULL ORDER BY rowid')]
            saved_files.append(('users.json', g['load']('users.json')))
            g['save']('users.json', {'users': roster})
            db.commit()
        except Exception:
            db.rollback()
            g['FLOW'].clear(); g['FLOW'].update(old_flow)
            g['CONFIG'].clear(); g['CONFIG'].update(old_config)
            g['STAGES'].clear(); g['STAGES'].update({s['code']: s for s in old_flow['stages']})
            g['load_adhoc']()
            for filename, original in reversed(saved_files):
                g['save'](filename, original)
            raise
        refresh(g)
    g['broadcast']({'type': 'reload'})
    g['STORAGE_DIRTY'].set(); g['GATHER_DIRTY'].set()
    return {'ok': True, 'users': g['USERS']}
