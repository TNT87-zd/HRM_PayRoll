"""Explicit, transactional migration from the old HRM JSON SQLite database.
Default: preview/rollback. Existing main employees remain authoritative.
No face images, face templates, active login sessions or source data are changed.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sqlalchemy import select
from sqlalchemy.engine import make_url
from config import Settings
from database import Base, open_database
from models import Employee, User, UserEmployee, MigrationRecord
from hrm.store import put, get, employee_dict, audit


def migrate(source, settings, apply=False, employee_policy='check'):
    source=Path(source).resolve()
    if not source.is_file(): raise ValueError('Không tìm thấy database HRM cũ')
    target=Path(make_url(settings.database_url).database).resolve()
    if target==source: raise ValueError('Database nguồn và đích phải khác nhau')
    # Read-only SQLite URI: never create or write the source database.
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as old:
        old.row_factory=sqlite3.Row
        items=[(x['kind'],x['id'],json.loads(x['payload'])) for x in old.execute('SELECT * FROM records ORDER BY kind,id')]
        users=[dict(x) for x in old.execute('SELECT * FROM users')]
    digest=hashlib.sha256(json.dumps([items,users],sort_keys=True).encode()).hexdigest()
    key='hrm-legacy-'+digest[:24]
    if not target.is_file(): raise ValueError('Khởi động bản mới một lần để tạo database đích, rồi dừng server')
    engine,factory=open_database(settings.database_url)
    report={'employees_added':0,'employees_kept':[],'records_added':0,'users_added':0,'users_kept':[],'applied':False}
    try:
        with factory() as con:
            if con.get(MigrationRecord,key): return {'already_imported':True}
            # Rollback everything on any conflict. Existing employee IDs never silently change.
            for kind,eid,e in items:
                if kind!='employees': continue
                current=con.get(Employee,eid)
                if current:
                    if employee_dict(current)!=e and employee_policy=='check':
                        raise ValueError('Hồ sơ khác nhau: '+eid+'. Kiểm tra; dùng --employee-policy keep-main để giữ hồ sơ main.')
                    report['employees_kept'].append(eid)
                else:
                    con.add(Employee(employee_id=eid,full_name=e['full_name'],branch_id=e['branch_id'],
                        role='phuc_vu',contract_type=e['contract_type'],primary_shift='',hire_date='',
                        base_salary=e['base_salary'] or None,hourly_rate=e['hourly_rate'] or None,
                        employment_status='active' if e['active'] else 'inactive'))
                    report['employees_added']+=1
            con.flush()
            # Import schedules before attendance. Prefix event IDs to isolate source identifiers.
            for kind,eid,value in sorted(items,key=lambda x: {'shifts':0,'leaves':1,'payroll':2,'events':3}.get(x[0],9)):
                if kind not in {'shifts','leaves','payroll','events'}: continue
                if kind=='events':
                    if not get(con,'shifts',value['shift_id']): raise ValueError('Thiếu ca: '+value['shift_id'])
                    value={**value,'event_id':'legacy-'+eid};eid=value['event_id']
                existing=get(con,kind,eid)
                if existing:
                    if existing!=value: raise ValueError('Trùng dữ liệu khác nội dung: '+kind+'/'+eid)
                    continue
                put(con,kind,eid,value);report['records_added']+=1
            for u in users:
                if con.scalar(select(User).where(User.username==u['username'])):
                    report['users_kept'].append(u['username']); continue
                if u['role'] not in {'hr','employee','kiosk'}: raise ValueError('Vai trò không hợp lệ')
                if u['role']=='employee' and not con.get(Employee,u['employee_id']): raise ValueError('Tài khoản thiếu nhân viên liên kết')
                new=User(username=u['username'],password_hash='legacy_scrypt$'+u['password'],role=u['role'])
                con.add(new);con.flush()
                if u['employee_id']: con.add(UserEmployee(user_id=new.id,employee_id=u['employee_id']))
                report['users_added']+=1
            # Reserve imported employee IDs for future automatic employee creation.
            from models import Counter
            import re
            max_id=max([int(e[2:]) for e in con.scalars(select(Employee.employee_id)) if re.fullmatch(r'NV\d+',e)] or [0])
            counter=con.get(Counter,'employee')
            if counter: counter.value=max(counter.value,max_id)
            else: con.add(Counter(name='employee',value=max_id))
            con.add(MigrationRecord(name=key,detail=json.dumps(report)))
            audit(con,'migration','legacy_hrm_import',report)
            con.flush()
            if apply:
                # Use SQLite backup to include WAL; create a separate recovery copy before commit.
                backup=target.with_name(target.name+'.before-legacy-'+digest[:8]+'.bak')
                if not backup.exists():
                    with sqlite3.connect(str(target)) as source_db, sqlite3.connect(str(backup)) as dest_db:
                        source_db.backup(dest_db)
                con.commit();report['applied']=True
            else: con.rollback()
    finally: engine.dispose()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--employee-policy',choices=['check','keep-main'],default='check')
    a=p.parse_args()
    try: print(json.dumps(migrate(a.source,Settings(),a.apply,a.employee_policy),ensure_ascii=False,indent=2))
    except Exception as exc: p.exit(1,'Không nhập dữ liệu: '+str(exc)+'\n')

if __name__=='__main__': main()
