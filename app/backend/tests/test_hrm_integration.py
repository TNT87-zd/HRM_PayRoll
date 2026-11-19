"""One login, one employee store, one attendance table; isolated test database."""
from datetime import datetime, timedelta
import uuid
from sqlalchemy import select, func
from test_enrollment import env, profile, completed, picture
from models import AttendanceRecord, AttendanceAssignment, Employee, User, UserEmployee
from routers.auth import hash_password
from hrm.core import VN
from routers import kiosk

def shift(client,eid,key='s1',start='2026-01-02T07:00:00+07:00',end='2026-01-02T15:00:00+07:00'):
    return client.put('/api/hrm/shifts',json=dict(shift_id=key,employee_id=eid,branch_id='CN01',start=start,end=end,approved_ot_minutes=60))

def event(client,eid,kind,ts,key='s1'):
    return client.post('/api/hrm/events/manual',json=dict(employee_id=eid,shift_id=key,scan_type=kind,ts=ts,reason='HR đối chiếu sổ ca'))

def test_shared_profiles_payroll_and_lock(env):
    from hrm.core import load_policy
    from hrm.store import put

    app, client, *_ = env
    day = "2026-10-06"
    month = day[:7]
    payroll_url = f"/api/hrm/payroll/{month}"

    response = profile(client, base_salary=10400000, hire_date="2026-10-01")
    assert response.status_code == 201, response.text
    employee_id = response.json()["employee_id"]

    # Use an isolated contract so the test can verify one day's pay.
    contract = {
        "resident": True,
        "nationality": "VN",
        "document_type": "trial",
        "duration_months": 1,
        "valid_from": month,
        "valid_until": month,
        "meal_per_day": 0,
        "attendance_bonus": 0,
    }
    with app.state.session_factory() as db:
        put(db, "payroll_config", month, {
            "payroll_2026_policy": load_policy(),
            "contracts": {employee_id: contract},
            "source": "TEST_FIXTURE",
        })
        db.commit()

    assert client.get("/api/hrm/auth/me").json()["role"] == "hr"
    assert employee_id in {
        row["employee_id"] for row in client.get("/api/hrm/employees").json()
    }
    schedule = {
        "start": f"{day}T07:00:00+07:00",
        "end": f"{day}T15:00:00+07:00",
    }
    response = shift(client, employee_id, **schedule)
    assert response.status_code == 200, response.text
    response = shift(client, employee_id, "overlap", **schedule)
    assert response.status_code == 409, response.text

    for kind, clock in (("IN", "07:00:00"), ("OUT", "16:00:00")):
        response = event(client, employee_id, kind, f"{day}T{clock}+07:00")
        assert response.status_code == 200, response.text
    response = client.get("/api/hrm/attendance", params={"month": month})
    assert response.status_code == 200, response.text
    row, = response.json()
    assert row["regular_hours"] == 8 and row["ot_hours"] == 1, row
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord)) == 2

    response = client.post(
        f"{payroll_url}/calculate",
        json={"note": "Đã kiểm tra công", "standard_hours": 208},
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["rows"][0]["net"] == 475000, run

    response = client.patch(
        f"/api/employees/{employee_id}", json={"base_salary": 12480000},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"{payroll_url}/finalize",
        json={"reviewed": True, "input_hash": run["input_hash"]},
    )
    assert response.status_code == 409, response.text

    response = client.post(f"{payroll_url}/calculate", json={"note": "Tính lại lương"})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["rows"][0]["net"] == 570000, run
    response = client.post(
        f"{payroll_url}/finalize",
        json={"reviewed": True, "input_hash": run["input_hash"]},
    )
    assert response.status_code == 200, response.text
    response = event(client, employee_id, "IN", f"{day}T07:10:00+07:00")
    assert response.status_code == 409, response.text
    assert client.get(f"{payroll_url}/export").content[:2] == b"PK"
    assert client.get("/api/hrm/audit").json()


def test_kiosk_to_timesheet_no_double_writes(env, monkeypatch):
    app, client, *_ = env
    employee_id = profile(client).json()["employee_id"]
    completed(env, employee_id)
    scan_time = datetime(2026, 11, 10, 10, 0, tzinfo=VN)
    class KioskTestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return scan_time.replace(tzinfo=None)
            return scan_time.astimezone(tz)
    monkeypatch.setattr(kiosk, "datetime", KioskTestClock)
    response = shift(
        client,
        employee_id,
        start=scan_time.replace(hour=7).isoformat(),
        end=scan_time.replace(hour=15).isoformat(),
    )
    assert response.status_code == 200, response.text

    files = [
        ("files", ("q.jpg", picture(seed), "image/jpeg"))
        for seed in range(50, 53)
    ]
    data = {
        "device_id": "CN01-TB01",
        "scan_type": "IN",
        "lat": 16.0471,
        "lon": 108.2208,
    }

    response = client.post("/api/kiosk/recognize", files=files, data=data)
    assert response.status_code == 200, response.text
    assert response.json()["recorded"] is True

    response = client.post("/api/kiosk/recognize", files=files, data=data)
    assert response.status_code == 200, response.text
    assert response.json()["recorded"] is False

    scan_time = scan_time.replace(hour=11)
    data["scan_type"] = "OUT"
    response = client.post("/api/kiosk/recognize", files=files, data=data)
    assert response.status_code == 200, response.text
    assert response.json()["recorded"] is True

    response = client.get(
        "/api/hrm/attendance",
        params={"month": scan_time.strftime("%Y-%m")},
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["status"] == "present"

    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceRecord)) == 2
        assert db.scalar(select(func.count()).select_from(AttendanceAssignment)) == 2

    data["lat"] = 0
    assert client.post("/api/kiosk/recognize", files=files, data=data).status_code == 403
    client.post("/api/auth/logout")
    assert client.post("/api/kiosk/recognize", files=files, data=data).status_code == 401


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
    assert shift(c,a,start='2026-01-02T07:00:00+07:00',end='2026-01-02T15:00:00+07:00').status_code==200
    body=dict(employee_id=a,start_date='2026-01-02',end_date='2026-01-02',leave_type='PAID',reason='Nghỉ có phép')
    assert c.post('/api/hrm/leaves',json=body).status_code==403
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
    submitted=c.post('/api/hrm/leaves',json=body)
    assert submitted.status_code==200, submitted.text
    assert submitted.json()['status']=='pending'
    leave_id=submitted.json()['leave_id']
    second=c.post('/api/hrm/leaves',json={**body,'start_date':'2026-01-03','end_date':'2026-01-03'})
    assert second.status_code==200
    second_id=second.json()['leave_id']
    assert c.post(f'/api/hrm/leaves/{leave_id}/decision',json={'status':'approved'}).status_code==403
    c.post('/api/auth/logout')
    assert c.post('/api/auth/login',json={'username':'manager','password':'test-enrollment-password'}).status_code==200
    row=next(row for row in c.get('/api/hrm/leaves').json() if row['leave_id']==leave_id)
    assert row['full_name']
    decision=c.post(f'/api/hrm/leaves/%20{leave_id}%20/decision',json={'status':'approved'})
    assert decision.status_code==200, decision.text
    assert c.post(f'/api/hrm/leaves/{second_id}/decision',json={'status':'rejected'}).json()['status']=='rejected'
    assert c.post(f'/api/hrm/leaves/{leave_id}/decision',json={'status':'rejected'}).status_code==409
    assert c.get('/api/hrm/attendance?month=2026-01').json()[0]['paid_leave_hours']==8
    c.post('/api/auth/logout')
    assert c.post('/api/auth/login',json={'username':'staff','password':'staff-password-123'}).status_code==200
    personal=c.get('/api/hrm/self?month=2026-01').json()['leaves']
    assert {row['leave_id']:row['status'] for row in personal}=={leave_id:'approved',second_id:'rejected'}


def test_manual_attendance_saves_assigned_events_and_ignores_retry(env):
    app, client, *_ = env
    eid = profile(client).json()['employee_id']
    assert shift(client, eid, start='2026-11-18T07:00:00+07:00', end='2026-11-18T15:00:00+07:00').status_code == 200
    assert event(client, eid, 'IN', '2026-11-18T01:00:00').status_code == 409
    entered = event(client, eid, 'IN', '2026-11-18T07:00:00').json()
    exited = event(client, eid, 'OUT', '2026-11-18T15:00:00').json()
    assert entered['source'] == exited['source'] == 'MANUAL'
    assert event(client, eid, 'OUT', '2026-11-18T15:00:00').json()['event_id'] == exited['event_id']
    row, = client.get('/api/hrm/attendance?month=2026-11').json()
    assert row['shift_id'] == 's1' and row['status'] == 'present' and row['regular_hours'] == 8
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceAssignment)) == 2
    assert len([item for item in client.get('/api/hrm/audit').json() if item['action'] == 'attendance_event']) == 2


def test_reconcile_existing_main_attendance_without_copy(env):
    app,c,*_=env
    e=profile(c).json()['employee_id']
    assert shift(c,e).status_code==200
    with app.state.session_factory() as db:
        old=AttendanceRecord(employee_id=e,device_id='CN01-TB01',scan_type='IN',timestamp=datetime(2026,1,2,7,tzinfo=VN).timestamp(),similarity=.8)
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
