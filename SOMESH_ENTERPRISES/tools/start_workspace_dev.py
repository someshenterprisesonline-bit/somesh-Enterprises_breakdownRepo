"""Run a synthetic local workspace using the existing launcher and a separate SQLite DB.

Never reads the office configuration, database, users or certificates. Runtime files
and copied source live under ignored data/workspace-dev. Stop the child to update.
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
RUNTIME=PROJECT/'data'/'workspace-dev'

def prepare(port):
    sys.path.insert(0,str(PROJECT/'tests'))
    from support import AppFixture
    from test_document_workspace import seed_documents
    from test_formula_engine import template,payload
    from test_neft_sync import neft_file
    (RUNTIME/'backend').mkdir(parents=True,exist_ok=True)
    (RUNTIME/'data').mkdir(exist_ok=True)
    (RUNTIME/'tools').mkdir(exist_ok=True)
    shutil.copy2(PROJECT/'tools'/'backup_db.py',RUNTIME/'tools'/'backup_db.py')
    for p in (PROJECT/'backend').glob('*.py'):shutil.copy2(p,RUNTIME/'backend'/p.name)
    shutil.copytree(PROJECT/'frontend',RUNTIME/'frontend',dirs_exist_ok=True)
    if not (RUNTIME/'data'/'monthly_cycle.db').exists():
        fixture=AppFixture()
        try:
            fixture.seed_browser()
            info=seed_documents(fixture,assign=False,worksheet_data=payload(template()),neft_data=neft_file())
            token=info['employees']['Nandha']['token']
            status,book=fixture.request('/api/excel/blank',{'id':info['masters']['worksheet']},token)
            assert status==200,book
            changes=[]
            for row,(name,designation) in enumerate([('Ramesh','Data Entry Operator'),('Kumar','Office Assistant'),('Priya','Accountant')],7):
                for col,value in [('A',row-6),('B',name),('C',designation)]:changes.append({'sheet':'TNOU','address':col+str(row),'value':str(value),'type':'number' if col=='A' else 'text'})
            status,result=fixture.request('/api/excel/save',{'id':book['id'],'revision':book['revision'],'changes':changes},token)
            assert status==200,result
            fixture.g['save']('users.json',{'users':fixture.g['USERS']})
            fixture.g['DB'].commit()
            with sqlite3.connect(RUNTIME/'data'/'monthly_cycle.db') as db:fixture.g['DB'].backup(db)
            for name in ('config','users','workflow'):
                shutil.copy2(fixture.root/'backend'/(name+'.json'),RUNTIME/'backend'/(name+'.json'))
        finally:fixture.close()
    config_path=RUNTIME/'backend'/'config.json'
    config=json.loads(config_path.read_text(encoding='utf-8'))
    config.update(host='127.0.0.1',port=port,environment='development')
    config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    return RUNTIME

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8081);parser.add_argument('--no-browser',action='store_true');parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535')
    # Do not copy source or update settings underneath an already running dev app.
    sys.path.insert(0,str(PROJECT/'backend'));import launcher
    existing_config=RUNTIME/'backend'/'config.json'
    if existing_config.exists():
        existing_port=json.loads(existing_config.read_text(encoding='utf-8')).get('port',8081)
        if existing_port!=args.port and launcher.healthy('http://127.0.0.1:'+str(existing_port),RUNTIME):
            parser.error('Development app already uses port '+str(existing_port)+'. Stop it before changing ports.')
    if launcher.healthy('http://127.0.0.1:'+str(args.port),RUNTIME):
        print('Development app is already running at http://localhost:'+str(args.port),flush=True)
        if not args.no_browser:launcher.open_browser('http://localhost:'+str(args.port))
        return 0
    runtime=prepare(args.port)
    print('Isolated development data: '+str(runtime/'data'),flush=True)
    print('Synthetic employee profile: Nandha (profile sign-in). No office data is used.',flush=True)
    if args.prepare:return 0
    command=[sys.executable,'-u',str(runtime/'backend'/'launcher.py'),'--no-pause']
    if args.no_browser:command.append('--no-browser')
    return subprocess.call(command,cwd=runtime)

if __name__=='__main__':raise SystemExit(main())
