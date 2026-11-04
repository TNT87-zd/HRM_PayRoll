"""One login, one employee store, one attendance table; isolated test database."""
from datetime import datetime, timedelta
import uuid
from sqlalchemy import select, func
from test_enrollment import env, profile, completed, picture
from models import AttendanceRecord, AttendanceAssignment, Employee, User, UserEmployee
from routers.auth import hash_password
from hrm.core import VN


def shift(client,eid,key='s1',start='2026-01-02T08:00:00+07:00',end='2026-01-02T16:00:00+07:00'):
    return client.put('/api/hrm/shifts',json=dict(shift_id=key,employee_id=eid,branch_id='CN01',start=start,end=end,approved_ot_minutes=60))

def event(client,eid,kind,ts,key='s1'):
    return client.post('/api/hrm/events/manual',json=dict(employee_id=eid,shift_id=key,scan_type=kind,ts=ts,reason='HR đối chiếu sổ ca'))

def test_shared_profiles_payroll_and_lock(env):
    app,c,*_=env
    e=profile(c,base_salary=10400000).json()['employee_id']
    assert c.get('/api/hrm/auth/me').json()['role']=='hr'
    assert e in {x['employee_id'] for x in c.get('/api/hrm/employees').json()}
    assert shift(c,e).status_code==200
    assert shift(c,e,'overlap').status_code==409
    assert event(c,e,'IN','2026-01-02T08:00:00+07:00').status_code==200
    assert event(c,e,'OUT','2026-01-02T17:00:00+07:00').status_code==200
    rows=c.get('/api/hrm/attendance?month=2026-01').json()
    assert rows[0]['regular_hours']==8 and rows[0]['ot_hours']==1
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord))==2
    run=c.post('/api/hrm/payroll/2026-01/calculate',json={'note':'Đã kiểm tra công','standard_hours':208}).json()
    assert run['rows'][0]['net']==475000
    # Employee edits through main invalidate draft HRM payroll too.
    assert c.patch('/api/employees/'+e,json={'base_salary':12480000}).status_code==200
    assert c.post('/api/hrm/payroll/2026-01/finalize',json={'reviewed':True,'input_hash':run['input_hash']}).status_code==409
    run=c.post('/api/hrm/payroll/2026-01/calculate',json={'note':'Tính lại lương'}).json()
    assert c.post('/api/hrm/payroll/2026-01/finalize',json={'reviewed':True,'input_hash':run['input_hash']}).status_code==200
    assert event(c,e,'IN','2026-01-02T08:10:00+07:00').status_code==409
    assert c.get('/api/hrm/payroll/2026-01/export').content[:2]==b'PK'
    assert c.get('/api/hrm/audit').json()


def test_kiosk_to_timesheet_no_double_writes(env):
    app,c,*_=env
    e=profile(c).json()['employee_id']; completed(env,e)
    now=datetime.now(VN)
    assert shift(c,e,start=(now-timedelta(minutes=5)).isoformat(),end=(now+timedelta(hours=1)).isoformat()).status_code==200
    files=[('files',('q.jpg',picture(n),'image/jpeg')) for n in range(50,53)]
    data={'device_id':'CN01-TB01','scan_type':'IN','lat':16.0471,'lon':108.2208}
    assert c.post('/api/kiosk/recognize',files=files,data=data).json()['recorded']
    assert not c.post('/api/kiosk/recognize',files=files,data=data).json()['recorded']
    data['scan_type']='OUT'
    assert c.post('/api/kiosk/recognize',files=files,data=data).json()['recorded']
    row=c.get('/api/hrm/attendance',params={'month':now.strftime('%Y-%m')}).json()[0]
    assert row['status']=='present'
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord))==2
        assert db.scalar(select(func.count()).select_from(AttendanceAssignment))==2
    data['lat']=0
    assert c.post('/api/kiosk/recognize',files=files,data=data).status_code==403
    c.post('/api/auth/logout')
    assert c.post('/api/kiosk/recognize',files=files,data=data).status_code==401


def test_no_schedule_never_records_success(env):
    app,c,*_=env
    e=profile(c).json()['employee_id']; completed(env,e)
    files=[('files',('q.jpg',picture(n),'image/jpeg')) for n in range(60,63)]
    response=c.post('/api/kiosk/recognize',files=files,data={'device_id':'CN01-TB01','scan_type':'IN','lat':16.0471,'lon':108.2208})
    assert response.status_code==409
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord))==0


def test_leave_and_employee_scope(env):
    app,c,*_=env
    a=profile(c).json()['employee_id']; b=profile(c).json()['employee_id']
    assert shift(c,a).status_code==200
    leave=c.post('/api/hrm/leaves',json=dict(employee_id=a,start_date='2026-01-02',end_date='2026-01-02',leave_type='PAID',reason='Nghỉ có phép')).json()
    assert c.post('/api/hrm/leaves/'+leave['leave_id']+'/decision',json={'status':'approved'}).status_code==200
    assert c.get('/api/hrm/attendance?month=2026-01').json()[0]['paid_leave_hours']==8
    with app.state.session_factory() as db:
        u=User(username='staff',password_hash=hash_password('staff-password-123'),role='employee'); db.add(u);db.flush()
        db.add(UserEmployee(user_id=u.id,employee_id=a));db.commit()
    c.post('/api/auth/logout')
    assert c.post('/api/auth/login',json={'username':'staff','password':'staff-password-123'}).status_code==200
    assert [e['employee_id'] for e in c.get('/api/hrm/employees').json()]==[a]
    assert c.get('/api/employees').status_code==403
    assert shift(c,a,'denied').status_code==403
    assert c.post('/api/hrm/leaves',json=dict(employee_id=b,start_date='2026-01-03',end_date='2026-01-03',leave_type='PAID',reason='Không đúng người')).status_code==403
    assert c.get('/api/hrm/payroll/2026-01').status_code==404


def test_reconcile_existing_main_attendance_without_copy(env):
    app,c,*_=env
    e=profile(c).json()['employee_id']
    assert shift(c,e).status_code==200
    with app.state.session_factory() as db:
        old=AttendanceRecord(employee_id=e,device_id='CN01-TB01',scan_type='IN',timestamp=datetime(2026,1,2,8,tzinfo=VN).timestamp(),similarity=.8)
        db.add(old);db.commit();key=old.id
    assert c.get('/api/hrm/events/unassigned').json()[0]['attendance_id']==key
    assert c.post(f'/api/hrm/events/{key}/assign',json={'shift_id':'s1','reason':'Đối chiếu log cũ'}).status_code==200
    assert c.post(f'/api/hrm/events/{key}/assign',json={'shift_id':'s1','reason':'Lặp lại yêu cầu'}).status_code==409
    assert c.get('/api/hrm/events/unassigned').json()==[]
    with app.state.session_factory() as db: assert db.scalar(select(func.count()).select_from(AttendanceRecord))==1


def test_legacy_migration_preview_apply_login_idempotent(env,tmp_path):
    import sys, sqlite3, json, hashlib
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    from migrate_legacy_hrm import migrate
    app,c,*_=env
    e=profile(c).json()['employee_id']
    person=next(x for x in c.get('/api/hrm/employees').json() if x['employee_id']==e)
    source=tmp_path/'old.sqlite3'
    salt='ab'*16;pw='legacy-password-123'
    encoded=salt+':'+hashlib.scrypt(pw.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    with sqlite3.connect(source) as old:
        old.execute('CREATE TABLE records(kind,id,payload)')
        old.execute('CREATE TABLE users(username,password,role,employee_id)')
        old.execute('INSERT INTO records VALUES(?,?,?)',('employees',e,json.dumps(person)))
        old.execute('INSERT INTO records VALUES(?,?,?)',('shifts','migrated',json.dumps(dict(shift_id='migrated',employee_id=e,branch_id='CN01',start='2026-01-02T08:00:00+07:00',end='2026-01-02T16:00:00+07:00',break_minutes=0,approved_ot_minutes=0,ot_multiplier=1.5))))
        old.execute('INSERT INTO users VALUES(?,?,?,?)',('oldstaff',encoded,'employee',e))
    before=source.read_bytes()
    report=migrate(source,app.state.settings)
    assert report['users_added']==1 and not report['applied']
    assert c.get('/api/hrm/shifts?month=2026-01').json()==[]
    assert migrate(source,app.state.settings,True)['applied']
    assert migrate(source,app.state.settings,True)['already_imported']
    assert source.read_bytes()==before
    c.post('/api/auth/logout')
    assert c.post('/api/auth/login',json={'username':'oldstaff','password':pw}).status_code==200
    assert c.get('/api/hrm/auth/me').json()['employee_id']==e
    assert len(c.get('/api/hrm/shifts?month=2026-01').json())==1
